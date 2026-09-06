import datetime
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.ingest_gemini import (
    find_transcripts_on_disk,
    parse_publish_date,
    extract_metadata_and_body,
    chunk_text,
    extract_timestamp_ref,
    GeminiEmbedder,
    insert_gemini_chunks,
    is_episode_already_ingested,
)
from app.models.db_models import TranscriptChunkGemini


def test_parse_publish_date():
    assert parse_publish_date("2023-04-21") == datetime.date(2023, 4, 21)
    assert parse_publish_date("2023/04/21") == datetime.date(2023, 4, 21)
    d = datetime.date(2022, 10, 13)
    assert parse_publish_date(d) == d
    dt = datetime.datetime(2022, 10, 13, 12, 0, 0)
    assert parse_publish_date(dt) == d
    assert parse_publish_date("invalid-date") is None
    assert parse_publish_date(None) is None


def test_extract_metadata_and_body(tmp_path):
    ep_dir = tmp_path / "test-guest"
    ep_dir.mkdir()
    transcript_file = ep_dir / "transcript.md"

    content = """---
guest: Test Guest
title: How to Scale Growth | Test Guest
youtube_url: https://www.youtube.com/watch?v=mock123
video_id: mock123
publish_date: 2024-05-15
---

# How to Scale Growth | Test Guest

## Transcript

Test Guest (00:00:15):
Growth requires relentless customer focus and experimentation.

Lenny (00:01:00):
Tell us more about how you prioritize bets.
"""
    transcript_file.write_text(content, encoding="utf-8")

    meta = extract_metadata_and_body(transcript_file)
    assert meta["slug"] == "test-guest"
    assert meta["guest"] == "Test Guest"
    assert meta["title"] == "How to Scale Growth | Test Guest"
    assert meta["youtube_url"] == "https://www.youtube.com/watch?v=mock123"
    assert meta["video_id"] == "mock123"
    assert meta["publish_date"] == datetime.date(2024, 5, 15)
    assert "Growth requires relentless customer focus" in meta["body_text"]


def test_chunk_text_reused_logic():
    # Verify paragraph splitting and overlap behavior
    text = "Paragraph 1: " + "a" * 500 + "\n\nParagraph 2: " + "b" * 500 + "\n\nParagraph 3: " + "c" * 500
    chunks = chunk_text(text, chunk_size=800, chunk_overlap=200)

    assert len(chunks) >= 2
    assert "Paragraph 1" in chunks[0]
    # Verify empty text handling
    assert chunk_text("") == []
    assert chunk_text("   \n\n   ") == []


def test_extract_timestamp_ref():
    s1 = "Ada Chen Rekhi (00:03:20): Thanks. I'm excited to be here."
    assert extract_timestamp_ref(s1, 0) == "00:03:20"

    s2 = "Lenny (12:45): That makes total sense."
    assert extract_timestamp_ref(s2, 5) == "12:45"

    s3 = "No timestamp here in this paragraph."
    assert extract_timestamp_ref(s3, 3) == "chunk_3"


def test_gemini_embedder_dimension_and_fallback():
    # Mock client and response
    mock_client = MagicMock()
    mock_emb_item = MagicMock()
    mock_emb_item.values = [0.1] * 768

    mock_resp = MagicMock()
    mock_resp.embeddings = [mock_emb_item]

    # Test when gemini-embedding-001 succeeds
    mock_client.models.embed_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client):
        embedder = GeminiEmbedder(api_key="mock-key", preferred_model="gemini-embedding-001")
        embeddings = embedder.embed_texts(["Test chunk"])
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 768

    # Test fallback to gemini-embedding-2 when primary returns 429
    mock_client_fallback = MagicMock()

    def side_effect(model, contents, config):
        if model == "gemini-embedding-001":
            raise Exception("429 RESOURCE_EXHAUSTED. Quota exceeded for gemini-embedding-001")
        mock_resp_fallback = MagicMock()
        mock_resp_fallback.embeddings = [mock_emb_item]
        return mock_resp_fallback

    mock_client_fallback.models.embed_content.side_effect = side_effect

    with patch("google.genai.Client", return_value=mock_client_fallback):
        embedder = GeminiEmbedder(api_key="mock-key", preferred_model="gemini-embedding-001")
        embeddings = embedder.embed_texts(["Test fallback chunk"])
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 768
        assert embedder.active_model == "gemini-embedding-2"


def test_transcript_chunk_gemini_model():
    chunk = TranscriptChunkGemini(
        episode_title="Test Episode",
        guest_name="Test Guest",
        publication_date=datetime.date(2024, 1, 1),
        timestamp_ref="00:01:00",
        youtube_url="https://youtube.com/watch?v=123",
        chunk_text="Test content",
        embedding=[0.0] * 768,
    )
    assert chunk.__tablename__ == "transcript_chunks_gemini"
    assert chunk.episode_title == "Test Episode"
    assert chunk.guest_name == "Test Guest"
    assert len(chunk.embedding) == 768
    assert "transcript_chunks_gemini" in str(TranscriptChunkGemini.__table__.name)
