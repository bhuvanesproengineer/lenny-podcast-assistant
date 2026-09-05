import argparse
import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Set

import yaml
from sqlalchemy import select, delete, func

# Ensure the backend directory is in sys.path so app modules can be imported
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import AsyncSessionLocal, init_db, engine
from app.models.db_models import Episode, TranscriptChunk

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ingest")


def find_episode_transcripts(base_dir: Path) -> List[Tuple[Path, Path]]:
    """
    Recursively scans the provided base directory to locate all episode folders
    that contain a transcript.md file.
    
    Returns a list of tuples: (episode_folder_path, transcript_file_path)
    ordered deterministically by folder name.
    """
    episodes: List[Tuple[Path, Path]] = []
    
    if not base_dir.exists():
        logger.error(f"Base directory does not exist: {base_dir}")
        return episodes

    # Find all transcript.md files recursively
    for transcript_file in sorted(base_dir.rglob("transcript.md")):
        if transcript_file.is_file():
            episode_folder = transcript_file.parent
            episodes.append((episode_folder, transcript_file))

    return episodes


def extract_metadata_and_body(transcript_file: Path) -> Tuple[str, str, str, str]:
    """
    Parses frontmatter and markdown body from transcript.md.
    Uses folder name strictly as the slug.
    
    Returns: (title, slug, transcript_path_str, body_text)
    """
    slug = transcript_file.parent.name
    transcript_path_str = str(transcript_file.resolve())
    content = transcript_file.read_text(encoding="utf-8", errors="ignore")

    # Default fallback title
    title = slug.replace("-", " ").title()
    body_text = content

    # Parse YAML frontmatter if present
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1])
                if isinstance(fm, dict):
                    if fm.get("title"):
                        title = str(fm["title"]).strip()
                    elif fm.get("guest"):
                        title = f"Episode with {fm['guest']}"
            except Exception as e:
                logger.warning(f"Could not parse YAML frontmatter for folder '{slug}': {e}")
            body_text = parts[2]

    # Fallback to first markdown header if title was not in frontmatter
    if not title or title == slug.replace("-", " ").title():
        for line in body_text.splitlines():
            line_stripped = line.strip()
            if line_stripped.startswith("# ") and len(line_stripped) > 2:
                title = line_stripped[2:].strip()
                break

    return title, slug, transcript_path_str, body_text


