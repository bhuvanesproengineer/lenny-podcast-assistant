import logging
import re
import time
from typing import Optional, List, Any, Tuple

from app.config import settings
from app.providers.base import BaseLLMProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.provider_factory import get_provider

logger = logging.getLogger(__name__)


# =============================================================================
# Ship30 Result Wrapper (Backward-Compatible String Subclass)
# =============================================================================

class Ship30Result(str):
    """
    A string subclass representing the generated essay, carrying attached sources,
    raw markdown content, rendered HTML content, artifact status, and word count.
    Behaves identically to a standard `str` for backward compatibility, while providing
    convenient access to `.sources`, `.essay`, `.markdown_content`, `.html_content`, `.artifact`, and `.word_count`.
    """
    sources: List[str]
    markdown_content: str
    html_content: str
    artifact: bool
    word_count: int

    def __new__(
        cls,
        essay: str,
        sources: Optional[List[str]] = None,
        markdown_content: Optional[str] = None,
        html_content: Optional[str] = None,
        artifact: bool = True,
        word_count: Optional[int] = None,
    ):
        instance = super().__new__(cls, essay)
        instance.sources = list(sources) if sources else []
        instance.markdown_content = markdown_content if markdown_content is not None else str(essay)
        instance.html_content = html_content or ""
        instance.artifact = artifact
        instance.word_count = word_count if word_count is not None else len(instance.markdown_content.split())
        return instance

    @property
    def essay(self) -> str:
        return str(self)


# =============================================================================
# Assignment-Aligned Ship30 Section Targets & Generation Prompt Template
# =============================================================================

SECTION_TARGETS = {
    "Hook": {"min": 150, "max": 200},
    "Problem": {"min": 200, "max": 250},
    "Insight": {"min": 250, "max": 300},
    "Lesson": {"min": 250, "max": 300},
    "Application": {"min": 250, "max": 300},
    "Conclusion": {"min": 100, "max": 150},
}

SHIP_30_PROMPT_TEMPLATE = """You are an expert ghostwriter trained in the Ship 30 for 30 methodology.

Your task is to transform the provided source transcripts and context into a complete, high-impact Ship30-style growth article.

### Structural Requirements:
Target Word Count: Approximately 1,250 words (Strict Minimum: 1,200 words, Target: 1,200–1,400 words).
Every section MUST be developed with substantial analytical depth, concrete frameworks, and grounded details to hit its word target:
- The Hook (First 2-3 lines): 150–200 words (start with a surprising observation, counterintuitive truth, or urgent product/growth tension)
- ## Problem: 200–250 words (deep dive into the core mistake, structural trap, or strategic failure product teams encounter)
- ## Insight: 250–300 words (the non-obvious breakthrough, mental shift, or counter-narrative uncovered by podcast guests)
- ## Lesson: 250–300 words (fundamental principles, mental models, or strategic frameworks extracted from the experience)
- ## Application: 250–300 words (concrete real-world case studies, walkthroughs, or tactical execution patterns from transcripts)
- ## Action Steps: 3-5 high-leverage implementation steps
- ## Conclusion: 100–150 words (memorable closing synthesis with the overarching takeaway)
- ## Transcript Sources: Referenced podcast episodes, guest speakers, and timestamps

### Mandatory Article Structure:
You MUST format the entire article with these exact Markdown headers in this exact order:

# [Punchy, Action-Oriented Title]

## Hook
[150-200 words: Start with a surprising observation, counterintuitive truth, or urgent product/growth tension.]

## Problem
[200-250 words: Deep dive into the core mistake, structural trap, or strategic failure product teams encounter.]

## Insight
[250-300 words: The non-obvious breakthrough, mental shift, or counter-narrative uncovered by podcast guests.]

## Lesson
[250-300 words: The fundamental principles, mental models, or strategic frameworks extracted from the experience.]

## Application
[250-300 words: Concrete real-world case studies, walkthroughs, or tactical execution patterns from the transcripts.]

## Action Steps
[3-5 clear, highly actionable, step-by-step takeaways product leaders can execute immediately.]

## Conclusion
[100-150 words: A memorable closing synthesis with the overarching takeaway.]

## Transcript Sources
Episode: <episode title>
Guest: <guest name>
Timestamp: <timestamp if available>

### Strict Length & Grounding Constraints:
1. STRICT MINIMUM ARTICLE LENGTH: The entire article MUST be at least 1,200 words (Target: 1,200–1,400 words). Do NOT abbreviate, summarize, or truncate any section.
2. Use ONLY information contained in the provided transcript context.
3. Attribute insights to the correct guest or episode with inline citations. The article must explicitly cite which podcast insights, frameworks, and guest quotes were used from the transcripts.
4. If the provided context does not contain enough transcript evidence to write this article, return EXACTLY AND ONLY:
   Not enough transcript evidence available.
5. Do NOT hallucinate.

Context Material:
{context_data}

User Request:
{user_query}
"""


