from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
import re


class ArtifactType(str, Enum):
    ESSAY = "essay"
    MARKDOWN = "markdown"
    HTML = "html"
    CHECKLIST = "checklist"
    CODE = "code"


@dataclass
class GeneratedArtifact:
    title: str
    artifact_type: ArtifactType
    content: str
    sources: List[str] = field(default_factory=list)
    word_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.word_count and self.content:
            words = re.findall(r"\b\w+\b", self.content)
            self.word_count = len(words)


class ArtifactGenerator:
    """
    Generator for structured artifacts (Ship 30 essays, framework guides, actionable checklists).
    """

    @staticmethod
    def extract_title(content: str, default: str = "Artifact Document") -> str:
        """Extracts the top markdown header (# Title) or returns a default title."""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and len(stripped) > 2:
                return stripped[2:].strip()
        return default

    @staticmethod
    def format_sources_section(sources: List[str]) -> str:
        """Formats a list of source titles into a clean markdown reference list."""
        if not sources:
            return ""
        unique_sources = list(dict.fromkeys(sources))
        lines = ["\n\n## Sources\n"]
        for src in unique_sources:
            lines.append(f"- {src}")
        return "\n".join(lines)

    @classmethod
    def create_artifact(
        cls,
        content: str,
        artifact_type: ArtifactType = ArtifactType.ESSAY,
        title: Optional[str] = None,
        sources: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GeneratedArtifact:
        """Creates a validated GeneratedArtifact instance."""
        final_sources = sources or []
        doc_title = title or cls.extract_title(content)

        return GeneratedArtifact(
            title=doc_title,
            artifact_type=artifact_type,
            content=content,
            sources=final_sources,
            metadata=metadata or {},
        )
