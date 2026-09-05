import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.database import AsyncSessionLocal, init_db
from app.models.db_models import Episode, TranscriptChunk
from app.rag.embeddings import EmbeddingGenerator
from app.providers.base import BaseLLMProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.provider_factory import get_provider

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("rag_service")


@dataclass
class RetrievalResult:
    """
    Encapsulates a retrieved transcript chunk with its cosine similarity score
    and linked episode metadata.
    """
    chunk_id: int
    content: str
    chunk_index: int
    similarity_score: float
    distance: float
    episode_id: int
    episode_title: str
    episode_slug: str
    transcript_path: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RAGResponse:
    """
    Encapsulates the final synthesized answer from the RAG service,
    including the original question, grounding sources, and retrieved excerpts.
    """
    question: str
    answer: str
    sources: List[str]
    retrieved_chunks: List[RetrievalResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "sources": self.sources,
            "retrieved_chunks": [c.to_dict() for c in self.retrieved_chunks]
        }


def is_boilerplate(content: str) -> bool:
    """Detects empty markdown title headers and outro promo boilerplate."""
    c = content.strip()
    if c.startswith("#") and "## Transcript" in c and len(c) < 350:
        return True
    if "your favorite podcast app" in c.lower() and len(c) < 450:
        return True
    return False


_cached_episodes: Optional[List[Dict[str, Any]]] = None


async def get_all_episodes_cached() -> List[Dict[str, Any]]:
    """Loads and caches all episodes for fast speaker/guest name matching."""
    global _cached_episodes
    if _cached_episodes is not None:
        return _cached_episodes
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Episode.id, Episode.title, Episode.slug))
            rows = res.all()
            _cached_episodes = [{"id": r[0], "title": r[1], "slug": r[2]} for r in rows]
    except Exception as exc:
        logger.debug("Could not load episode cache: %s", exc)
        return []
    return _cached_episodes or []


def find_matching_episode_ids(query: str, episodes: List[Dict[str, Any]]) -> List[int]:
    """Identifies episode IDs matching guest/speaker names in the query."""
    if not episodes or not query:
        return []
    q_lower = query.lower()
    matched_ids = []
    for ep in episodes:
        slug = ep.get("slug", "")
        if not slug:
            continue
        slug_clean = slug.replace("-", " ")
        parts = [p for p in slug.split("-") if len(p) > 2]
        # Check if full guest name or all name parts appear in query
        if slug_clean in q_lower or (len(parts) >= 2 and all(p in q_lower for p in parts)):
            matched_ids.append(ep["id"])
    return matched_ids