def parse_source_reference(title: str) -> Tuple[str, Optional[str]]:
    """
    Extracts (clean_episode_title, speaker_name) from an episode title string.
    e.g. 'How to build your product strategy stack | Ravi Mehta (Tinder, Facebook)'
    -> ('How to build your product strategy stack', 'Ravi Mehta')
    """
    if "|" in title:
        parts = title.split("|", 1)
        ep_title = parts[0].strip()
        speaker_part = parts[1].strip()
        speaker_match = re.match(r"^([^(]+)", speaker_part)
        speaker = speaker_match.group(1).strip() if speaker_match else speaker_part
        return ep_title, speaker
    return title.strip(), None


def format_sources_section(sources: List[str], chunks: Optional[List[Any]] = None) -> str:
    """Formats a guaranteed ## Transcript Sources section with Episode, Guest, and Timestamp (Requirement 8)."""
    if not sources:
        return "## Transcript Sources\n\nEpisode: Lenny's Podcast Transcripts\nGuest: N/A\nTimestamp: N/A"

    entries = []
    seen = set()
    for src in sources:
        ep_title, speaker = parse_source_reference(src)
        key = (ep_title, speaker or "")
        if key in seen:
            continue
        seen.add(key)
        ts = "N/A"
        if chunks:
            for c in chunks:
                c_title = getattr(c, "episode_title", "")
                if c_title == src or ep_title in c_title:
                    content_str = getattr(c, "content", getattr(c, "chunk_text", ""))
                    match = re.search(r"\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?", content_str)
                    if match:
                        ts = match.group(1)
                        break

        entry = f"Episode: {ep_title}\nGuest: {speaker or 'Lenny’s Podcast Guest'}\nTimestamp: {ts}"
        entries.append(entry)

    return "## Transcript Sources\n\n" + "\n\n".join(entries)


def count_words(text: str) -> int:
    """Calculates word count for markdown text."""
    if not text:
        return 0
    return len(text.strip().split())


def parse_markdown_sections(markdown_text: str) -> List[Tuple[str, str]]:
    """
    Parses an article into ordered (header_title, section_body) pairs.
    Handles the top title '# Title' and each '## Header'.
    """
    lines = markdown_text.splitlines(keepends=True)
    sections: List[Tuple[str, str]] = []
    current_header = ""
    current_lines: List[str] = []

    for line in lines:
        if line.startswith("# ") and not sections and not current_header:
            current_header = line.strip()
            current_lines = []
        elif line.startswith("## "):
            if current_header or current_lines:
                sections.append((current_header, "".join(current_lines)))
            current_header = line.strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_header or current_lines:
        sections.append((current_header, "".join(current_lines)))

    return sections


def reconstruct_markdown(sections: List[Tuple[str, str]]) -> str:
    """Reconstructs clean markdown article from (header, body) section pairs."""
    blocks = []
    for header, body in sections:
        clean_b = body.strip()
        if header:
            if clean_b:
                blocks.append(f"{header}\n{clean_b}")
            else:
                blocks.append(header)
        elif clean_b:
            blocks.append(clean_b)
    return "\n\n".join(blocks).strip()


# =============================================================================
# Ship30Writer Implementation
# =============================================================================

