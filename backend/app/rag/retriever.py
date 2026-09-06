import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
import re
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.database import AsyncSessionLocal, init_db
from app.models.db_models import Episode, TranscriptChunk, TranscriptChunkGemini
from app.rag.embeddings import EmbeddingGenerator
from app.rag.embedding_router import (
    get_embedding_generator,
    get_active_embedding_provider,
    get_embedding_info,
)
from app.providers.base import BaseLLMProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.provider_factory import get_provider, get_active_provider_name

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("rag_service")

# Standard refusal message when transcript evidence is missing or insufficient (Requirements 3 & 6)
INSUFFICIENT_EVIDENCE_MESSAGE = (
    "Not enough transcript evidence available to answer this question confidently based on the indexed Lenny Podcast episodes."
)


def extract_timestamp(content: str) -> Optional[str]:
    """Extracts timestamp like [00:12:34] or 12:34 from chunk text if available."""
    if not content:
        return None
    match = re.search(r"\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?", content)
    if match:
        return match.group(1)
    return None


def parse_source_reference(title: str) -> Tuple[str, str]:
    """Extracts (clean_episode_title, guest_name) from episode title."""
    if not title:
        return "Lenny's Podcast Episode", "Lenny's Podcast Guest"
    if "|" in title:
        parts = title.split("|", 1)
        ep_title = parts[0].strip()
        speaker_part = parts[1].strip()
        speaker_match = re.match(r"^([^(]+)", speaker_part)
        speaker = speaker_match.group(1).strip() if speaker_match else speaker_part
        return ep_title, speaker
    return title.strip(), "Lenny's Podcast Guest"


def format_rag_sources_section(chunks: List["RetrievalResult"]) -> Tuple[str, List[str]]:
    """
    Formats the ## Sources block according to Requirement 4:
    ## Sources

    Episode: <episode title>
    Guest: <guest name>
    Timestamp: <timestamp if available>
    """
    if not chunks:
        return "## Sources\n\nEpisode: N/A\nGuest: N/A\nTimestamp: N/A", []

    entries = []
    seen = set()
    source_titles = []

    for c in chunks:
        title = c.episode_title or "Lenny's Podcast Episode"
        source_titles.append(title)
        clean_title, guest = parse_source_reference(title)
        ts = extract_timestamp(c.content) or "N/A"
        key = (clean_title, guest)
        if key in seen:
            continue
        seen.add(key)
        entry = f"Episode: {clean_title}\nGuest: {guest}\nTimestamp: {ts}"
        entries.append(entry)

    sources_block = "## Sources\n\n" + "\n\n".join(entries)
    unique_titles = list(dict.fromkeys(source_titles))
    return sources_block, unique_titles


