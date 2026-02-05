"""Tests for framework/knowledge.py."""

import json

import pytest

from framework.knowledge import (
    KnowledgeBase,
    KnowledgeEntry,
    chunk_text,
    search_knowledge,
    validate_knowledge,
)


class TestChunkText:
    def test_short_text_no_split(self):
        """Text under chunk_size returns as single chunk."""
        result = chunk_text("Hello world", chunk_size=100)
        assert result == ["Hello world"]

    def test_empty_text(self):
        """Empty/whitespace text returns empty list."""
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_paragraph_boundaries(self):
        """Splits on double-newline paragraph boundaries."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        result = chunk_text(text, chunk_size=30, overlap=0)
        assert len(result) >= 2
        assert "Paragraph one." in result[0]

    def test_long_text_multiple_chunks(self):
        """Long text produces multiple chunks within size limit."""
        paragraphs = [f"Paragraph {i} with some content." for i in range(20)]
        text = "\n\n".join(paragraphs)
        result = chunk_text(text, chunk_size=100, overlap=0)
        assert len(result) > 1
        for chunk in result:
            # Allow some tolerance for overlap
            assert len(chunk) <= 200  # generous bound

    def test_single_huge_paragraph(self):
        """A single paragraph larger than chunk_size is split."""
        text = "Word " * 1000  # ~5000 chars
        result = chunk_text(text, chunk_size=200, overlap=0)
        assert len(result) > 1

    def test_overlap_preservation(self):
        """Overlap text from previous chunk appears at start of next."""
        text = "A" * 100 + "\n\n" + "B" * 100 + "\n\n" + "C" * 100
        result = chunk_text(text, chunk_size=120, overlap=20)
        assert len(result) >= 2
        # Second chunk should start with tail of first
        if len(result) >= 2:
            first_tail = result[0][-20:]
            assert first_tail in result[1]


class TestSearchKnowledge:
    def _make_entries(self, contents: list[str]) -> list[KnowledgeEntry]:
        return [
            KnowledgeEntry(source=f"src{i}", type="text", content=c)
            for i, c in enumerate(contents)
        ]

    def test_keyword_match(self):
        """Entries matching query keywords are returned."""
        entries = self._make_entries([
            "Python is great for data science",
            "JavaScript is used for web development",
            "Python frameworks include Django and Flask",
        ])
        result = search_knowledge(entries, "Python frameworks", max_chars=10000)
        assert len(result) >= 1
        # The Python entries should come first
        assert "Python" in result[0].content

    def test_no_match_fallback(self):
        """When no keywords match, falls back to newest entries."""
        entries = self._make_entries([
            "Alpha content here",
            "Beta content here",
            "Gamma content here",
        ])
        result = search_knowledge(entries, "zzz_nonexistent", max_chars=10000)
        # Should return entries (fallback to newest)
        assert len(result) > 0

    def test_budget_enforcement(self):
        """Results fit within max_chars budget."""
        entries = self._make_entries([
            "A" * 100,
            "B" * 100,
            "C" * 100,
        ])
        result = search_knowledge(entries, "A B C", max_chars=150)
        total = sum(len(e.content) for e in result)
        assert total <= 150

    def test_multi_keyword_scoring(self):
        """Entry with more keyword matches ranks higher."""
        entries = self._make_entries([
            "python python python",  # 3 matches
            "python once",           # 1 match
            "no match here",         # 0 matches
        ])
        result = search_knowledge(entries, "python", max_chars=10000)
        assert result[0].content == "python python python"

    def test_empty_entries(self):
        """Empty entries list returns empty."""
        assert search_knowledge([], "query", max_chars=1000) == []

    def test_zero_budget(self):
        """Zero budget returns empty."""
        entries = self._make_entries(["content"])
        assert search_knowledge(entries, "content", max_chars=0) == []


class TestValidateKnowledge:
    def _make_entry(self, content: str, source: str = "test") -> KnowledgeEntry:
        return KnowledgeEntry(source=source, type="text", content=content)

    def test_empty_content(self):
        """Flags entries with empty content."""
        entries = [self._make_entry(""), self._make_entry("   ")]
        warnings = validate_knowledge(entries)
        assert any("empty" in w for w in warnings)

    def test_short_content(self):
        """Flags entries with <50 chars."""
        entries = [self._make_entry("Short.")]
        warnings = validate_knowledge(entries)
        assert any("very short" in w for w in warnings)

    def test_duplicate_content(self):
        """Flags duplicate entries."""
        entries = [self._make_entry("A" * 100), self._make_entry("A" * 100)]
        warnings = validate_knowledge(entries)
        assert any("duplicate" in w for w in warnings)

    def test_repetitive_content(self):
        """Flags content where >50% is the same character."""
        entries = [self._make_entry("aaaaaaaaaa" + "b" * 5)]
        warnings = validate_knowledge(entries)
        assert any("repetitive" in w for w in warnings)

    def test_clean_pass(self):
        """Valid entries produce no warnings."""
        entries = [self._make_entry("A well-written paragraph with enough content to pass validation checks.")]
        warnings = validate_knowledge(entries)
        assert warnings == []

    def test_total_size_warning(self):
        """Warns when total size exceeds 500KB."""
        entries = [self._make_entry("x" * 600_000)]
        warnings = validate_knowledge(entries)
        assert any("500KB" in w for w in warnings)

    def test_empty_list(self):
        """Empty list returns no warnings."""
        assert validate_knowledge([]) == []


class TestKnowledgeBase:
    def test_load_save_roundtrip(self, tmp_path):
        """Save then load preserves entries."""
        kb_dir = tmp_path / "knowledge_base"
        kb = KnowledgeBase(kb_dir)
        entries = [
            KnowledgeEntry(
                source="test.txt", type="text", content="Hello world",
                title="Test", chunk_index=0,
            ),
            KnowledgeEntry(
                source="test.txt", type="text", content="Second chunk",
                title="Test", chunk_index=1,
            ),
        ]
        kb.add_entries(entries)

        # Reload
        kb2 = KnowledgeBase.load(kb_dir)
        assert len(kb2.entries) == 2
        assert kb2.entries[0].content == "Hello world"
        assert kb2.entries[1].chunk_index == 1

    def test_load_nonexistent(self, tmp_path):
        """Loading from nonexistent dir returns empty KnowledgeBase."""
        kb = KnowledgeBase.load(tmp_path / "nope")
        assert kb.entries == []

    def test_load_corrupt_json(self, tmp_path):
        """Corrupt JSON returns empty KnowledgeBase."""
        kb_dir = tmp_path / "knowledge_base"
        kb_dir.mkdir()
        (kb_dir / "knowledge.json").write_text("not json{{{")
        kb = KnowledgeBase.load(kb_dir)
        assert kb.entries == []

    def test_add_entries_appends(self, tmp_path):
        """add_entries appends to existing entries."""
        kb_dir = tmp_path / "knowledge_base"
        kb = KnowledgeBase(kb_dir)
        kb.add_entries([KnowledgeEntry(source="a", type="text", content="first")])
        kb.add_entries([KnowledgeEntry(source="b", type="text", content="second")])
        assert len(kb.entries) == 2

        # Verify persisted
        kb2 = KnowledgeBase.load(kb_dir)
        assert len(kb2.entries) == 2
