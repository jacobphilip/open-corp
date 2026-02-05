"""Knowledge base — chunking, search, and validation for worker training."""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class KnowledgeEntry:
    """A single chunk of training knowledge."""

    source: str          # URL, file path
    type: str            # "youtube_transcript", "pdf", "markdown", "text", "webpage"
    content: str         # Raw text chunk
    title: str = ""      # Optional filename/page title
    chunk_index: int = 0 # Which chunk of the source (0 = first/only)


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> list[str]:
    """Split text into chunks on paragraph boundaries.

    Strategy: split on \\n\\n, merge small paragraphs up to chunk_size,
    fall back to '. ' then hard-split for huge paragraphs.
    """
    if not text or not text.strip():
        return []

    if len(text) <= chunk_size:
        return [text]

    # Split on paragraph boundaries
    paragraphs = text.split("\n\n")
    paragraphs = [p for p in paragraphs if p.strip()]

    if not paragraphs:
        return [text]

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # If a single paragraph exceeds chunk_size, split it further
        if len(para) > chunk_size:
            # Flush current buffer first
            if current:
                chunks.append(current)
                current = ""
            # Split on sentence boundaries
            sub_chunks = _split_large_paragraph(para, chunk_size)
            chunks.extend(sub_chunks)
            continue

        # Would adding this paragraph exceed the limit?
        separator = "\n\n" if current else ""
        if len(current) + len(separator) + len(para) > chunk_size:
            if current:
                chunks.append(current)
            # Start new chunk with overlap from previous
            if chunks and overlap > 0:
                prev = chunks[-1]
                overlap_text = prev[-overlap:] if len(prev) > overlap else prev
                current = overlap_text + "\n\n" + para
            else:
                current = para
        else:
            current = current + separator + para

    if current:
        chunks.append(current)

    return chunks


def _split_large_paragraph(text: str, chunk_size: int) -> list[str]:
    """Split a single large paragraph on sentence boundaries, then hard-split."""
    # Try sentence boundaries first
    sentences = text.replace(". ", ".\n").split("\n")
    sentences = [s for s in sentences if s.strip()]

    if len(sentences) > 1:
        chunks: list[str] = []
        current = ""
        for sent in sentences:
            separator = " " if current else ""
            if len(current) + len(separator) + len(sent) > chunk_size:
                if current:
                    chunks.append(current)
                current = sent
            else:
                current = current + separator + sent
        if current:
            chunks.append(current)
        return chunks

    # Hard-split as last resort
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


def search_knowledge(
    entries: list[KnowledgeEntry],
    query: str,
    max_chars: int,
) -> list[KnowledgeEntry]:
    """Find relevant knowledge entries by keyword matching.

    Tokenizes query into lowercase keywords, scores entries by keyword count,
    returns greedily within max_chars budget. Falls back to newest entries
    if no keywords match.
    """
    if not entries or max_chars <= 0:
        return []

    keywords = [w.lower() for w in query.split() if len(w) >= 2]

    if not keywords:
        return _take_within_budget(entries, max_chars)

    # Score each entry by keyword occurrence count
    scored: list[tuple[int, int, KnowledgeEntry]] = []
    for i, entry in enumerate(entries):
        content_lower = entry.content.lower()
        score = sum(content_lower.count(kw) for kw in keywords)
        scored.append((score, i, entry))

    # Sort by score descending, then by original order
    scored.sort(key=lambda x: (-x[0], x[1]))

    # If no matches at all, fall back to newest entries
    if scored[0][0] == 0:
        return _take_within_budget(list(reversed(entries)), max_chars)

    # Take greedily within budget, skip zero-score entries
    result: list[KnowledgeEntry] = []
    used = 0
    for score, _, entry in scored:
        if score == 0:
            break
        if used + len(entry.content) > max_chars:
            continue
        result.append(entry)
        used += len(entry.content)

    return result


def _take_within_budget(entries: list[KnowledgeEntry], max_chars: int) -> list[KnowledgeEntry]:
    """Take entries greedily within character budget."""
    result: list[KnowledgeEntry] = []
    used = 0
    for entry in entries:
        if used + len(entry.content) > max_chars:
            break
        result.append(entry)
        used += len(entry.content)
    return result


def validate_knowledge(entries: list[KnowledgeEntry]) -> list[str]:
    """Return warnings for problematic knowledge entries.

    Checks: empty content, very short (<50 chars), duplicates,
    repetitive chars (>50% same char), total size >500KB.
    """
    warnings: list[str] = []

    if not entries:
        return warnings

    total_size = 0
    seen_content: set[str] = set()

    for i, entry in enumerate(entries):
        content = entry.content

        if not content or not content.strip():
            warnings.append(f"Entry {i}: empty content (source: {entry.source})")
            continue

        if len(content) < 50:
            warnings.append(f"Entry {i}: very short ({len(content)} chars, source: {entry.source})")

        # Check for duplicates
        content_key = content[:200]
        if content_key in seen_content:
            warnings.append(f"Entry {i}: duplicate content (source: {entry.source})")
        seen_content.add(content_key)

        # Check for repetitive characters
        if content:
            from collections import Counter
            char_counts = Counter(content)
            most_common_count = char_counts.most_common(1)[0][1]
            if most_common_count > len(content) * 0.5:
                warnings.append(f"Entry {i}: repetitive content (source: {entry.source})")

        total_size += len(content)

    if total_size > 500_000:
        warnings.append(f"Total knowledge size {total_size} chars exceeds 500KB limit")

    return warnings


class KnowledgeBase:
    """Manages a worker's knowledge entries on disk."""

    def __init__(self, knowledge_dir: Path, entries: list[KnowledgeEntry] | None = None):
        self.knowledge_dir = knowledge_dir
        self.entries: list[KnowledgeEntry] = entries or []

    @classmethod
    def load(cls, knowledge_dir: Path) -> "KnowledgeBase":
        """Load knowledge entries from knowledge.json in the given directory."""
        knowledge_path = knowledge_dir / "knowledge.json"
        if not knowledge_path.exists():
            return cls(knowledge_dir, [])

        try:
            data = json.loads(knowledge_path.read_text())
            entries = [
                KnowledgeEntry(
                    source=d.get("source", ""),
                    type=d.get("type", "text"),
                    content=d.get("content", ""),
                    title=d.get("title", ""),
                    chunk_index=d.get("chunk_index", 0),
                )
                for d in data
            ]
            return cls(knowledge_dir, entries)
        except (json.JSONDecodeError, OSError):
            return cls(knowledge_dir, [])

    def save(self) -> None:
        """Write entries to knowledge.json."""
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        knowledge_path = self.knowledge_dir / "knowledge.json"
        knowledge_path.write_text(json.dumps(
            [asdict(e) for e in self.entries],
            indent=2,
        ))

    def add_entries(self, new_entries: list[KnowledgeEntry]) -> None:
        """Append new entries and save."""
        self.entries.extend(new_entries)
        self.save()
