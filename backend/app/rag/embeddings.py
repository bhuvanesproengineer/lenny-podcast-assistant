import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

import httpx
from sqlalchemy import select, func

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.database import AsyncSessionLocal, init_db
from app.models.db_models import TranscriptChunk

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("embeddings")


class EmbeddingGenerator:
    """
    Handles communication with Ollama's embedding API with persistent connection pooling
    and exponential backoff retry logic.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.EMBEDDING_MODEL
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

    async def get_client(self) -> httpx.AsyncClient:
        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if (
            self._client is None
            or self._client.is_closed
            or self._client_loop is not curr_loop
        ):
            if self._client and not self._client.is_closed:
                try:
                    await self._client.aclose()
                except Exception:
                    pass
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
            self._client_loop = curr_loop
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_embeddings(
        self,
        texts: List[str],
        max_retries: int = 3,
        backoff_factor: float = 2.0
    ) -> List[List[float]]:
        """
        Generates dense vector embeddings for a list of text strings with exponential backoff.
        """
        if not texts:
            return []

        url = f"{self.base_url}/api/embed"
        payload = {
            "model": self.model,
            "input": texts
        }

        client = await self.get_client()
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                embeddings = data.get("embeddings", [])
                if len(embeddings) != len(texts):
                    raise ValueError(
                        f"Expected {len(texts)} embeddings, received {len(embeddings)}"
                    )
                return embeddings

            except Exception as exc:
                last_error = exc
                wait_time = backoff_factor ** attempt
                logger.warning(
                    f"Embedding request attempt {attempt}/{max_retries} failed: {exc}. "
                    f"Retrying in {wait_time:.1f}s..."
                )
                if attempt < max_retries:
                    await asyncio.sleep(wait_time)
                else:
                    # Recreate client on final failure in case connection was dropped
                    await self.close()

        logger.error(f"Failed to generate embeddings after {max_retries} attempts: {last_error}")
        raise RuntimeError(f"Embedding generation failed: {last_error}") from last_error

    async def get_single_embedding(self, text: str) -> List[float]:
        results = await self.get_embeddings([text])
        if not results:
            raise ValueError("No embedding returned")
        return results[0]


async def run_embedding_pipeline(
    batch_size: int = 100,
    limit: Optional[int] = None,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Scans for TranscriptChunk records without embeddings, generates embeddings in batches,
    and commits them to the pgvector column.
    
    Safe to interrupt and resume:
    - Queries WHERE embedding IS NULL
    - Commits after every batch
    - Detailed metrics logging on every iteration
    """
    start_time = time.time()
    generator = EmbeddingGenerator()

    logger.info("=" * 70)
    logger.info("STARTING EMBEDDING GENERATION PIPELINE")
    logger.info(f"Model Endpoint : {generator.base_url}/api/embed")
    logger.info(f"Model Name     : {generator.model}")
    logger.info(f"Batch Size     : {batch_size}")
    if limit:
        logger.info(f"Process Limit  : {limit} chunks")
    logger.info("=" * 70)

    await init_db()

    async with AsyncSessionLocal() as session:
        # 1. Total chunk count across table
        total_chunks_stmt = select(func.count(TranscriptChunk.id))
        total_chunks = (await session.execute(total_chunks_stmt)).scalar() or 0

        # 2. Count already embedded chunks (skipped)
        already_embedded_stmt = select(func.count(TranscriptChunk.id)).where(
            TranscriptChunk.embedding.is_not(None)
        )
        total_skipped = (await session.execute(already_embedded_stmt)).scalar() or 0

        # 3. Count pending chunks
        pending_stmt = select(func.count(TranscriptChunk.id)).where(
            TranscriptChunk.embedding.is_(None)
        )
        total_pending = (await session.execute(pending_stmt)).scalar() or 0

        logger.info(f"Total Chunks in Database        : {total_chunks}")
        logger.info(f"Already Embedded (to skip)     : {total_skipped}")
        logger.info(f"Pending Chunks to Process       : {total_pending}")

        if total_pending == 0:
            logger.info("All transcript chunks already have embeddings. Nothing to process.")
            await generator.close()
            return {
                "total_chunks": total_chunks,
                "embeddings_generated": 0,
                "total_skipped": total_skipped,
                "total_failures": 0,
                "elapsed": 0.0
            }

        target_to_process = min(total_pending, limit) if limit else total_pending
        total_processed = 0
        total_failed = 0
        batch_num = 0
        last_id = 0

        while total_processed + total_failed < target_to_process:
            batch_num += 1
            current_batch_limit = min(
                batch_size,
                target_to_process - (total_processed + total_failed)
            )

            # Cursor-based pagination using primary key index for fast retrieval
            chunk_query = (
                select(TranscriptChunk)
                .where(TranscriptChunk.embedding.is_(None))
                .where(TranscriptChunk.id > last_id)
                .order_by(TranscriptChunk.id)
                .limit(current_batch_limit)
            )
            chunks = (await session.execute(chunk_query)).scalars().all()

            # If no more chunks found with id > last_id, reset last_id to pick up any skipped
            if not chunks:
                if last_id > 0:
                    last_id = 0
                    continue
                else:
                    break

            last_id = chunks[-1].id
            texts = [c.content for c in chunks]
            batch_start = time.time()

            try:
                # Generate embeddings for the batch
                embeddings = await generator.get_embeddings(texts, max_retries=max_retries)

                # Assign embeddings
                for chunk, emb in zip(chunks, embeddings):
                    chunk.embedding = emb

                # Commit batch immediately to guarantee safe resumption on interrupt
                await session.commit()

                total_processed += len(chunks)
                remaining_chunks = target_to_process - (total_processed + total_failed)
                batch_duration = time.time() - batch_start
                rate = len(chunks) / batch_duration if batch_duration > 0 else 0.0

                # Detailed required progress logging
                logger.info(
                    f"[Batch {batch_num}] Processed {len(chunks)} chunks | "
                    f"Total Chunks: {total_chunks} | "
                    f"Processed: {total_processed} | "
                    f"Remaining: {remaining_chunks} | "
                    f"Failed: {total_failed} | "
                    f"Rate: {rate:.1f} chunks/s ({batch_duration:.2f}s)"
                )

            except Exception as exc:
                await session.rollback()
                total_failed += len(chunks)
                remaining_chunks = target_to_process - (total_processed + total_failed)
                logger.error(
                    f"[Batch {batch_num}] FAILED on {len(chunks)} chunks after {max_retries} retries: {exc}. "
                    f"Rolling back and continuing next batch.",
                    exc_info=True
                )

    await generator.close()
    elapsed = time.time() - start_time

    # 8. Completion Summary Report
    logger.info("\n" + "=" * 70)
    logger.info("EMBEDDING PIPELINE COMPLETION SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total Chunks in Database         : {total_chunks}")
    logger.info(f"Total Embeddings Generated       : {total_processed}")
    logger.info(f"Total Chunks Skipped (Existed)   : {total_skipped}")
    logger.info(f"Total Failures                   : {total_failed}")
    logger.info(f"Elapsed Time                     : {elapsed:.2f}s")
    logger.info("=" * 70)

    return {
        "total_chunks": total_chunks,
        "embeddings_generated": total_processed,
        "total_skipped": total_skipped,
        "total_failures": total_failed,
        "elapsed": elapsed
    }


def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for transcript chunks.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of chunks per batch (default: 100)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on total chunks to process."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Embedding model name (defaults to settings.EMBEDDING_MODEL)."
    )

    args = parser.parse_args()

    if args.model:
        settings.EMBEDDING_MODEL = args.model

    asyncio.run(run_embedding_pipeline(
        batch_size=args.batch_size,
        limit=args.limit
    ))


if __name__ == "__main__":
    main()