class Retriever:
    """
    Performs semantic vector search over TranscriptChunk records in PostgreSQL
    using pgvector cosine similarity with speaker-name awareness and boilerplate filtering.
    """

    def __init__(
        self,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        default_top_k: Optional[int] = None
    ):
        self.embedding_generator = embedding_generator or EmbeddingGenerator()
        self.default_top_k = default_top_k or getattr(settings, "SIMILARITY_TOP_K", 6)

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> List[RetrievalResult]:
        """
        Generates an embedding for the query and retrieves the top-K most similar
        substantive transcript chunks along with their episode metadata.
        """
        start_time = time.time()
        k = top_k or self.default_top_k
        query_stripped = query.strip()

        if not query_stripped:
            logger.warning("Empty search query provided to retriever.")
            return []

        logger.info(f"Retrieving top {k} chunks for query: '{query_stripped[:80]}...'")

        # 1. Generate query embedding
        try:
            t0_emb = time.time()
            query_vector = await self.embedding_generator.get_single_embedding(query_stripped)
            emb_duration = time.time() - t0_emb
            logger.debug(
                f"Generated query embedding vector (dim={len(query_vector)}) in {emb_duration:.3f}s"
            )
        except Exception as exc:
            logger.error(f"Failed to generate query embedding: {exc}", exc_info=True)
            raise RuntimeError(f"Query embedding generation failed: {exc}") from exc

        # 2. Check for speaker/guest name matches in episode metadata
        matched_ep_ids: List[int] = []
        try:
            episodes = await get_all_episodes_cached()
            matched_ep_ids = find_matching_episode_ids(query_stripped, episodes)
            if matched_ep_ids:
                logger.info("Speaker/guest matched in query: %s -> Episode IDs %s", query_stripped[:60], matched_ep_ids)
        except Exception as exc:
            logger.debug("Failed checking speaker matches: %s", exc)

        # 3. Search pgvector using cosine distance with joined Episode metadata
        async def _execute_search(db_session: AsyncSession) -> List[RetrievalResult]:
            from sqlalchemy import case
            t0_sql = time.time()
            dist_expr = TranscriptChunk.embedding.cosine_distance(query_vector)

            # Apply distance boost to chunks from episodes matching the speaker in the query
            if matched_ep_ids:
                effective_dist = case(
                    (TranscriptChunk.episode_id.in_(matched_ep_ids), dist_expr * 0.85),
                    else_=dist_expr
                ).label("distance")
            else:
                effective_dist = dist_expr.label("distance")

            # Fetch extra candidates to account for post-filtering of empty header chunks
            fetch_k = max(k * 2, 12)
            stmt = (
                select(TranscriptChunk, Episode, effective_dist)
                .join(Episode, TranscriptChunk.episode_id == Episode.id)
                .where(TranscriptChunk.embedding.is_not(None))
                .order_by(effective_dist)
                .limit(fetch_k)
            )

            result = await db_session.execute(stmt)
            rows = result.all()
            sql_duration = time.time() - t0_sql

            retrieved_items: List[RetrievalResult] = []
            for chunk, episode, dist in rows:
                content = chunk.content or ""
                if is_boilerplate(content):
                    continue

                dist_val = float(dist) if dist is not None else 1.0
                similarity = round(max(0.0, 1.0 - dist_val), 4)

                retrieved_items.append(
                    RetrievalResult(
                        chunk_id=chunk.id,
                        content=content,
                        chunk_index=chunk.chunk_index,
                        similarity_score=similarity,
                        distance=round(dist_val, 4),
                        episode_id=episode.id,
                        episode_title=episode.title,
                        episode_slug=episode.slug,
                        transcript_path=episode.transcript_path
                    )
                )
                if len(retrieved_items) >= k:
                    break

            total_duration = time.time() - start_time
            chunk_titles = [f"{c.episode_title} (chunk {c.chunk_index})" for c in retrieved_items]
            scores = [c.similarity_score for c in retrieved_items]
            logger.info(
                "Retriever Query: '%s' | Chunks: %d (SQL: %.3fs, Total: %.3fs)\n"
                "  Retrieved chunk titles: %s\n"
                "  Similarity scores: %s",
                query_stripped, len(retrieved_items), sql_duration, total_duration,
                chunk_titles, scores
            )
            return retrieved_items

        try:
            if session is not None:
                return await _execute_search(session)
            else:
                async with AsyncSessionLocal() as session_ctx:
                    return await _execute_search(session_ctx)

        except Exception as exc:
            logger.error(f"Database query failed during vector retrieval: {exc}", exc_info=True)
            raise RuntimeError(f"Vector search retrieval failed: {exc}") from exc


