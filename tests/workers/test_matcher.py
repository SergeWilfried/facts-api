from unittest.mock import MagicMock, patch
import uuid


def _fake_embedding(dim: int = 1536) -> list[float]:
    return [0.1] * dim


def _openai_embed_response(embedding: list[float]):
    data = MagicMock()
    data.embedding = embedding
    response = MagicMock()
    response.data = [data]
    return response


# ---------------------------------------------------------------------------
# embed
# ---------------------------------------------------------------------------

@patch("app.workers.matcher._openai")
def test_embed_calls_openai_and_returns_vector(mock_openai):
    from app.workers.matcher import embed

    mock_openai.embeddings.create.return_value = _openai_embed_response(_fake_embedding())

    result = embed("Some claim text")

    mock_openai.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small",
        input="Some claim text",
    )
    assert len(result) == 1536
    assert isinstance(result[0], float)


# ---------------------------------------------------------------------------
# find_similar
# ---------------------------------------------------------------------------

@patch("app.workers.matcher.SyncSessionLocal")
@patch("app.workers.matcher._openai")
def test_find_similar_returns_none_when_no_rows(mock_openai, mock_session_cls):
    from app.workers.matcher import find_similar

    mock_openai.embeddings.create.return_value = _openai_embed_response(_fake_embedding())

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.fetchall.return_value = []
    mock_session_cls.return_value = mock_session

    result = find_similar("Honey never expires")

    assert result is None


@patch("app.workers.matcher.SyncSessionLocal")
@patch("app.workers.matcher._openai")
def test_find_similar_returns_matched_claim(mock_openai, mock_session_cls):
    from app.workers.matcher import find_similar

    mock_openai.embeddings.create.return_value = _openai_embed_response(_fake_embedding())

    fake_id = uuid.uuid4()
    row = MagicMock()
    row.id = fake_id
    row.text = "Honey does not expire"
    row.verdict = "verified"
    row.similarity = 0.94

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.fetchall.return_value = [row]
    mock_session_cls.return_value = mock_session

    result = find_similar("Honey never expires")

    assert result is not None
    assert result.claim_id == str(fake_id)
    assert result.verdict == "verified"
    assert result.similarity == 0.94


@patch("app.workers.matcher.SyncSessionLocal")
@patch("app.workers.matcher._openai")
def test_find_similar_builds_correct_sql_params(mock_openai, mock_session_cls):
    from app.workers.matcher import find_similar, _SIMILARITY_THRESHOLD

    vec = _fake_embedding()
    mock_openai.embeddings.create.return_value = _openai_embed_response(vec)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.fetchall.return_value = []
    mock_session_cls.return_value = mock_session

    find_similar("Test claim")

    call_args = mock_session.execute.call_args
    params = call_args.args[1]
    assert params["threshold"] == _SIMILARITY_THRESHOLD
    assert params["vec"].startswith("[")
    assert params["vec"].endswith("]")
