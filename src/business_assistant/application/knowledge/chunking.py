"""Deterministic Markdown and FAQ normalization and chunking policies."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from .models import KnowledgeChunkDraft

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_INSTRUCTION_PATTERNS = (
    re.compile(r"\bignore\s+(all\s+)?previous\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\b(system|developer)\s+(prompt|message)\b", re.IGNORECASE),
    re.compile(r"\b(call|invoke|use)\s+(a\s+)?tool\b", re.IGNORECASE),
    re.compile(r"\breveal\s+(the\s+)?(prompt|secret|api key)\b", re.IGNORECASE),
)


def normalize_source(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()]
    result: list[str] = []
    for line in lines:
        if line or (result and result[-1]):
            result.append(line)
    return "\n".join(result).strip()


def content_checksum(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def has_instruction_risk(value: str) -> bool:
    return any(pattern.search(value) is not None for pattern in _INSTRUCTION_PATTERNS)


@dataclass(frozen=True, slots=True)
class DeterministicKnowledgeChunker:
    max_tokens: int = 500
    overlap_tokens: int = 50

    def __post_init__(self) -> None:
        if not 50 <= self.max_tokens <= 1000:
            raise ValueError("Knowledge chunk maximum must be between 50 and 1000 tokens")
        if not 0 <= self.overlap_tokens < self.max_tokens // 2:
            raise ValueError("Knowledge chunk overlap is invalid")

    def markdown(self, source: str) -> tuple[KnowledgeChunkDraft, ...]:
        normalized = normalize_source(source)
        if not normalized:
            raise ValueError("Markdown knowledge source is empty")
        sections = self._sections(normalized)
        chunks: list[KnowledgeChunkDraft] = []
        for heading, body in sections:
            tokens = body.split()
            if not tokens:
                continue
            start = 0
            while start < len(tokens):
                window = tokens[start : start + self.max_tokens]
                prefix = f"{heading}\n" if heading else ""
                text = f"{prefix}{' '.join(window)}".strip()
                chunks.append(
                    KnowledgeChunkDraft(
                        len(chunks),
                        text,
                        len(window),
                        content_checksum(text),
                        heading,
                        has_instruction_risk(text),
                    )
                )
                if start + self.max_tokens >= len(tokens):
                    break
                start += self.max_tokens - self.overlap_tokens
        if not chunks:
            raise ValueError("Markdown knowledge source has no usable content")
        return tuple(chunks)

    def faq(
        self,
        question: str,
        answer: str,
        *,
        aliases: tuple[str, ...] = (),
        priority: int = 0,
    ) -> tuple[KnowledgeChunkDraft, ...]:
        question_value, answer_value = normalize_source(question), normalize_source(answer)
        alias_values = tuple(normalize_source(alias) for alias in aliases)
        if not question_value or not answer_value or any(not alias for alias in alias_values):
            raise ValueError("FAQ question, answer, and aliases must be non-empty")
        if len(alias_values) > 20 or len(set(alias_values)) != len(alias_values):
            raise ValueError("FAQ aliases must be unique and contain at most 20 values")
        if not 0 <= priority <= 100:
            raise ValueError("FAQ priority must be between 0 and 100")
        text = f"Question: {question_value}\nAnswer: {answer_value}"
        if len(text.split()) > self.max_tokens:
            raise ValueError("FAQ must fit in one knowledge chunk")
        return (
            KnowledgeChunkDraft(
                0,
                text,
                len(text.split()),
                content_checksum(text),
                "FAQ",
                has_instruction_risk(text),
                {"aliases": alias_values, "priority": priority, "question": question_value},
            ),
        )

    @staticmethod
    def _sections(source: str) -> tuple[tuple[str | None, str], ...]:
        sections: list[tuple[str | None, list[str]]] = []
        heading: str | None = None
        body: list[str] = []
        for line in source.splitlines():
            match = _HEADING.match(line)
            if match:
                if body:
                    sections.append((heading, body))
                heading, body = match.group(2), []
            elif line:
                body.append(line)
        if body:
            sections.append((heading, body))
        return tuple((title, "\n".join(lines)) for title, lines in sections)