class RAGService:
    """
    Orchestration layer coordinating retrieval and grounded LLM generation.
    """

    SYSTEM_PROMPT = (
        "You are Lenny Growth Assistant, an AI expert trained exclusively on Lenny's Podcast transcripts.\n"
        "Your task is to answer user questions concisely, accurately, and authoritatively using ONLY the provided transcript excerpts.\n\n"
        "Strict Guidelines:\n"
        "1. Ground your answer strictly and exclusively in the provided transcript excerpts.\n"
        "2. Do not hallucinate, speculate, or introduce external knowledge not explicitly backed by the excerpts.\n"
        "3. If the excerpts do not provide enough context to answer the question, clearly state: "
        "\"Based on the available podcast transcripts, there is not enough information to answer this question.\"\n"
        "4. Be concise, direct, and actionable in your response."
    )

    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        llm_provider: Optional[BaseLLMProvider] = None
    ):
        self.retriever = retriever or Retriever()
        self._custom_llm_provider = llm_provider

    @property
    def llm_provider(self) -> BaseLLMProvider:
        if self._custom_llm_provider is not None:
            return self._custom_llm_provider
        return get_provider()

    @llm_provider.setter
    def llm_provider(self, val: Optional[BaseLLMProvider]) -> None:
        self._custom_llm_provider = val

    def build_context(self, chunks: List[RetrievalResult]) -> str:
        """
        Formats retrieved transcript chunks into a structured context block.
        """
        if not chunks:
            return ""

        context_blocks = []
        for i, chunk in enumerate(chunks, start=1):
            block = (
                f"[Excerpt {i}] (From Episode: \"{chunk.episode_title}\")\n"
                f"{chunk.content.strip()}"
            )
            context_blocks.append(block)

        return "\n\n".join(context_blocks)

    async def answer(
        self,
        question: str,
        top_k: int = 6,
        session: Optional[AsyncSession] = None
    ) -> RAGResponse:
        """
        End-to-end RAG workflow:
        1. Validates user question.
        2. Retrieves top-K transcript chunks via pgvector.
        3. Builds grounded context prompt.
        4. Invokes the configured LLM.
        5. Extracts unique source episode titles.
        6. Returns RAGResponse.
        """
        start_time = time.time()
        question_stripped = question.strip()

        if not question_stripped:
            return RAGResponse(
                question=question,
                answer="Please provide a valid question.",
                sources=[],
                retrieved_chunks=[]
            )

        logger.info(f"Processing RAG question: '{question_stripped[:60]}...'")

        # 1. Fetch relevant chunks from retriever
        try:
            chunks = await self.retriever.retrieve(
                query=question_stripped,
                top_k=top_k,
                session=session
            )
        except Exception as exc:
            logger.error(f"RAG retrieval phase failed: {exc}", exc_info=True)
            raise RuntimeError(f"RAG retrieval failed: {exc}") from exc

        # Handle empty retrieval
        if not chunks:
            logger.warning(f"No relevant excerpts found for question: '{question_stripped}'")
            return RAGResponse(
                question=question_stripped,
                answer="No relevant podcast transcripts were found matching your question.",
                sources=[],
                retrieved_chunks=[]
            )

        # 2. Build structured context
        context_str = self.build_context(chunks)
        logger.info(
            f"Built RAG context: {len(context_str)} characters ({len(context_str.split())} words) from {len(chunks)} chunks"
        )

        # 3. Formulate grounded prompt
        prompt = (
            f"Transcript Excerpts:\n"
            f"{context_str}\n\n"
            f"User Question: {question_stripped}\n\n"
            f"Concise Answer (based solely on the excerpts above):"
        )

        # 4. Generate completion from configured LLM (with local fallback if cloud fails)
        try:
            t0_gen = time.time()
            # Support both common interface generate_response and backward-compatible generate
            gen_fn = getattr(self.llm_provider, "generate_response", None)
            if gen_fn is None or not (asyncio.iscoroutinefunction(gen_fn) or hasattr(gen_fn, "assert_awaited") or hasattr(gen_fn, "__await__")):
                gen_fn = getattr(self.llm_provider, "generate")

            raw_answer = await gen_fn(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.2
            )
            gen_duration = time.time() - t0_gen
            logger.info(f"LLM generated answer in {gen_duration:.2f}s ({len(raw_answer)} chars)")
        except Exception as exc:
            if getattr(settings, "FALLBACK_TO_LOCAL", True) and not self.llm_provider.is_local:
                logger.warning("Cloud generation failed: %s. Falling back to local Ollama...", exc)
                try:
                    fallback_prov = OllamaProvider()
                    raw_answer = await fallback_prov.generate_response(
                        prompt=prompt,
                        system_prompt=self.SYSTEM_PROMPT,
                        temperature=0.2
                    )
                except Exception as fallback_exc:
                    logger.error("Local fallback also failed: %s", fallback_exc, exc_info=True)
                    raise RuntimeError(f"Both Cloud and Local generation failed: {fallback_exc}") from fallback_exc
            else:
                logger.error(f"LLM generation phase failed: {exc}", exc_info=True)
                raise RuntimeError(f"LLM generation failed: {exc}") from exc

        # 5. Extract unique source episode titles in order of appearance
        unique_sources: List[str] = list(dict.fromkeys([c.episode_title for c in chunks]))

        elapsed = time.time() - start_time
        logger.info(
            f"Completed RAG response in {elapsed:.2f}s | Sources: {len(unique_sources)} episodes"
        )

        return RAGResponse(
            question=question_stripped,
            answer=raw_answer,
            sources=unique_sources,
            retrieved_chunks=chunks
        )


async def retrieve_relevant_chunks(
    query: str,
    top_k: int = 5,
    session: Optional[AsyncSession] = None
) -> List[RetrievalResult]:
    """
    Convenience function for semantic vector search over Lenny's podcast transcripts.
    """
    retriever = Retriever(default_top_k=top_k)
    return await retriever.retrieve(query=query, top_k=top_k, session=session)


async def answer_question(
    question: str,
    top_k: int = 5,
    session: Optional[AsyncSession] = None
) -> RAGResponse:
    """
    Convenience function for the complete RAG pipeline.
    """
    service = RAGService()
    return await service.answer(question=question, top_k=top_k, session=session)


def main():
    parser = argparse.ArgumentParser(description="Lenny Growth Assistant RAG Service.")
    parser.add_argument("question", type=str, help="User question to answer.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve (default: 5).")

    args = parser.parse_args()

    async def run():
        response = await answer_question(question=args.question, top_k=args.top_k)
        print("\n" + "=" * 75)
        print(f"QUESTION: {response.question}")
        print("=" * 75)
        print(f"\nANSWER:\n{response.answer}\n")
        print("=" * 75)
        print("SOURCE EPISODES:")
        for idx, src in enumerate(response.sources, start=1):
            print(f"  [{idx}] {src}")
        print("=" * 75)

    asyncio.run(run())


if __name__ == "__main__":
    main()
