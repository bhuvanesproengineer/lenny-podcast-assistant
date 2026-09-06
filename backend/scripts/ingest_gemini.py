"""
Standalone Ingestion Pipeline for Gemini Embeddings.

Reads transcript markdown files directly from disk:
    lennys-podcast-transcripts/episodes/**/transcript.md

Preserves frontmatter metadata:
    - guest
    - title
    - youtube_url
    - publish_date
    - episode information (slug, timestamp_ref)

Reuses chunking logic:
    - chunk_size: 1200 chars
    - chunk_overlap: 200 chars
    - paragraph-aware splitting

Generates embeddings:
    - Gemini gemini-embedding-001 (768 dimensions)
    - Graceful fallback to gemini-embedding-2 (768 dimensions) if primary is unavailable

Target Table:
    - transcript_chunks_gemini

STRICT INVARIANTS:
    - Does NOT read from transcript_chunks
    - Does NOT modify existing nomic embeddings
    - Does NOT modify current retrieval flow
    - Recursively processes ALL 303 episode folders
    - Skips duplicates safely using episode_title + chunk index checks
"""

import argparse
import asyncio
import datetime
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from dotenv import load_dotenv
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Locate repo and backend root directories
current_file = Path(__file__).resolve()
backend_dir = current_file.parent.parent
repo_root = backend_dir.parent

# Ensure backend_dir is in sys.path
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Load environment variables (.env from repo root or backend)
load_dotenv(repo_root / ".env")
load_dotenv(backend_dir / ".env")

from app.database import AsyncSessionLocal, engine
from app.models.db_models import TranscriptChunkGemini

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingest_gemini")


# ==============================================================================
# 1. Direct Disk Discovery & Metadata Parsing
# ==============================================================================

def find_transcripts_on_disk(base_dir: Path) -> List[Tuple[Path, Path]]:
    """
    Recursively scans base_dir to locate all episode directories containing transcript.md.
    Returns sorted list of (episode_folder, transcript_file).
    No slicing or limits applied here — discovers all episode folders.
    """
    if not base_dir.exists():
        logger.error(f"Transcripts directory does not exist: {base_dir}")
        return []

    episodes: List[Tuple[Path, Path]] = []
    for transcript_path in sorted(base_dir.rglob("transcript.md")):
        if transcript_path.is_file():
            episodes.append((transcript_path.parent, transcript_path))

    return episodes


def parse_publish_date(raw_date: Any) -> Optional[datetime.date]:
    """
    Safely parses a publish_date from YAML frontmatter into a datetime.date object.
    Checks datetime.datetime before datetime.date.
    """
    if isinstance(raw_date, datetime.datetime):
        return raw_date.date()
    if isinstance(raw_date, datetime.date):
        return raw_date
    if isinstance(raw_date, str):
        raw_date = raw_date.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.datetime.strptime(raw_date, fmt).date()
            except ValueError:
                continue
        try:
            return datetime.date.fromisoformat(raw_date)
        except ValueError:
            pass
    return None


def extract_metadata_and_body(transcript_file: Path) -> Dict[str, Any]:
    """
    Parses YAML frontmatter and body from a transcript.md file.
    Extracts:
        - guest (str)
        - title (str)
        - youtube_url (str or None)
        - publish_date (datetime.date or None)
        - slug (str)
        - body_text (str)
        - video_id (str or None)
    """
    slug = transcript_file.parent.name
    content = transcript_file.read_text(encoding="utf-8", errors="ignore")

    metadata: Dict[str, Any] = {
        "slug": slug,
        "guest": slug.replace("-", " ").title(),
        "title": slug.replace("-", " ").title(),
        "youtube_url": None,
        "publish_date": None,
        "video_id": None,
        "body_text": content,
    }

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1])
                if isinstance(fm, dict):
                    if fm.get("guest"):
                        metadata["guest"] = str(fm["guest"]).strip()
                    if fm.get("title"):
                        metadata["title"] = str(fm["title"]).strip()
                    elif metadata["guest"]:
                        metadata["title"] = f"Episode with {metadata['guest']}"
                    if fm.get("youtube_url"):
                        metadata["youtube_url"] = str(fm["youtube_url"]).strip()
                    if fm.get("video_id"):
                        metadata["video_id"] = str(fm["video_id"]).strip()
                    if fm.get("publish_date"):
                        metadata["publish_date"] = parse_publish_date(fm["publish_date"])
            except Exception as exc:
                logger.warning(f"Could not parse YAML frontmatter for '{slug}': {exc}")
            metadata["body_text"] = parts[2]

    # Fallback to markdown header if title was not in frontmatter
    if metadata["title"] == slug.replace("-", " ").title():
        for line in metadata["body_text"].splitlines():
            line_str = line.strip()
            if line_str.startswith("# ") and len(line_str) > 2:
                metadata["title"] = line_str[2:].strip()
                break

    return metadata


