"""Tests for framework/validation.py — input validation, rate limiting, safe JSON I/O."""

import json
import time
from pathlib import Path

import pytest

from framework.exceptions import ValidationError
from framework.validation import (
    RateLimiter,
    safe_load_json,
    safe_write_json,
    validate_path_within,
    validate_payload_size,
    validate_worker_name,
)


class TestValidateWorkerName:
    def test_valid_simple(self):
        assert validate_worker_name("alice") == "alice"

    def test_valid_with_hyphens(self):
        assert validate_worker_name("data-analyst") == "data-analyst"

    def test_valid_with_underscores(self):
        assert validate_worker_name("content_writer") == "content_writer"

    def test_valid_with_numbers(self):
        assert validate_worker_name("worker1") == "worker1"

    def test_valid_single_char(self):
        assert validate_worker_name("a") == "a"

    def test_empty_string_raises(self):
        with pytest.raises(ValidationError, match="non-empty"):
            validate_worker_name("")

    def test_none_raises(self):
        with pytest.raises(ValidationError, match="non-empty"):
            validate_worker_name(None)

    def test_path_traversal_raises(self):
        with pytest.raises(ValidationError, match="Invalid worker name"):
            validate_worker_name("../etc/passwd")

    def test_slashes_raise(self):
        with pytest.raises(ValidationError, match="Invalid worker name"):
            validate_worker_name("foo/bar")

    def test_null_bytes_raise(self):
        with pytest.raises(ValidationError, match="Invalid worker name"):
            validate_worker_name("alice\x00evil")

    def test_too_long_raises(self):
        with pytest.raises(ValidationError, match="Invalid worker name"):
            validate_worker_name("a" * 65)

    def test_leading_hyphen_raises(self):
        with pytest.raises(ValidationError, match="Invalid worker name"):
            validate_worker_name("-alice")

    def test_leading_underscore_raises(self):
        with pytest.raises(ValidationError, match="Invalid worker name"):
            validate_worker_name("_alice")

    def test_special_chars_raise(self):
        with pytest.raises(ValidationError, match="Invalid worker name"):
            validate_worker_name("alice@home")

    def test_max_length_valid(self):
        name = "a" * 64
        assert validate_worker_name(name) == name


class TestValidatePathWithin:
    def test_within_project(self, tmp_path):
        child = tmp_path / "workers" / "alice"
        child.mkdir(parents=True, exist_ok=True)
        result = validate_path_within(child, tmp_path)
        assert str(result).startswith(str(tmp_path.resolve()))

    def test_absolute_escape(self, tmp_path):
        with pytest.raises(ValidationError, match="outside project"):
            validate_path_within(Path("/etc/passwd"), tmp_path)

    def test_relative_escape(self, tmp_path):
        escape = tmp_path / ".." / ".." / "etc" / "passwd"
        with pytest.raises(ValidationError, match="outside project"):
            validate_path_within(escape, tmp_path)

    def test_exact_root(self, tmp_path):
        result = validate_path_within(tmp_path, tmp_path)
        assert result == tmp_path.resolve()


class TestValidatePayloadSize:
    def test_within_limit(self):
        validate_payload_size(b"hello")  # no exception

    def test_at_limit(self):
        validate_payload_size(b"x" * 100, max_bytes=100)  # no exception

    def test_over_limit(self):
        with pytest.raises(ValidationError, match="too large"):
            validate_payload_size(b"x" * 101, max_bytes=100)

    def test_custom_limit(self):
        validate_payload_size(b"x" * 500, max_bytes=1000)
        with pytest.raises(ValidationError, match="too large"):
            validate_payload_size(b"x" * 1001, max_bytes=1000)


class TestRateLimiter:
    def test_allows_within_limit(self):
        rl = RateLimiter(rate=10, burst=5)
        for _ in range(5):
            assert rl.allow("client1") is True

    def test_blocks_over_limit(self):
        rl = RateLimiter(rate=10, burst=3)
        for _ in range(3):
            assert rl.allow("client1") is True
        assert rl.allow("client1") is False

    def test_refills_over_time(self):
        rl = RateLimiter(rate=100, burst=2)
        assert rl.allow("c") is True
        assert rl.allow("c") is True
        assert rl.allow("c") is False
        time.sleep(0.05)  # 100 tokens/sec * 0.05s = 5 tokens refilled
        assert rl.allow("c") is True

    def test_independent_keys(self):
        rl = RateLimiter(rate=10, burst=2)
        assert rl.allow("a") is True
        assert rl.allow("a") is True
        assert rl.allow("a") is False
        # Different key still has full burst
        assert rl.allow("b") is True

    def test_cleanup(self):
        rl = RateLimiter(rate=10, burst=5)
        rl.allow("old")
        # Manually age the entry
        with rl._lock:
            rl._buckets["old"][1] -= 7200  # 2 hours ago
        evicted = rl.cleanup(max_age=3600)
        assert evicted == 1
        assert "old" not in rl._buckets


class TestSafeLoadJson:
    def test_valid_file(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text(json.dumps([{"key": "value"}]))
        result = safe_load_json(p)
        assert result == [{"key": "value"}]

    def test_missing_file(self, tmp_path):
        result = safe_load_json(tmp_path / "nope.json")
        assert result == []

    def test_corrupted_backup(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{broken json!!!")
        result = safe_load_json(p, default=[], warn=False)
        assert result == []
        assert (tmp_path / "bad.json.corrupt").exists()

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("")
        result = safe_load_json(p, default={"fallback": True})
        assert result == {"fallback": True}


class TestSafeWriteJson:
    def test_creates_file(self, tmp_path):
        p = tmp_path / "output.json"
        safe_write_json(p, [1, 2, 3])
        assert p.exists()
        assert json.loads(p.read_text()) == [1, 2, 3]

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "sub" / "dir" / "data.json"
        safe_write_json(p, {"nested": True})
        assert p.exists()

    def test_roundtrip(self, tmp_path):
        p = tmp_path / "rt.json"
        data = [{"name": "alice", "score": 4.5}, {"name": "bob", "score": 3.0}]
        safe_write_json(p, data)
        loaded = safe_load_json(p)
        assert loaded == data