def chunk_text(text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> List[str]:
    """
    Splits transcript dialogue into semantic chunks of roughly chunk_size characters
    with chunk_overlap character overlap between adjacent chunks.
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

            # Build overlapping section from trailing paragraphs
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

        # If a single paragraph is larger than chunk_size, split by word window
        if para_len > chunk_size:
            words = para.split()
            buf: List[str] = []
            buf_len = 0
            for w in words:
                if buf_len + len(w) + 1 > chunk_size and buf:
                    chunk_str = " ".join(buf).strip()
                    if chunk_str:
                        chunks.append(chunk_str)
                    buf = buf[-25:]  # Retain ~25 words for overlap
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


async def run_ingestion(
    transcripts_dir: Path,
    limit: Optional[int] = None,
    force: bool = False
) -> None:
    """
    Orchestrates the ingestion pipeline:
    1. Discovers all episode folders with transcript.md.
    2. Enforces unique Episode records with folder name as slug.
    3. Correctly maps episode_id to every chunk of that episode.
    4. Handles duplicates safely to prevent duplicate episodes.
    5. Outputs comprehensive progress and final summary metrics.
    """
    start_time = time.time()
    logger.info("=" * 70)
    logger.info("STARTING TRANSCRIPT INGESTION PIPELINE")
    logger.info(f"Target Directory: {transcripts_dir.resolve()}")
    logger.info("=" * 70)

    # 1. Discover all episode folders
    episode_entries = find_episode_transcripts(transcripts_dir)
    total_folders_discovered = len(episode_entries)
    logger.info(f"Discovered {total_folders_discovered} episode folder(s) containing transcript.md")

    if total_folders_discovered == 0:
        logger.error("No episode folders with transcript.md found. Ingestion halted.")
        return

    # Apply limit if specified
    if limit and limit > 0:
        episode_entries = episode_entries[:limit]
        logger.info(f"Applying execution limit: processing first {len(episode_entries)} episode(s)")

    # Ensure database schema is ready
    await init_db()

    # Track metrics
    total_episodes_inserted = 0
    total_chunks_inserted = 0
    skipped_files: List[Tuple[str, str]] = []
    failures: List[Tuple[str, str]] = []

    async with AsyncSessionLocal() as session:
        # Load existing episode slugs for fast duplicate protection
        stmt = select(Episode.slug)
        existing_result = await session.execute(stmt)
        existing_slugs: Set[str] = set(existing_result.scalars().all())
        logger.info(f"Currently existing episodes in database: {len(existing_slugs)}")

        for index, (folder_path, transcript_path) in enumerate(episode_entries, start=1):
            slug = folder_path.name

            try:
                # Duplicate protection check
                if slug in existing_slugs and not force:
                    reason = "Episode already exists in database (slug duplicate protection)"
                    skipped_files.append((slug, reason))
                    logger.info(f"[{index}/{len(episode_entries)}] SKIPPED: '{slug}' -> {reason}")
                    continue

                # If force re-ingesting an existing episode, remove old record and its cascading chunks
                if slug in existing_slugs and force:
                    logger.info(f"[{index}/{len(episode_entries)}] FORCE RE-INGEST: Removing existing '{slug}'...")
                    await session.execute(delete(Episode).where(Episode.slug == slug))
                    await session.flush()
                    existing_slugs.discard(slug)

                # Extract content
                title, extracted_slug, file_path_str, body_text = extract_metadata_and_body(transcript_path)

                # Validate slug matches folder name
                assert extracted_slug == slug, f"Extracted slug '{extracted_slug}' does not match folder '{slug}'"

                # 2. Create distinct Episode record
                episode_record = Episode(
                    title=title,
                    slug=slug,
                    transcript_path=file_path_str
                )
                session.add(episode_record)
                await session.flush()  # Ensures episode_record.id is populated

                # Verify episode_record.id is allocated
                current_episode_id = episode_record.id
                if not current_episode_id:
                    raise RuntimeError(f"Failed to obtain generated ID for Episode '{slug}'")

                # 3. Generate dialogue chunks
                chunks = chunk_text(body_text)
                
                # 4. Create TranscriptChunk records explicitly mapped to this episode's ID
                chunk_records = [
                    TranscriptChunk(
                        episode_id=current_episode_id,  # Strictly mapped to this episode
                        chunk_index=chunk_idx,
                        content=chunk_content,
                        embedding=None  # Explicitly None per requirements
                    )
                    for chunk_idx, chunk_content in enumerate(chunks)
                ]

                if chunk_records:
                    session.add_all(chunk_records)

                # Commit transaction for this episode
                await session.commit()
                existing_slugs.add(slug)

                total_episodes_inserted += 1
                total_chunks_inserted += len(chunk_records)

                logger.info(
                    f"[{index}/{len(episode_entries)}] INSERTED: Episode ID {current_episode_id} | "
                    f"'{title[:45]}...' ({slug}) -> {len(chunk_records)} chunks"
                )

            except Exception as err:
                await session.rollback()
                logger.error(f"[{index}/{len(episode_entries)}] FAILED on '{slug}': {err}", exc_info=True)
                failures.append((slug, str(err)))

    elapsed = time.time() - start_time

    # 8. Final Ingestion Summary
    logger.info("\n" + "=" * 70)
    logger.info("FINAL INGESTION SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total episode folders discovered : {total_folders_discovered}")
    logger.info(f"Total episode folders processed  : {len(episode_entries)}")
    logger.info(f"Total episodes inserted          : {total_episodes_inserted}")
    logger.info(f"Total transcript chunks inserted : {total_chunks_inserted}")
    logger.info(f"Total skipped files              : {len(skipped_files)}")
    logger.info(f"Total failures                   : {len(failures)}")
    logger.info(f"Elapsed Time                     : {elapsed:.2f}s")
    logger.info("=" * 70)

    if skipped_files and len(skipped_files) <= 10:
        logger.info("Skipped Files Details:")
        for s_slug, s_reason in skipped_files:
            logger.info(f"  - {s_slug}: {s_reason}")
    elif skipped_files:
        logger.info(f"Skipped {len(skipped_files)} files due to duplicate protection (already in database).")

    if failures:
        logger.error("Failures Details:")
        for f_slug, f_err in failures:
            logger.error(f"  - {f_slug}: {f_err}")


def main():
    parser = argparse.ArgumentParser(description="Ingest Lenny's podcast transcripts into PostgreSQL.")
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        help="Path to lennys-podcast-transcripts directory (defaults to auto-detecting)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on the number of transcripts to ingest."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingestion and replacement of existing episodes."
    )

    args = parser.parse_args()

    # Determine transcripts directory
    if args.dir:
        transcripts_path = Path(args.dir)
    else:
        root_repo = Path(__file__).resolve().parent.parent.parent
        transcripts_path = root_repo / "lennys-podcast-transcripts" / "episodes"
        if not transcripts_path.exists():
            transcripts_path = root_repo / "lennys-podcast-transcripts"

    asyncio.run(run_ingestion(
        transcripts_dir=transcripts_path,
        limit=args.limit,
        force=args.force
    ))


if __name__ == "__main__":
    main()