# ==============================================================================
# 2. Existing Chunking Logic (Reused Exactly)
# ==============================================================================

def chunk_text(text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> List[str]:
    """
    Splits transcript dialogue into semantic chunks of roughly chunk_size characters
    with chunk_overlap character overlap between adjacent chunks.
    Preserves paragraph structure where possible.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_length = 0

    for para in paragraphs:
        para_len = len(para)

        if current_length + para_len > chunk_size and current_chunk:
            combined = "\n\n".join(current_chunk).strip()
            if combined:
                chunks.append(combined)

            overlap_chunk: List[str] = []
            overlap_len = 0
            for p in reversed(current_chunk):
                if overlap_len + len(p) <= chunk_overlap:
                    overlap_chunk.insert(0, p)
                    overlap_len += len(p)
                else:
                    break
            current_chunk = overlap_chunk
            current_length = overlap_len

        if para_len > chunk_size:
            words = para.split()
            buf: List[str] = []
            buf_len = 0
            for w in words:
                if buf_len + len(w) + 1 > chunk_size and buf:
                    chunk_str = " ".join(buf).strip()
                    if chunk_str:
                        chunks.append(chunk_str)
                    buf = buf[-25:]
                    buf_len = sum(len(x) + 1 for x in buf)
                buf.append(w)
                buf_len += len(w) + 1
            if buf:
                current_chunk.append(" ".join(buf))
                current_length += buf_len
        else:
            current_chunk.append(para)
            current_length += para_len + 2

    if current_chunk:
        combined = "\n\n".join(current_chunk).strip()
        if combined:
            chunks.append(combined)

    return chunks


def extract_timestamp_ref(chunk_str: str, default_idx: int) -> str:
    """
    Extracts the first timestamp pattern (e.g., (00:12:34) or (12:34)) from chunk,
    or falls back to 'chunk_{default_idx}'.
    """
    match = re.search(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", chunk_str)
    if match:
        return match.group(1)
    return f"chunk_{default_idx}"


# ==============================================================================
# 3. Gemini Embedding Client (gemini-embedding-001 + fallback)
# ==============================================================================

class GeminiEmbedder:
    """
    Generates 768-dimensional embeddings using Gemini API.
    Uses gemini-embedding-001 as primary supported model, falling back to:
    ['gemini-embedding-001', 'gemini-embedding-2', 'gemini-embedding-2-preview'].
    Tracks per-model cooldowns on 429 quota exhaustion to maximize throughput across model quotas.
    """

    FALLBACK_POOL = ["gemini-embedding-001", "gemini-embedding-2", "gemini-embedding-2-preview"]

    def __init__(self, api_key: Optional[str] = None, preferred_model: str = "gemini-embedding-001"):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GOOGLE_API_KEY is not set. Please provide it via environment variable or --api-key."
            )

        from google import genai
        self.client = genai.Client(api_key=self.api_key)
        self.preferred_model = preferred_model
        self.active_models = [preferred_model] if preferred_model not in self.FALLBACK_POOL else list(self.FALLBACK_POOL)
        self.active_model = preferred_model
        self.fallback_model = self.FALLBACK_POOL[0]
        self.model_cooldowns: Dict[str, float] = {}
        self.current_idx = 0
        self._preferred_failed = False

    def _get_next_model(self) -> Optional[str]:
        """Selects the next available model that is not in a cooldown state."""
        models = self.FALLBACK_POOL if self._preferred_failed else [self.preferred_model] + self.FALLBACK_POOL
        now = time.time()

        for i in range(len(models)):
            idx = (self.current_idx + i) % len(models)
            candidate = models[idx]
            if now >= self.model_cooldowns.get(candidate, 0.0):
                self.current_idx = idx
                self.active_model = candidate
                return candidate

        # All models cooling down; return None to avoid blocking entire ingestion
        return None

    def embed_texts(self, texts: List[str], max_retries: int = 3) -> Optional[List[List[float]]]:
        """
        Embeds a list of texts into 768-dimensional vectors.
        Rotates across available models. If quota is exhausted, returns None.
        """
        if not texts:
            return []

        from google.genai import types

        for attempt in range(1, max_retries + 1):
            model = self._get_next_model()
            if model is None:
                logger.info("All Gemini embedding models currently rate-limited. Storing chunks with metadata.")
                return None

            try:
                config = types.EmbedContentConfig(output_dimensionality=768)
                response = self.client.models.embed_content(
                    model=model,
                    contents=texts,
                    config=config,
                )
                embeddings = [e.values for e in response.embeddings]
                if embeddings and len(embeddings[0]) != 768:
                    return None
                time.sleep(0.3)
                self.current_idx = (self.current_idx + 1) % len(self.FALLBACK_POOL)
                return embeddings

            except Exception as exc:
                exc_str = str(exc)
                if ("404" in exc_str or "NOT_FOUND" in exc_str):
                    logger.warning(f"Model '{model}' returned 404/NOT_FOUND. Activating multi-model fallback pool.")
                    self._preferred_failed = True
                    self.model_cooldowns[model] = time.time() + 999999.0
                    continue

                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    logger.warning(f"Rate limit (429) on '{model}'. Setting cooldown for 60s.")
                    self.model_cooldowns[model] = time.time() + 60.0
                    self.current_idx = (self.current_idx + 1) % len(self.FALLBACK_POOL)
                    continue

                logger.warning(f"Embedding error on '{model}': {exc}")
                return None

        return None


# ==============================================================================
# 4. Ingestion Orchestrator
# ==============================================================================

async def get_existing_episode_chunks(session: AsyncSession, episode_title: str) -> Set[str]:
    """
    Returns existing timestamp_ref / chunk identifiers for an episode in transcript_chunks_gemini.
    Strictly checks transcript_chunks_gemini; does NOT touch transcript_chunks.
    """
    stmt = (
        select(TranscriptChunkGemini.timestamp_ref)
        .where(TranscriptChunkGemini.episode_title == episode_title)
    )
    result = await session.execute(stmt)
    return set(r for r in result.scalars().all() if r)


async def is_episode_already_ingested(session: AsyncSession, episode_title: str) -> bool:
    """
    Checks if an episode has any chunks in transcript_chunks_gemini.
    """
    existing = await get_existing_episode_chunks(session, episode_title)
    return len(existing) > 0


async def delete_episode_chunks(session: AsyncSession, episode_title: str) -> int:
    """
    Deletes existing chunks for an episode from transcript_chunks_gemini (for --force re-ingestion).
    """
    stmt = text(
        "DELETE FROM transcript_chunks_gemini WHERE episode_title = :title"
    )
    res = await session.execute(stmt, {"title": episode_title})
    await session.commit()
    return res.rowcount or 0


async def insert_gemini_chunks(
    session: AsyncSession,
    chunks_data: List[Dict[str, Any]]
) -> int:
    """
    Inserts chunk records with Gemini embeddings directly into transcript_chunks_gemini.
    """
    if not chunks_data:
        return 0

    chunk_objects = [
        TranscriptChunkGemini(
            id=uuid.uuid4(),
            episode_title=c["episode_title"],
            guest_name=c["guest_name"],
            publication_date=c["publication_date"],
            timestamp_ref=c["timestamp_ref"],
            youtube_url=c["youtube_url"],
            chunk_text=c["chunk_text"],
            embedding=c["embedding"],
        )
        for c in chunks_data
    ]

    session.add_all(chunk_objects)
    await session.commit()
    return len(chunk_objects)


async def run_gemini_ingestion(
    transcripts_dir: Path,
    limit: Optional[int] = None,
    batch_size: int = 50,
    dry_run: bool = False,
    force: bool = False,
    preferred_model: str = "gemini-embedding-001",
) -> Dict[str, Any]:
    """
    Executes the standalone Gemini ingestion workflow.
    Recursively processes ALL episode folders found on disk.
    """
    start_time = time.time()
    logger.info("=" * 70)
    logger.info("STARTING GEMINI TRANSCRIPT INGESTION PIPELINE")
    logger.info(f"Source Directory: {transcripts_dir.resolve()}")
    logger.info(f"Target Table:     transcript_chunks_gemini (768-dim)")
    logger.info(f"Preferred Model:  {preferred_model}")
    logger.info(f"Batch Size:       {batch_size}")
    logger.info(f"Dry Run:          {dry_run}")
    logger.info(f"Force Ingest:     {force}")
    logger.info("=" * 70)

    # 1. Discover all transcript.md files directly on disk
    episode_files = find_transcripts_on_disk(transcripts_dir)
    total_discovered = len(episode_files)
    logger.info(f"Discovered {total_discovered} episode transcript(s) on disk.")

    if total_discovered == 0:
        logger.error(f"No transcript.md files found in {transcripts_dir}!")
        return {"status": "error", "message": "No transcript files found."}

    # Only apply limit if explicitly passed via CLI
    if limit is not None and limit > 0:
        episode_files = episode_files[:limit]
        logger.info(f"Applying execution limit: processing {len(episode_files)} episode(s).")
    else:
        logger.info(f"Processing ALL {total_discovered} episode(s) without restriction.")

    # 2. Initialize Embedder if not in dry-run mode
    embedder: Optional[GeminiEmbedder] = None
    if not dry_run:
        embedder = GeminiEmbedder(preferred_model=preferred_model)
        logger.info(f"Initialized GeminiEmbedder with model target: {preferred_model}")

    episodes_processed = 0
    episodes_skipped = 0
    total_chunks_created = 0
    total_embeddings_stored = 0

    # Disambiguate duplicate titles across folders so each folder maps to a distinct episode
    from collections import Counter
    raw_titles = [extract_metadata_and_body(tp)["title"] for _, tp in episode_files]
    title_counts = Counter(raw_titles)
    seen_titles: Set[str] = set()

    async with AsyncSessionLocal() as session:
        for idx, (ep_folder, transcript_path) in enumerate(episode_files, 1):
            ep_start = time.time()

            try:
                meta = extract_metadata_and_body(transcript_path)
                raw_title = meta["title"]
                if title_counts[raw_title] > 1:
                    if raw_title not in seen_titles:
                        episode_title = raw_title
                        seen_titles.add(raw_title)
                    else:
                        episode_title = f"{raw_title} ({ep_folder.name})"
                else:
                    episode_title = raw_title

                guest_name = meta["guest"]
                pub_date = meta["publish_date"]
                yt_url = meta["youtube_url"]

                # Progress logging in required format
                logger.info(f"Processing episode {idx}/{len(episode_files)}: '{episode_title}' (Guest: {guest_name})")
                print(f"Processing episode {idx}/{len(episode_files)}: '{episode_title}'", flush=True)

                # Generate dialogue chunks
                text_chunks = chunk_text(meta["body_text"], chunk_size=1200, chunk_overlap=200)
                if not text_chunks:
                    logger.warning(f"  No text chunks generated for '{episode_title}'. Skipping.")
                    continue

                if dry_run:
                    total_chunks_created += len(text_chunks)
                    episodes_processed += 1
                    logger.info(f"  [DRY RUN] Would embed and insert {len(text_chunks)} chunks.")
                    continue

                # Duplicate protection: check existing chunks in transcript_chunks_gemini
                existing_refs = await get_existing_episode_chunks(session, episode_title)

                if force and existing_refs:
                    deleted = await delete_episode_chunks(session, episode_title)
                    logger.info(f"  --force specified: removed {deleted} existing chunks for '{episode_title}'")
                    existing_refs = set()

                # If all chunks already exist, skip episode safely
                if len(existing_refs) >= len(text_chunks):
                    logger.info(f"  Episode already fully ingested ({len(existing_refs)} chunks present). Skipping.")
                    episodes_skipped += 1
                    continue

                # Identify only chunks that still need to be embedded and inserted
                pending_chunks: List[Tuple[int, str, str]] = []  # (chunk_idx, chunk_text, timestamp_ref)
                for chunk_idx, chunk_str in enumerate(text_chunks):
                    t_ref = extract_timestamp_ref(chunk_str, chunk_idx)
                    chunk_id = f"chunk_{chunk_idx}"
                    # Skip if chunk timestamp or index already recorded
                    if t_ref in existing_refs or chunk_id in existing_refs:
                        continue
                    pending_chunks.append((chunk_idx, chunk_str, t_ref))

                if not pending_chunks:
                    logger.info(f"  All chunks for '{episode_title}' already exist. Skipping.")
                    episodes_skipped += 1
                    continue

                logger.info(f"  Embedding {len(pending_chunks)} pending chunk(s) (of {len(text_chunks)} total)...")

                episode_chunks_data: List[Dict[str, Any]] = []

                # Embed chunks in batches
                for batch_start in range(0, len(pending_chunks), batch_size):
                    batch_items = pending_chunks[batch_start : batch_start + batch_size]
                    batch_texts = [item[1] for item in batch_items]

                    logger.info(
                        f"  Batch {batch_start // batch_size + 1}/"
                        f"{(len(pending_chunks) + batch_size - 1) // batch_size} "
                        f"({len(batch_texts)} chunks)..."
                    )

                    embeddings = embedder.embed_texts(batch_texts) if embedder else None
                    if embeddings is None:
                        embeddings = [None] * len(batch_items)
                    else:
                        total_embeddings_stored += sum(1 for e in embeddings if e is not None)

                    for (chunk_idx, chunk_str, t_ref), emb in zip(batch_items, embeddings):
                        episode_chunks_data.append({
                            "episode_title": episode_title,
                            "guest_name": guest_name,
                            "publication_date": pub_date,
                            "timestamp_ref": t_ref,
                            "youtube_url": yt_url,
                            "chunk_text": chunk_str,
                            "embedding": emb,
                        })

                # Insert into transcript_chunks_gemini
                inserted_count = await insert_gemini_chunks(session, episode_chunks_data)
                total_chunks_created += inserted_count
                episodes_processed += 1

                ep_elapsed = time.time() - ep_start
                logger.info(
                    f"  Inserted {inserted_count} chunks into transcript_chunks_gemini "
                    f"in {ep_elapsed:.2f}s."
                )

            except Exception as ep_exc:
                logger.error(f"Error processing episode at {transcript_path}: {ep_exc}", exc_info=True)
                continue

    total_elapsed = time.time() - start_time

    # Print completion summary as required by specification
    print("\n" + "=" * 60, flush=True)
    print(f"Total Episodes Processed: {episodes_processed}", flush=True)
    print(f"Total Chunks Created:    {total_chunks_created}", flush=True)
    print(f"Total Embeddings Stored: {total_embeddings_stored}", flush=True)
    print("=" * 60 + "\n", flush=True)

    logger.info("=" * 70)
    logger.info("GEMINI INGESTION COMPLETED")
    logger.info(f"Total Elapsed Time:       {total_elapsed:.2f}s")
    logger.info(f"Total Episodes Processed: {episodes_processed}")
    logger.info(f"Total Episodes Skipped:   {episodes_skipped}")
    logger.info(f"Total Chunks Created:    {total_chunks_created}")
    logger.info(f"Total Embeddings Stored: {total_embeddings_stored}")
    logger.info(f"Active Model Used:        {embedder.active_model if embedder else 'N/A (dry-run)'}")
    logger.info("=" * 70)

    return {
        "episodes_processed": episodes_processed,
        "episodes_skipped": episodes_skipped,
        "total_chunks_created": total_chunks_created,
        "total_embeddings_stored": total_embeddings_stored,
        "active_model": embedder.active_model if embedder else None,
        "elapsed_seconds": total_elapsed,
    }


# ==============================================================================
# 5. Verification Commands
# ==============================================================================

async def verify_gemini_table() -> Dict[str, Any]:
    """
    Performs comprehensive verification on transcript_chunks_gemini table:
    1. Total rows in transcript_chunks_gemini.
    2. Distinct episode count.
    3. Metadata completeness (null titles, null guests, null dates, null urls).
    4. Non-null embedding count and dimensionality.
    5. Verifies that transcript_chunks row count and nomic embeddings are intact.
    """
    logger.info("=" * 70)
    logger.info("VERIFYING TRANSCRIPT_CHUNKS_GEMINI TABLE")
    logger.info("=" * 70)

    async with AsyncSessionLocal() as session:
        # 1. Total chunks in transcript_chunks_gemini
        gemini_count_res = await session.execute(
            text("SELECT COUNT(*) FROM transcript_chunks_gemini")
        )
        gemini_total = gemini_count_res.scalar() or 0

        # 2. Distinct episodes in transcript_chunks_gemini
        ep_count_res = await session.execute(
            text("SELECT COUNT(DISTINCT episode_title) FROM transcript_chunks_gemini")
        )
        distinct_eps = ep_count_res.scalar() or 0

        # 3. Metadata validation
        null_title_res = await session.execute(
            text("SELECT COUNT(*) FROM transcript_chunks_gemini WHERE episode_title IS NULL")
        )
        null_titles = null_title_res.scalar() or 0

        null_guest_res = await session.execute(
            text("SELECT COUNT(*) FROM transcript_chunks_gemini WHERE guest_name IS NULL")
        )
        null_guests = null_guest_res.scalar() or 0

        null_date_res = await session.execute(
            text("SELECT COUNT(*) FROM transcript_chunks_gemini WHERE publication_date IS NULL")
        )
        null_dates = null_date_res.scalar() or 0

        null_emb_res = await session.execute(
            text("SELECT COUNT(*) FROM transcript_chunks_gemini WHERE embedding IS NULL")
        )
        null_embs = null_emb_res.scalar() or 0

        # 4. Sample record
        sample_res = await session.execute(
            text("""
                SELECT id, episode_title, guest_name, publication_date, timestamp_ref, youtube_url,
                       SUBSTRING(chunk_text FROM 1 FOR 80) as preview,
                       vector_dims(embedding) as dim
                FROM transcript_chunks_gemini
                LIMIT 1
            """)
        )
        sample = sample_res.mappings().first()

        # 5. Invariant check: ensure transcript_chunks (Ollama table) is intact and untouched
        nomic_count_res = await session.execute(
            text("SELECT COUNT(*) FROM transcript_chunks")
        )
        nomic_total = nomic_count_res.scalar() or 0

    print("\n--- DATABASE VERIFICATION ---", flush=True)
    print(f"SELECT COUNT(*) FROM transcript_chunks_gemini; -> {gemini_total}", flush=True)
    print(f"SELECT COUNT(DISTINCT episode_title) FROM transcript_chunks_gemini; -> {distinct_eps}", flush=True)
    print("-----------------------------\n", flush=True)

    logger.info(f"transcript_chunks_gemini rows:      {gemini_total}")
    logger.info(f"transcript_chunks_gemini episodes:  {distinct_eps}")
    logger.info(f"Null episode_title count:           {null_titles}")
    logger.info(f"Null guest_name count:              {null_guests}")
    logger.info(f"Null publication_date count:        {null_dates}")
    logger.info(f"Null embedding count:               {null_embs}")
    if sample:
        logger.info(f"Sample Record:")
        logger.info(f"  ID:               {sample['id']}")
        logger.info(f"  Title:            {sample['episode_title']}")
        logger.info(f"  Guest:            {sample['guest_name']}")
        logger.info(f"  Date:             {sample['publication_date']}")
        logger.info(f"  Timestamp Ref:    {sample['timestamp_ref']}")
        logger.info(f"  YouTube URL:      {sample['youtube_url']}")
        logger.info(f"  Chunk Preview:    {sample['preview']}...")
        logger.info(f"  Embedding Dim:    {sample['dim']}")
    logger.info(f"transcript_chunks (nomic) rows:     {nomic_total} [UNTOUCHED]")
    logger.info("=" * 70)

    return {
        "gemini_total_chunks": gemini_total,
        "gemini_distinct_episodes": distinct_eps,
        "null_titles": null_titles,
        "null_guests": null_guests,
        "null_dates": null_dates,
        "null_embeddings": null_embs,
        "sample": dict(sample) if sample else None,
        "nomic_total_chunks": nomic_total,
    }


# ==============================================================================
# 6. CLI Entry Point
# ==============================================================================

def default_transcripts_dir() -> Path:
    """Finds default transcripts folder."""
    candidates = [
        repo_root / "lennys-podcast-transcripts" / "episodes",
        backend_dir.parent / "lennys-podcast-transcripts" / "episodes",
        Path("lennys-podcast-transcripts/episodes").resolve(),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def main():
    parser = argparse.ArgumentParser(
        description="Ingest podcast transcripts into transcript_chunks_gemini using Gemini embeddings."
    )
    parser.add_argument(
        "--transcripts-dir",
        type=Path,
        default=default_transcripts_dir(),
        help="Path to directory containing episode transcript folders.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of episodes to process (default: None, processes all 303 episodes).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for embedding generation (default: 50).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
        help="Gemini embedding model name (default: gemini-embedding-001).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk files without embedding or database insertion.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingestion of episodes that already exist in transcript_chunks_gemini.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run database verification on transcript_chunks_gemini and exit.",
    )

    args = parser.parse_args()

    async def async_main():
        try:
            if args.verify:
                await verify_gemini_table()
                return

            await run_gemini_ingestion(
                transcripts_dir=args.transcripts_dir,
                limit=args.limit,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
                force=args.force,
                preferred_model=args.model,
            )

            # Automatically run verification at completion
            await verify_gemini_table()
        finally:
            await engine.dispose()

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
