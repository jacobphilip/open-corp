"""Tests for framework/db.py — thread-safe TinyDB wrapper."""

import threading

import pytest

from framework.db import _reset_registry, close_all, get_db


@pytest.fixture(autouse=True)
def clean_registry():
    """Reset registry before and after each test."""
    _reset_registry()
    yield
    close_all()


class TestGetDb:
    def test_get_db_returns_tinydb_and_lock(self, tmp_path):
        """Returns a (TinyDB, Lock) tuple."""
        from tinydb import TinyDB
        db, lock = get_db(tmp_path / "test.json")
        assert isinstance(db, TinyDB)
        assert hasattr(lock, "acquire") and hasattr(lock, "release")

    def test_get_db_same_path_same_instance(self, tmp_path):
        """Same path returns the same TinyDB object."""
        db1, lock1 = get_db(tmp_path / "test.json")
        db2, lock2 = get_db(tmp_path / "test.json")
        assert db1 is db2
        assert lock1 is lock2

    def test_get_db_different_paths(self, tmp_path):
        """Different paths return different instances."""
        db1, _ = get_db(tmp_path / "a.json")
        db2, _ = get_db(tmp_path / "b.json")
        assert db1 is not db2

    def test_get_db_creates_parent_dirs(self, tmp_path):
        """Parent directories are auto-created."""
        db_path = tmp_path / "deep" / "nested" / "db.json"
        db, _ = get_db(db_path)
        assert db_path.parent.exists()


class TestCloseAll:
    def test_close_all(self, tmp_path):
        """All instances closed, registry empty."""
        get_db(tmp_path / "a.json")
        get_db(tmp_path / "b.json")
        close_all()
        # After close_all, getting same path creates fresh instance
        db_new, _ = get_db(tmp_path / "a.json")
        # Verify it works (can insert)
        db_new.insert({"test": True})
        assert len(db_new.all()) == 1

    def test_get_db_after_close_all(self, tmp_path):
        """Fresh instance created after close_all."""
        db1, _ = get_db(tmp_path / "test.json")
        db1.insert({"x": 1})
        close_all()
        db2, _ = get_db(tmp_path / "test.json")
        # New instance reads from same file
        assert db1 is not db2

    def test_close_all_idempotent(self, tmp_path):
        """Calling close_all twice doesn't error."""
        get_db(tmp_path / "test.json")
        close_all()
        close_all()  # should not raise


class TestConcurrency:
    def test_concurrent_get_db_same_path(self, tmp_path):
        """10 threads requesting same path all get same instance."""
        results = []
        db_path = tmp_path / "shared.json"

        def get_it():
            db, _ = get_db(db_path)
            results.append(id(db))

        threads = [threading.Thread(target=get_it) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(results)) == 1  # all same object

    def test_concurrent_writes(self, tmp_path):
        """10 threads writing to same DB don't corrupt data."""
        db, lock = get_db(tmp_path / "writes.json")
        errors = []

        def writer(i):
            try:
                with lock:
                    db.insert({"thread": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(db.all()) == 10

    def test_concurrent_read_write(self, tmp_path):
        """Readers + writers concurrently produce consistent results."""
        db, lock = get_db(tmp_path / "rw.json")
        # Seed some data
        with lock:
            for i in range(5):
                db.insert({"val": i})
        errors = []

        def reader():
            try:
                with lock:
                    data = db.all()
                assert isinstance(data, list)
            except Exception as e:
                errors.append(e)

        def writer(i):
            try:
                with lock:
                    db.insert({"val": 100 + i})
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=reader) for _ in range(5)]
            + [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(db.all()) == 10  # 5 seed + 5 writes

    def test_lock_is_per_db(self, tmp_path):
        """Lock on DB A doesn't block DB B."""
        _, lock_a = get_db(tmp_path / "a.json")
        _, lock_b = get_db(tmp_path / "b.json")
        assert lock_a is not lock_b

        # Acquire A, B should still be acquirable
        lock_a.acquire()
        assert lock_b.acquire(timeout=0.1)
        lock_b.release()
        lock_a.release()


class TestResetRegistry:
    def test_reset_registry(self, tmp_path):
        """_reset_registry clears without closing."""
        db1, _ = get_db(tmp_path / "test.json")
        _reset_registry()
        db2, _ = get_db(tmp_path / "test.json")
        assert db1 is not db2
