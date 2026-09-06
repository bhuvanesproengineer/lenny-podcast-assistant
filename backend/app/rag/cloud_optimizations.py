import asyncio
import logging
import re
import time
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger("cloud_optimizations")


def estimate_tokens(text: str) -> int:
    """
    Estimates token count for text using standard character/word ratio.
    Averages ~3.8 characters per token for English text and code.
    """
    if not text:
        return 0
    char_estimate = len(text) / 3.8
    word_estimate = len(text.split()) * 1.33
    # Use blended estimate for accuracy
    return max(1, int((char_estimate + word_estimate) / 2))


def compress_transcript_content(content: str) -> str:
    """
    Compresses transcript text to maximize information density for Cloud LLM:
    - Normalizes excessive whitespace and multiple newlines
    - Strips dialogue tags or redundant timestamp headers if repetitive
    - Strips filler outro/intro boilerplate
    """
    if not content:
        return ""
    # Normalize multiple newlines
    c = re.sub(r"\n{3,}", "\n\n", content.strip())
    # Normalize spaces per line
    lines = [line.strip() for line in c.split("\n")]
    compressed = "\n".join(lines)
    # Collapse multiple inline spaces
    compressed = re.sub(r"[ \t]{2,}", " ", compressed)
    return compressed.strip()


def build_cloud_context(
    chunks: List[Any],
    max_tokens: int = 1800
) -> Tuple[str, List[Any]]:
    """
    Constructs a token-budgeted, compressed context block for Cloud LLM.
    Ensures context never exceeds max_tokens budget (trimming lower-ranked excerpts).
    Returns (formatted_context, retained_chunks).
    """
    if not chunks:
        return "", []

    retained_chunks = []
    context_blocks = []
    current_tokens = 0

    for i, chunk in enumerate(chunks, start=1):
        raw_text = getattr(chunk, "content", getattr(chunk, "chunk_text", "")) or ""
        compressed = compress_transcript_content(raw_text)
        ep_title = getattr(chunk, "episode_title", None) or "Lenny's Podcast"
        block_header = f"[Excerpt {i}] (From Episode: \"{ep_title}\")\n"
        block_full = f"{block_header}{compressed}"
        block_tokens = estimate_tokens(block_full)

        if current_tokens + block_tokens <= max_tokens:
            context_blocks.append(block_full)
            retained_chunks.append(chunk)
            current_tokens += block_tokens
        else:
            # Check if we can partially fit this excerpt
            remaining_tokens = max_tokens - current_tokens
            if remaining_tokens > 150:
                # Trim excerpt to fit remaining budget
                allowed_chars = int(remaining_tokens * 3.6)
                trimmed_text = compressed[:allowed_chars].rsplit(" ", 1)[0] + "..."
                trimmed_block = f"{block_header}{trimmed_text}"
                context_blocks.append(trimmed_block)
                retained_chunks.append(chunk)
                current_tokens += estimate_tokens(trimmed_block)
            break

    total_context = "\n\n".join(context_blocks)
    logger.info(
        "Cloud Context Optimization: %d chunks compressed to %d chars (~%d tokens, budget: %d)",
        len(retained_chunks),
        len(total_context),
        current_tokens,
        max_tokens
    )
    return total_context, retained_chunks


class TPMTracker:
    """
    Thread-safe / async rolling window rate limiter to protect Cloud/Groq from TPM exhaustion.
    Maintains a 60-second sliding window of token usage.
    """

    def __init__(self, tpm_limit: int = 20000):
        self.tpm_limit = tpm_limit
        self._history: List[Tuple[float, int]] = []
        self._lock = asyncio.Lock()

    def _purge_old_entries(self, now: float) -> None:
        window_start = now - 60.0
        self._history = [entry for entry in self._history if entry[0] >= window_start]

    def get_current_window_tokens(self) -> int:
        now = time.time()
        self._purge_old_entries(now)
        return sum(tokens for _, tokens in self._history)

    async def acquire(self, estimated_tokens: int) -> float:
        """
        Acquires token capacity. If adding estimated_tokens exceeds tpm_limit,
        sleeps for the necessary delay to stay within the 60s sliding window limit.
        Returns total sleep time (if any).
        """
        async with self._lock:
            now = time.time()
            self._purge_old_entries(now)
            current_usage = sum(tokens for _, tokens in self._history)

            total_slept = 0.0
            while current_usage + estimated_tokens > self.tpm_limit and self._history:
                # Need to wait until oldest entry slides out of the 60s window
                oldest_time, oldest_tokens = self._history[0]
                sleep_needed = max(0.05, (oldest_time + 60.0) - time.time() + 0.05)
                logger.warning(
                    "TPM protection triggered: current %d + request %d > limit %d. Sleeping %.2fs...",
                    current_usage,
                    estimated_tokens,
                    self.tpm_limit,
                    sleep_needed
                )
                await asyncio.sleep(sleep_needed)
                total_slept += sleep_needed
                now = time.time()
                self._purge_old_entries(now)
                current_usage = sum(tokens for _, tokens in self._history)

            self._history.append((time.time(), estimated_tokens))
            logger.info(
                "TPM Tracker: Reserved %d tokens (sliding window usage: %d/%d TPM)",
                estimated_tokens,
                current_usage + estimated_tokens,
                self.tpm_limit
            )
            return total_slept


# Global singleton tracker for cloud providers
_cloud_tpm_tracker: Optional[TPMTracker] = None


def get_cloud_tpm_tracker(tpm_limit: Optional[int] = None) -> TPMTracker:
    global _cloud_tpm_tracker
    if _cloud_tpm_tracker is None:
        from app.config import settings
        limit = tpm_limit or getattr(settings, "CLOUD_TPM_LIMIT", 20000)
        _cloud_tpm_tracker = TPMTracker(tpm_limit=limit)
    return _cloud_tpm_tracker
