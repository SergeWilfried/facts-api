import json
from unittest.mock import MagicMock, patch

from app.workers.verifier import _infer_stance


# ---------------------------------------------------------------------------
# _infer_stance (pure function — no mocking needed)
# ---------------------------------------------------------------------------

def test_infer_stance_verified():
    assert _infer_stance("verified", {}) == "supports"


def test_infer_stance_false():
    assert _infer_stance("false", {}) == "contradicts"


def test_infer_stance_misleading():
    assert _infer_stance("misleading", {}) == "neutral"


# ---------------------------------------------------------------------------
# verify (mocks Tavily + Claude)
# ---------------------------------------------------------------------------

def _tavily_results():
    return {
        "results": [
            {"title": "Fact Check: Honey", "url": "https://source1.com", "content": "Honey does not expire."},
            {"title": "Archaeology Report", "url": "https://source2.com", "content": "Ancient honey found in Egypt."},
        ]
    }


def _claude_response(text: str):
    content = MagicMock()
    content.text = text
    message = MagicMock()
    message.content = [content]
    return message


@patch("app.workers.verifier._claude")
@patch("app.workers.verifier._tavily")
def test_verify_returns_verification_result(mock_tavily, mock_claude):
    from app.workers.verifier import verify

    mock_tavily.search.return_value = _tavily_results()
    mock_claude.messages.create.return_value = _claude_response(
        json.dumps({"verdict": "verified", "confidence": 0.95, "reasoning": "Multiple sources confirm."})
    )

    result = verify("Honey never expires")

    assert result.verdict == "verified"
    assert result.confidence == 0.95
    assert result.reasoning == "Multiple sources confirm."
    assert len(result.sources) == 2
    assert result.sources[0]["url"] == "https://source1.com"
    assert result.sources[0]["stance"] == "supports"


@patch("app.workers.verifier._claude")
@patch("app.workers.verifier._tavily")
def test_verify_strips_markdown_fences(mock_tavily, mock_claude):
    from app.workers.verifier import verify

    mock_tavily.search.return_value = _tavily_results()
    raw = '```json\n{"verdict": "false", "confidence": 0.9, "reasoning": "No evidence."}\n```'
    mock_claude.messages.create.return_value = _claude_response(raw)

    result = verify("New law bans cash payments")

    assert result.verdict == "false"
    assert result.sources[0]["stance"] == "contradicts"


@patch("app.workers.verifier._claude")
@patch("app.workers.verifier._tavily")
def test_verify_confidence_defaults_when_missing(mock_tavily, mock_claude):
    from app.workers.verifier import verify

    mock_tavily.search.return_value = _tavily_results()
    mock_claude.messages.create.return_value = _claude_response(
        json.dumps({"verdict": "misleading", "reasoning": "Partial truth."})
        # no "confidence" key
    )

    result = verify("Bank fees will triple")

    assert result.confidence == 0.8  # fallback value


@patch("app.workers.verifier._claude")
@patch("app.workers.verifier._tavily")
def test_verify_passes_claim_to_tavily(mock_tavily, mock_claude):
    from app.workers.verifier import verify

    mock_tavily.search.return_value = {"results": []}
    mock_claude.messages.create.return_value = _claude_response(
        json.dumps({"verdict": "misleading", "confidence": 0.5, "reasoning": "..."})
    )

    verify("Solar eclipse visible next Friday")

    call_kwargs = mock_tavily.search.call_args
    assert "Solar eclipse" in call_kwargs.kwargs.get("query", "") or \
           "Solar eclipse" in (call_kwargs.args[0] if call_kwargs.args else "")