def enforce_rag_response_format(raw_answer: str, chunks: List["RetrievalResult"]) -> Tuple[str, List[str]]:
    """
    Guarantees every answer conforms to the assignment required structure:
    ## Answer
    [Grounded explanation with citation markers]

    ## Key Insights
    - Insight 1
    - Insight 2
    - Insight 3

    ## Sources
    Episode: ...
    Guest: ...
    Timestamp: ...
    """
    clean = raw_answer.strip()

    # Check if the model explicitly refused or indicated lack of evidence
    if "not enough transcript evidence" in clean.lower():
        return INSUFFICIENT_EVIDENCE_MESSAGE, []

    sources_block, unique_sources = format_rag_sources_section(chunks)

    # Check if the model output already has ## Answer and ## Key Insights
    has_answer_hdr = bool(re.search(r"^##\s+Answer", clean, re.MULTILINE))
    has_insights_hdr = bool(re.search(r"^##\s+Key Insights", clean, re.MULTILINE))

    if has_answer_hdr and has_insights_hdr:
        # Strip out any existing ## Sources block and replace with the canonical formatted sources block
        cleaned_body = re.split(r"^##\s+Sources", clean, flags=re.MULTILINE)[0].strip()
        final_answer = f"{cleaned_body}\n\n{sources_block}"
        return final_answer, unique_sources

    # If headers are missing, structure the content
    lines = clean.splitlines()
    bullets = [line.strip() for line in lines if line.strip().startswith(("-", "*"))]
    non_bullets = [line for line in lines if not line.strip().startswith(("-", "*", "#"))]
    body_text = "\n".join(non_bullets).strip()
    if not body_text:
        body_text = clean

    # Ensure inline citation marker exists if missing
    if "[Source:" not in body_text and chunks:
        first_chunk = chunks[0]
        _, g = parse_source_reference(first_chunk.episode_title)
        body_text = f"{body_text} [Source: {g}, {first_chunk.episode_title}]"

    # Ensure key insights exist
    if bullets:
        insights_text = "\n".join(bullets[:4])
    else:
        # Generate clean key insights from retrieved chunks
        insights_list = []
        for c in chunks[:3]:
            _, g = parse_source_reference(c.episode_title)
            snippet = c.content.strip().replace("\n", " ")
            if len(snippet) > 100:
                snippet = snippet[:97] + "..."
            insights_list.append(f"- {g}: \"{snippet}\"")
        insights_text = "\n".join(insights_list)

    final_answer = (
        f"## Answer\n\n"
        f"{body_text}\n\n"
        f"## Key Insights\n\n"
        f"{insights_text}\n\n"
        f"{sources_block}"
    )
    return final_answer, unique_sources


