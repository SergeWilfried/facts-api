from unittest.mock import MagicMock, patch


def _make_claude_response(text: str):
    content = MagicMock()
    content.text = text
    message = MagicMock()
    message.content = [content]
    return message


@patch("app.workers.claim_extractor._client")
def test_empty_content_returns_no_api_call(mock_client):
    from app.workers.claim_extractor import extract_claims

    result = extract_claims(None, None)

    assert result == []
    mock_client.messages.create.assert_not_called()


@patch("app.workers.claim_extractor._client")
def test_whitespace_only_content_returns_empty(mock_client):
    from app.workers.claim_extractor import extract_claims

    result = extract_claims("   ", "\n\n")

    assert result == []
    mock_client.messages.create.assert_not_called()


@patch("app.workers.claim_extractor._client")
def test_caption_only_extracts_claims(mock_client):
    from app.workers.claim_extractor import extract_claims

    mock_client.messages.create.return_value = _make_claude_response(
        '["Honey never expires", "Archaeologists found 3000-year-old honey"]'
    )

    result = extract_claims("Honey never expires! Archaeologists found 3000-year-old honey in Egypt.", None)

    assert result == ["Honey never expires", "Archaeologists found 3000-year-old honey"]
    mock_client.messages.create.assert_called_once()


@patch("app.workers.claim_extractor._client")
def test_strips_markdown_code_fences(mock_client):
    from app.workers.claim_extractor import extract_claims

    mock_client.messages.create.return_value = _make_claude_response(
        '```json\n["Bank fees will triple"]\n```'
    )

    result = extract_claims("Bank fees will triple under new mobile money rules.", None)

    assert result == ["Bank fees will triple"]


@patch("app.workers.claim_extractor._client")
def test_combines_caption_and_transcript(mock_client):
    from app.workers.claim_extractor import extract_claims

    mock_client.messages.create.return_value = _make_claude_response('["Claim A", "Claim B"]')

    extract_claims("Caption text", "Transcript text")

    call_kwargs = mock_client.messages.create.call_args
    user_content = call_kwargs.kwargs["messages"][0]["content"]
    assert "Caption text" in user_content
    assert "Transcript text" in user_content


@patch("app.workers.claim_extractor._client")
def test_filters_out_non_string_entries(mock_client):
    from app.workers.claim_extractor import extract_claims

    mock_client.messages.create.return_value = _make_claude_response(
        '["Valid claim", null, 42, "", "Another claim"]'
    )

    result = extract_claims("Some post text", None)

    assert result == ["Valid claim", "Another claim"]
