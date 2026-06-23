"""Extract caption, video URL, author, and platform from a social media URL via Apify."""
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


def extract(url: str) -> ExtractedContent:
    actor = _actor_for_url(url)
    if not actor:
        raise ValueError(f"Unsupported URL: {url}")

    client = ApifyClient(settings.apify_api_token)
    run = client.actor(actor).call(run_input={"startUrls": [{"url": url}], "resultsLimit": 1})
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    if not items:
        raise RuntimeError(f"Apify returned no results for {url}")

    return _parse_result(actor, items[0])