@dataclass
class RetrievalResult:
    """
    Encapsulates a retrieved transcript chunk with its cosine similarity score
    and linked episode metadata.
    """
    chunk_id: Any
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
    Performs semantic vector search over TranscriptChunk (Ollama) or
    TranscriptChunkGemini (Cloud) records in PostgreSQL using pgvector cosine similarity.
    """

    def __init__(
        self,
        embedding_generator: Optional[Any] = None,
        default_top_k: Optional[int] = None
    ):
        self._custom_embedding_generator = embedding_generator
        self.default_top_k = default_top_k or getattr(settings, "SIMILARITY_TOP_K", 6)

    @property
    def embedding_generator(self) -> Any:
        if self._custom_embedding_generator is not None:
            return self._custom_embedding_generator
        return get_embedding_generator()

    @embedding_generator.setter
    def embedding_generator(self, val: Any) -> None:
        self._custom_embedding_generator = val

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

        # Resolve diagnostics for verification logging
        llm_provider = get_active_provider_name()
        try:
            prov_inst = get_provider(llm_provider, fallback_on_error=False)
            chat_model = getattr(prov_inst, "model_name", getattr(prov_inst, "model", "unknown"))
        except Exception:
            chat_model = getattr(settings, "GROQ_MODEL", "openai/gpt-oss-20b") if llm_provider in ("cloud", "groq") else getattr(settings, "OLLAMA_DEFAULT_MODEL", "llama3.2:3b")

        emb_info = get_embedding_info()
        if (
            self._custom_embedding_generator is not None
            and hasattr(self._custom_embedding_generator, "provider")
            and isinstance(self._custom_embedding_generator.provider, str)
        ):
            embedding_provider = self._custom_embedding_generator.provider
        else:
            embedding_provider = emb_info["provider"]
        vector_table = "transcript_chunks_gemini" if embedding_provider == "gemini" else "transcript_chunks"
        embedding_model = emb_info["model"]

        # Requirement 5: Print selection diagnostics
        print(
            f"Selected LLM Provider: {llm_provider}\n"
            f"Selected Embedding Provider: {embedding_provider}\n"
            f"Selected Vector Table: {vector_table}\n"
            f"Selected Chat Model: {chat_model}\n"
            f"Selected Embedding Model: {embedding_model}",
            flush=True
        )

        logger.info(
            "Selected LLM Provider: %s\n"
            "Selected Embedding Provider: %s\n"
            "Selected Vector Table: %s\n"
            "Selected Chat Model: %s\n"
            "Selected Embedding Model: %s",
            llm_provider,
            embedding_provider,
            vector_table,
            chat_model,
            embedding_model,
        )

        logger.info(f"Retrieving top {k} chunks for query: '{query_stripped[:80]}...'")

        # 1. Generate query embedding using the routed embedding generator
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

        # 3. Search pgvector using cosine distance routed by active embedding provider
        async def _execute_search(db_session: AsyncSession) -> List[RetrievalResult]:
            t0_sql = time.time()
            retrieved_items: List[RetrievalResult] = []

            if embedding_provider == "gemini":
                dist_expr = TranscriptChunkGemini.embedding.cosine_distance(query_vector).label("distance")
                fetch_k = max(k * 2, 12)
                stmt = (
                    select(TranscriptChunkGemini, dist_expr)
                    .where(TranscriptChunkGemini.embedding.is_not(None))
                    .order_by(dist_expr)
                    .limit(fetch_k)
                )
                result = await db_session.execute(stmt)
                rows = result.all()
                for row in rows:
                    if len(row) == 2:
                        chunk, dist = row
                    else:
                        chunk, _, dist = row
                    content = getattr(chunk, "chunk_text", getattr(chunk, "content", "")) or ""
                    if is_boilerplate(content):
                        continue

                    dist_val = float(dist) if dist is not None else 1.0
                    similarity = round(max(0.0, 1.0 - dist_val), 4)

                    retrieved_items.append(
                        RetrievalResult(
                            chunk_id=chunk.id,
                            content=content,
                            chunk_index=0,
                            similarity_score=similarity,
                            distance=round(dist_val, 4),
                            episode_id=0,
                            episode_title=getattr(chunk, "episode_title", None) or getattr(chunk, "guest_name", None) or "Lenny's Podcast Episode",
                            episode_slug="",
                            transcript_path=getattr(chunk, "youtube_url", "") or ""
                        )
                    )
                    if len(retrieved_items) >= k:
                        break
            else:
                # Local Ollama flow: transcript_chunks joined with Episode
                from sqlalchemy import case
                dist_expr = TranscriptChunk.embedding.cosine_distance(query_vector)

                # Apply distance boost to chunks from episodes matching the speaker in the query
                if matched_ep_ids:
                    effective_dist = case(
                        (TranscriptChunk.episode_id.in_(matched_ep_ids), dist_expr * 0.85),
                        else_=dist_expr
                    ).label("distance")
                else:
                    effective_dist = dist_expr.label("distance")

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

                for row in rows:
                    if len(row) == 2:
                        chunk, dist = row
                        episode = getattr(chunk, "episode", None)
                    else:
                        chunk, episode, dist = row
                    content = getattr(chunk, "content", getattr(chunk, "chunk_text", "")) or ""
                    if is_boilerplate(content):
                        continue

                    dist_val = float(dist) if dist is not None else 1.0
                    similarity = round(max(0.0, 1.0 - dist_val), 4)

                    ep_id = getattr(episode, "id", 0) if episode else getattr(chunk, "episode_id", 0)
                    ep_title = getattr(episode, "title", "") if episode else getattr(chunk, "episode_title", "Lenny's Podcast Episode")
                    ep_slug = getattr(episode, "slug", "") if episode else ""
                    ep_path = getattr(episode, "transcript_path", "") if episode else ""

                    retrieved_items.append(
                        RetrievalResult(
                            chunk_id=chunk.id,
                            content=content,
                            chunk_index=getattr(chunk, "chunk_index", 0),
                            similarity_score=similarity,
                            distance=round(dist_val, 4),
                            episode_id=ep_id,
                            episode_title=ep_title,
                            episode_slug=ep_slug,
                            transcript_path=ep_path
                        )
                    )
                    if len(retrieved_items) >= k:
                        break

            sql_duration = time.time() - t0_sql
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
        "You are the Lenny Podcast Growth Assistant.\n\n"
        "Rules:\n"
        "- Use ONLY the provided transcript context.\n"
        "- Do NOT use outside knowledge.\n"
        "- Do NOT invent facts.\n"
        "- Do NOT provide generic industry advice.\n"
        "- Do NOT answer from model memory.\n"
        "- Every claim must be traceable to retrieved transcript content.\n"
        "- If evidence is weak or missing, explicitly refuse by stating:\n"
        "\"Not enough transcript evidence available to answer this question confidently based on the indexed Lenny Podcast episodes.\"\n\n"
        "Required Output Structure:\n"
        "You MUST strictly format your response using this exact Markdown structure:\n\n"
        "## Answer\n\n"
        "[Grounded explanation derived only from retrieved transcript chunks. Include inline citation markers throughout the text like [Source: <Guest Name>, <Episode Title>] for each fact or recommendation.]\n\n"
        "## Key Insights\n\n"
        "- Insight 1\n"
        "- Insight 2\n"
        "- Insight 3\n\n"
        "## Sources\n\n"
        "Episode: <episode title>\n"
        "Guest: <guest name>\n"
        "Timestamp: <timestamp if available, or N/A>\n"
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
        session: Optional[AsyncSession] = None,
        min_relevant_chunks: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
    ) -> RAGResponse:
        """
        End-to-end RAG workflow:
        1. Validates user question.
        2. Retrieves top-K transcript chunks via pgvector.
        3. Validates retrieval quality (>= 2 relevant chunks, avg similarity >= threshold).
        4. Logs Grounding Check metrics.
        5. Builds grounded context prompt with citation instructions.
        6. Invokes configured LLM (with local fallback if cloud fails).
        7. Enforces strict ## Answer, ## Key Insights, and ## Sources structure.
        8. Returns grounded RAGResponse.
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

        # Check active provider to apply token-budget controls ONLY in Cloud Mode
        active_provider = get_active_provider_name()
        is_cloud = (active_provider in ("cloud", "groq")) or (not getattr(self.llm_provider, "is_local", True))

        if is_cloud:
            effective_top_k = min(top_k, getattr(settings, "CLOUD_TOP_K", 4))
            logger.info("Cloud Mode active: using top_k=%d (reduced for token budget control)", effective_top_k)
        else:
            effective_top_k = top_k

        # 1. Fetch relevant chunks from retriever
        try:
            chunks = await self.retriever.retrieve(
                query=question_stripped,
                top_k=effective_top_k,
                session=session
            )
        except Exception as exc:
            logger.error(f"RAG retrieval phase failed: {exc}", exc_info=True)
            raise RuntimeError(f"RAG retrieval failed: {exc}") from exc

        # 2. Retrieval quality validation (Requirement 6 & 10)
        threshold = similarity_threshold if similarity_threshold is not None else getattr(settings, "SIMILARITY_THRESHOLD", 0.50)
        req_min_chunks = min_relevant_chunks if min_relevant_chunks is not None else getattr(settings, "RAG_MIN_RELEVANT_CHUNKS", 2)

        if not chunks:
            logger.info(
                "Grounding Check:\n"
                "- Chunks Retrieved: 0\n"
                "- Average Similarity: 0.0000\n"
                "- Evidence Sufficient: False"
            )
            logger.warning("No relevant excerpts found for question: '%s'", question_stripped)
            return RAGResponse(
                question=question_stripped,
                answer=INSUFFICIENT_EVIDENCE_MESSAGE,
                sources=[],
                retrieved_chunks=[]
            )

        relevant_chunks = [c for c in chunks if c.similarity_score >= threshold]
        avg_similarity = sum(c.similarity_score for c in chunks) / len(chunks) if chunks else 0.0

        evidence_sufficient = (
            len(chunks) >= req_min_chunks
            and len(relevant_chunks) >= req_min_chunks
            and avg_similarity >= threshold
        )

        logger.info(
            "Grounding Check:\n"
            "- Chunks Retrieved: %d\n"
            "- Average Similarity: %.4f\n"
            "- Evidence Sufficient: %s",
            len(chunks),
            avg_similarity,
            evidence_sufficient
        )

        if not evidence_sufficient:
            logger.warning(
                "Retrieval quality insufficient for question '%s' (chunks: %d, relevant: %d, avg_sim: %.4f < %.2f)",
                question_stripped, len(chunks), len(relevant_chunks), avg_similarity, threshold
            )
            return RAGResponse(
                question=question_stripped,
                answer=INSUFFICIENT_EVIDENCE_MESSAGE,
                sources=[],
                retrieved_chunks=chunks
            )

        # 3. Build structured context (with compression & budget trimming for Cloud mode only)
        if is_cloud:
            from app.rag.cloud_optimizations import build_cloud_context, estimate_tokens
            max_context_tokens = getattr(settings, "CLOUD_MAX_CONTEXT_TOKENS", 1800)
            context_str, chunks = build_cloud_context(chunks, max_tokens=max_context_tokens)
            estimated_context_tokens = estimate_tokens(context_str)
            logger.info(
                "Cloud Context Compression & Trimming: %d characters (~%d tokens) from %d chunks",
                len(context_str),
                estimated_context_tokens,
                len(chunks),
            )
        else:
            # Local Ollama flow: completely untouched full context
            context_str = self.build_context(chunks)
            logger.info(
                "Built RAG context: %d characters (%d words) from %d chunks",
                len(context_str), len(context_str.split()), len(chunks)
            )

        # 4. Formulate grounded prompt with strict citations and structure
        prompt = (
            f"Transcript Context:\n"
            f"{context_str}\n\n"
            f"User Question: {question_stripped}\n\n"
            f"Instructions:\n"
            f"- Ground your response ONLY in the transcript context above.\n"
            f"- Do NOT use prior or outside knowledge.\n"
            f"- Add citation markers throughout the answer, for example: [Source: <Guest Name>, <Episode Title>].\n"
            f"- Structure your response with ## Answer, ## Key Insights, and ## Sources.\n\n"
            f"Response:"
        )

        if is_cloud:
            from app.rag.cloud_optimizations import estimate_tokens
            prompt_tokens = estimate_tokens(prompt) + estimate_tokens(self.SYSTEM_PROMPT)
            logger.info(
                "Cloud Token Estimation: Prompt comprises ~%d estimated tokens (budget limit: 4096)",
                prompt_tokens
            )

        # 5. Generate completion from configured LLM (with local fallback if cloud fails)
        try:
            t0_gen = time.time()
            gen_fn = getattr(self.llm_provider, "generate_response", None)
            if gen_fn is None or not (asyncio.iscoroutinefunction(gen_fn) or hasattr(gen_fn, "assert_awaited") or hasattr(gen_fn, "__await__")):
                gen_fn = getattr(self.llm_provider, "generate")

            raw_answer = await gen_fn(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.2
            )
            gen_duration = time.time() - t0_gen
            logger.info("LLM generated answer in %.2fs (%d chars)", gen_duration, len(raw_answer))
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
                logger.error("LLM generation phase failed: %s", exc, exc_info=True)
                raise RuntimeError(f"LLM generation failed: {exc}") from exc

        # 6. Enforce exact ## Answer, ## Key Insights, and ## Sources structure
        formatted_answer, unique_sources = enforce_rag_response_format(raw_answer, chunks)
        if formatted_answer == INSUFFICIENT_EVIDENCE_MESSAGE:
            unique_sources = []

        elapsed = time.time() - start_time
        logger.info(
            "Completed RAG response in %.2fs | Sources: %d episodes",
            elapsed, len(unique_sources)
        )

        return RAGResponse(
            question=question_stripped,
            answer=formatted_answer,
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