class Ship30Writer:
    """
    Skill for generating authentic, narrative-driven Ship 30 style essays
    grounded in Lenny's Podcast transcripts.
    """

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        retriever: Optional[Any] = None,
    ):
        self._custom_llm_provider = llm_provider
        self._retriever = retriever

    @property
    def llm_provider(self) -> BaseLLMProvider:
        if self._custom_llm_provider is not None:
            return self._custom_llm_provider
        return get_provider()

    @llm_provider.setter
    def llm_provider(self, val: Optional[BaseLLMProvider]) -> None:
        self._custom_llm_provider = val

    def _get_retriever(self) -> Optional[Any]:
        """Lazy-loads the retriever to avoid database connections during unit testing."""
        if self._retriever is not None:
            return self._retriever
        try:
            from app.rag.retriever import Retriever
            self._retriever = Retriever()
            return self._retriever
        except Exception as exc:
            logger.warning("Retriever unavailable for Ship30Writer: %s", exc)
            return None

    async def _generate_llm(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.3,
        num_predict: int = 4000,
    ) -> str:
        """Helper to invoke active LLM provider with fallback to local Ollama if configured."""
        try:
            return await self.llm_provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                num_predict=num_predict,
            )
        except Exception as exc:
            if getattr(settings, "FALLBACK_TO_LOCAL", True) and not self.llm_provider.is_local:
                logger.warning("Cloud generation failed in Ship30Writer: %s. Falling back to local Ollama...", exc)
                try:
                    fallback_prov = OllamaProvider()
                    return await fallback_prov.generate(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        num_predict=num_predict,
                    )
                except Exception as fallback_exc:
                    logger.error("Local fallback also failed in Ship30Writer: %s", fallback_exc, exc_info=True)
                    raise RuntimeError(f"Both Cloud and Local generation failed: {fallback_exc}") from fallback_exc
            else:
                logger.error("Ship30 generation failed: %s", exc, exc_info=True)
                raise RuntimeError(f"Ship30 generation failed: {exc}") from exc

    async def write(
        self,
        topic: str = "",
        context: Optional[str] = None,
        user_query: Optional[str] = None,
        context_data: Optional[str] = None,
    ) -> Ship30Result:
        """
        Generates an authentic Ship30 essay grounded in podcast transcript context.
        Enforces a minimum article length of 1,200 words (target: 1,200–1,400 words).

        Args:
            topic: The central topic or theme for the essay.
            context: Optional pre-retrieved background text.
            user_query: Alternative parameter for topic/request.
            context_data: Alternative parameter for context.

        Returns:
            Ship30Result (str subclass) with .essay text, .sources list, and .word_count.
        """
        query = (user_query or topic or "").strip()
        ctx = (context_data if context_data is not None else context) or ""
        logger.info("Generating authentic Ship 30 long-form essay", extra={"query": query})

        sources: List[str] = []

        # 1. If context was not passed, retrieve it using the RAG retriever
        if not ctx.strip():
            retriever = self._get_retriever()
            if retriever:
                try:
                    chunks = await retriever.retrieve(query=query, top_k=8)
                    if chunks:
                        threshold = getattr(settings, "SIMILARITY_THRESHOLD", 0.50)
                        avg_sim = sum(c.similarity_score for c in chunks) / len(chunks) if chunks else 0.0
                        evidence_sufficient = len(chunks) >= 2 and avg_sim >= threshold
                        logger.info(
                            "Grounding Check:\n"
                            "- Chunks Retrieved: %d\n"
                            "- Average Similarity: %.4f\n"
                            "- Evidence Sufficient: %s",
                            len(chunks),
                            avg_sim,
                            evidence_sufficient
                        )
                        max_sim = max(c.similarity_score for c in chunks)
                        if max_sim < threshold:
                            logger.info(
                                "Ship30Writer: Chunks for '%s' below similarity threshold (max %.4f < %.2f)",
                                query, max_sim, threshold
                            )
                            chunks = []

                    if chunks:
                        sources = list(dict.fromkeys([c.episode_title for c in chunks]))
                        context_blocks = []
                        for i, chunk in enumerate(chunks, start=1):
                            context_blocks.append(
                                f"--- Transcript Excerpt {i} (Episode: \"{chunk.episode_title}\") ---\n"
                                f"{chunk.content.strip()}"
                            )
                        ctx = "\n\n".join(context_blocks)
                        logger.info(
                            "Ship30Writer retrieved %d transcript chunks across %d episodes",
                            len(chunks), len(sources)
                        )
                except Exception as exc:
                    logger.warning("Transcript retrieval failed for query '%s': %s", query, exc)
        else:
            # Extract any episode titles explicitly mentioned in the passed context
            found_episodes = re.findall(r'Episode:\s*["\']([^"\']+)["\']', ctx)
            if found_episodes:
                sources = list(dict.fromkeys(found_episodes))

        # Check if transcript evidence is missing
        if not ctx.strip():
            logger.info("Ship30Writer: Insufficient transcript context available for query '%s'", query)
            negative_msg = "Not enough transcript evidence available."
            return Ship30Result(
                negative_msg,
                sources=[],
                markdown_content=None,
                html_content=None,
                artifact=False,
                word_count=len(negative_msg.split())
            )

        # 2. Build generation prompt using SHIP_30_PROMPT_TEMPLATE
        effective_context = ctx.strip()
        full_prompt = SHIP_30_PROMPT_TEMPLATE.format(
            context_data=effective_context,
            user_query=query,
        )

        system_prompt = (
            "You are an expert ghostwriter trained in the Ship 30 for 30 methodology.\n"
            "Your mission is to write a complete, comprehensive, long-form Ship 30 for 30 style article.\n"
            "MANDATORY LENGTH REQUIREMENTS: Strict minimum 1,200 words, target 1,200–1,400 words.\n"
            "Section word budgets:\n"
            "- Hook: 150–200 words\n"
            "- Problem: 200–250 words\n"
            "- Insight: 250–300 words\n"
            "- Lesson: 250–300 words\n"
            "- Application: 250–300 words\n"
            "- Conclusion: 100–150 words\n"
            "Use the exact Markdown headers in this exact order:\n"
            "# [Punchy Title]\n"
            "## Hook\n"
            "## Problem\n"
            "## Insight\n"
            "## Lesson\n"
            "## Application\n"
            "## Action Steps\n"
            "## Conclusion\n"
            "## Sources\n"
            "Grounded strictly in the provided podcast transcripts.\n"
            "If there is insufficient transcript evidence, return EXACTLY: Not enough transcript evidence available."
        )

        # 3. Generate initial completion
        t0 = time.time()
        raw_essay = await self._generate_llm(
            prompt=full_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            num_predict=4000,
        )

        clean_essay = raw_essay.strip()

        # Check if output indicates insufficient transcript evidence
        is_insufficient = (
            clean_essay == "Not enough transcript evidence available."
            or "not enough transcript evidence available" in clean_essay.lower()
        )

        if is_insufficient:
            logger.info("Insufficient transcript evidence for Ship30 essay on query '%s'", query)
            return Ship30Result(
                "Not enough transcript evidence available.",
                sources=[],
                markdown_content="Not enough transcript evidence available.",
                html_content="<p>Not enough transcript evidence available.</p>",
                artifact=False,
                word_count=5
            )

        # 4. Guarantee # Title is at the top of the article if it started with an H2 section
        if clean_essay.startswith("## "):
            title_candidate = query.strip().title() if query.strip() else "Ship30 Growth Strategy"
            clean_essay = f"# {title_candidate}\n\n{clean_essay}"

        # 5. Word count validation and automatic expansion step
        initial_words = count_words(clean_essay)
        logger.info(
            "Initial Ship30 draft generated: %d words (target: >= 1200 words)",
            initial_words,
            extra={"query": query, "initial_words": initial_words}
        )

        if initial_words < 1200:
            logger.info(
                "Draft is below 1200 words (%d words). Commencing automatic section expansion...",
                initial_words
            )
            parsed_sections = parse_markdown_sections(clean_essay)
            candidate_keys = ["Problem", "Insight", "Lesson", "Application", "Hook", "Conclusion"]
            attempted_indices = set()
            expansion_rounds = 0
            max_expansion_rounds = 4

            while count_words(reconstruct_markdown(parsed_sections)) < 1200 and expansion_rounds < max_expansion_rounds:
                best_idx = None
                best_deficit = -1
                best_sec_name = None

                for idx, (hdr, body) in enumerate(parsed_sections):
                    if idx in attempted_indices:
                        continue
                    matched_key = None
                    for k in candidate_keys:
                        if k.lower() in hdr.lower():
                            matched_key = k
                            break
                    if matched_key and matched_key in SECTION_TARGETS:
                        sec_words = count_words(body)
                        target_min = SECTION_TARGETS[matched_key]["min"]
                        deficit = target_min - sec_words
                        if deficit > best_deficit:
                            best_deficit = deficit
                            best_idx = idx
                            best_sec_name = matched_key

                # Fallback: choose shortest unattempted body section
                if best_idx is None:
                    shortest_len = float("inf")
                    for idx, (hdr, body) in enumerate(parsed_sections):
                        if idx in attempted_indices or not hdr.startswith("## ") or "sources" in hdr.lower():
                            continue
                        w = count_words(body)
                        if w < shortest_len:
                            shortest_len = w
                            best_idx = idx
                            best_sec_name = hdr.replace("##", "").strip()

                if best_idx is None:
                    break

                attempted_indices.add(best_idx)
                expansion_rounds += 1
                hdr, body = parsed_sections[best_idx]
                target_min = SECTION_TARGETS.get(best_sec_name, {}).get("min", 250)
                target_max = SECTION_TARGETS.get(best_sec_name, {}).get("max", 300)

                expand_prompt = (
                    f"You are expanding a section of a Ship 30 for 30 growth article to meet publication depth standards.\n\n"
                    f"Article Topic: {query}\n"
                    f"Section Header: {hdr}\n"
                    f"Current Section Text ({count_words(body)} words):\n{body}\n\n"
                    f"Podcast Transcript Context:\n{effective_context}\n\n"
                    f"Task:\n"
                    f"Rewrite and significantly expand this '{hdr}' section so it reaches {target_min} to {target_max} words.\n"
                    f"- Ground deeply in podcast transcript frameworks, guest quotes, tactical metrics, and real-world examples.\n"
                    f"- Preserve the authoritative, punchy Ship 30 tone.\n"
                    f"- Return ONLY the expanded body text for this section. Do NOT include the '{hdr}' line or any other sections."
                )

                try:
                    expanded_body = await self._generate_llm(
                        prompt=expand_prompt,
                        system_prompt="You are an elite product ghostwriter expanding an article section to substantial analytical depth. Return only the body text.",
                        temperature=0.3,
                        num_predict=2000,
                    )
                    clean_expanded = expanded_body.strip()
                    clean_expanded = re.sub(r"^#+\s*[^\n]+\n+", "", clean_expanded).strip()

                    if count_words(clean_expanded) > count_words(body):
                        logger.info(
                            "Expanded section '%s' from %d to %d words",
                            hdr, count_words(body), count_words(clean_expanded)
                        )
                        parsed_sections[best_idx] = (hdr, clean_expanded)
                    else:
                        logger.info(
                            "Expansion for '%s' did not increase word count (%d -> %d)",
                            hdr, count_words(body), count_words(clean_expanded)
                        )
                except Exception as exp_err:
                    logger.warning("Section expansion failed for '%s': %s", hdr, exp_err)

            clean_essay = reconstruct_markdown(parsed_sections)

        # 6. Guarantee ## Transcript Sources section with episode titles, guest, and timestamps
        chunks_val = chunks if 'chunks' in locals() else None
        formatted_sources = format_sources_section(sources, chunks=chunks_val)
        if "## Transcript Sources" in clean_essay:
            clean_essay = re.sub(r"##\s*Transcript Sources[\s\S]*$", formatted_sources.strip(), clean_essay).strip()
        elif "## Sources" in clean_essay:
            clean_essay = re.sub(r"##\s*Sources[\s\S]*$", formatted_sources.strip(), clean_essay).strip()
        else:
            clean_essay = clean_essay + "\n\n" + formatted_sources.strip()

        # 7. Generate rendered HTML content
        try:
            from markdown_it import MarkdownIt
            md_parser = MarkdownIt()
            rendered_body = md_parser.render(clean_essay)
            html_content = f'<article class="ship30-article">\n{rendered_body}\n</article>'
        except Exception as exc:
            logger.warning("Failed to render HTML from markdown: %s", exc)
            html_content = f'<article class="ship30-article">\n<div>{clean_essay}</div>\n</article>'

        # 8. Log final word count in the backend
        word_count = count_words(clean_essay)
        elapsed = time.time() - t0
        logger.info(
            "Ship30 article generation completed | Word count: %d (target >= 1200 words)",
            word_count,
            extra={
                "query": query,
                "duration_s": round(elapsed, 2),
                "word_count": word_count,
                "sources_count": len(sources),
                "meets_target": word_count >= 1200,
            }
        )

        return Ship30Result(
            clean_essay,
            sources=sources,
            markdown_content=clean_essay,
            html_content=html_content,
            artifact=True,
            word_count=word_count,
        )
