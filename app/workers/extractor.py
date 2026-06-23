"""Extract caption, video URL, author, and platform from a social media or web URL."""
import re
from dataclasses import dataclass
from typing import Optional

from apify_client import ApifyClient

from app.config import settings

# Map of URL pattern → Apify actor ID
_ACTOR_MAP = [
    (r"tiktok\.com", "clockworks/free-tiktok-scraper"),
    (r"instagram\.com", "apify/instagram-scraper"),
    (r"facebook\.com|fb\.watch", "apify/facebook-posts-scraper"),
    (r"twitter\.com|x\.com", "apidojo/tweet-scraper"),
    (r"youtube\.com|youtu\.be", "bernardo/youtube-scraper"),
]


@dataclass
class ExtractedContent:
    platform: str
    author_handle: Optional[str]
    caption: Optional[str]
    video_url: Optional[str]  # direct downloadable video URL if available


def _detect_platform(url: str) -> Optional[str]:
    for pattern, _ in _ACTOR_MAP:
        if re.search(pattern, url):
            return pattern.split(r"\.")[0].replace("\\", "")
    return "unknown"


def _actor_for_url(url: str) -> Optional[str]:
    for pattern, actor in _ACTOR_MAP:
        if re.search(pattern, url):
            return actor
    return None


def _parse_result(actor: str, item: dict) -> ExtractedContent:
    """Normalise the raw Apify item into a common shape."""
    if "tiktok" in actor:
        return ExtractedContent(
            platform="tiktok",
            author_handle=item.get("authorMeta", {}).get("name"),
            caption=item.get("text"),
            video_url=item.get("videoUrl"),
        )
    if "instagram" in actor:
        return ExtractedContent(
            platform="instagram",
            author_handle=item.get("ownerUsername"),
            caption=item.get("caption"),
            video_url=item.get("videoUrl"),
        )
    if "facebook" in actor:
        return ExtractedContent(
            platform="facebook",
            author_handle=item.get("pageName"),
            caption=item.get("text"),
            video_url=item.get("video", {}).get("url") if item.get("video") else None,
        )
    if "tweet" in actor:
        return ExtractedContent(
            platform="twitter",
            author_handle=item.get("author", {}).get("userName"),
            caption=item.get("text"),
            video_url=None,
        )
    if "youtube" in actor:
        return ExtractedContent(
            platform="youtube",
            author_handle=item.get("channelName"),
            caption=item.get("title", "") + "\n" + item.get("description", ""),
            video_url=None,
        )
    return ExtractedContent(platform="unknown", author_handle=None, caption=None, video_url=None)


def _assert_safe_url(url: str) -> None:
    """Reject non-public URLs to prevent SSRF."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: missing hostname")

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError("Could not resolve hostname")

    _BLOCKED = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("169.254.0.0/16"),   # link-local / AWS metadata
        ipaddress.ip_network("fe80::/10"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("fc00::/7"),           # unique local
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("224.0.0.0/4"),        # multicast
    ]

    for _, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if any(ip in net for net in _BLOCKED):
            raise ValueError("URL resolves to a disallowed address")


def _extract_article(url: str) -> ExtractedContent:
    """Fallback: extract article text via Tavily (handles anti-crawl)."""
    from urllib.parse import urlparse
    from tavily import TavilyClient

    _assert_safe_url(url)

    client = TavilyClient(api_key=settings.tavily_api_key)
    response = client.extract(urls=[url])

    results = response.get("results", [])
    if not results:
        raise RuntimeError("Tavily could not extract content from the URL")

    raw_content = results[0].get("raw_content") or results[0].get("content") or ""
    text = raw_content[:8000]  # cap to avoid token overflow

    domain = urlparse(url).netloc.replace("www.", "")
    return ExtractedContent(
        platform="web",
        author_handle=domain,
        caption=text,
        video_url=None,
    )


def extract(url: str) -> ExtractedContent:
    actor = _actor_for_url(url)
    if not actor:
        return _extract_article(url)

    client = ApifyClient(settings.apify_api_token)
    run = client.actor(actor).call(run_input={"startUrls": [{"url": url}], "resultsLimit": 1})
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    if not items:
        raise RuntimeError(f"Apify returned no results for {url}")

    return _parse_result(actor, items[0])
