"""Tests for framework/events.py — event log and pub/sub."""

import threading

import pytest

from framework.events import Event, EventLog


@pytest.fixture
def event_log(tmp_path):
    return EventLog(tmp_path / "data" / "events.json")


class TestEventLog:
    def test_event_auto_timestamp(self, event_log):
        """Empty timestamp is auto-filled on emit."""
        event = Event(type="test.event", source="test")
        event_log.emit(event)
        assert event.timestamp != ""
        results = event_log.query()
        assert len(results) == 1
        assert results[0]["timestamp"] != ""

    def test_event_explicit_timestamp(self, event_log):
        """Explicit timestamp is preserved."""
        event = Event(type="test.event", source="test", timestamp="2026-01-01T00:00:00Z")
        event_log.emit(event)
        results = event_log.query()
        assert results[0]["timestamp"] == "2026-01-01T00:00:00Z"

    def test_emit_persists(self, event_log):
        """Emitted event is found in TinyDB."""
        event = Event(type="task.done", source="worker:alice", data={"result": "ok"})
        event_log.emit(event)
        results = event_log.query()
        assert len(results) == 1
        assert results[0]["type"] == "task.done"
        assert results[0]["source"] == "worker:alice"
        assert results[0]["data"]["result"] == "ok"

    def test_emit_dispatches_handler(self, event_log):
        """Handler is called with the correct Event."""
        received = []
        event_log.on("task.done", lambda e: received.append(e))
        event = Event(type="task.done", source="test", data={"x": 1})
        event_log.emit(event)
        assert len(received) == 1
        assert received[0].type == "task.done"
        assert received[0].data == {"x": 1}

    def test_handler_exception_swallowed(self, event_log):
        """Bad handler doesn't prevent persistence or other handlers."""
        good_received = []

        def bad_handler(e):
            raise RuntimeError("boom")

        event_log.on("test.event", bad_handler)
        event_log.on("test.event", lambda e: good_received.append(e))
        event = Event(type="test.event", source="test")
        event_log.emit(event)

        # Event still persisted
        assert len(event_log.query()) == 1
        # Good handler still called
        assert len(good_received) == 1

    def test_wildcard_handler(self, event_log):
        """'*' handler receives all event types."""
        received = []
        event_log.on("*", lambda e: received.append(e.type))
        event_log.emit(Event(type="a", source="test"))
        event_log.emit(Event(type="b", source="test"))
        assert received == ["a", "b"]

    def test_off_removes_handler(self, event_log):
        """Removed handler is not called on subsequent emits."""
        received = []
        handler = lambda e: received.append(e)
        event_log.on("test.event", handler)
        event_log.emit(Event(type="test.event", source="test"))
        assert len(received) == 1

        event_log.off("test.event", handler)
        event_log.emit(Event(type="test.event", source="test"))
        assert len(received) == 1  # not called again

    def test_query_by_type(self, event_log):
        """Filter by event type returns only matching events."""
        event_log.emit(Event(type="a", source="test"))
        event_log.emit(Event(type="b", source="test"))
        event_log.emit(Event(type="a", source="test"))
        results = event_log.query(event_type="a")
        assert len(results) == 2
        assert all(r["type"] == "a" for r in results)

    def test_query_by_source(self, event_log):
        """Filter by source returns only matching events."""
        event_log.emit(Event(type="x", source="alpha"))
        event_log.emit(Event(type="x", source="beta"))
        results = event_log.query(source="alpha")
        assert len(results) == 1
        assert results[0]["source"] == "alpha"

    def test_query_limit(self, event_log):
        """Limit caps results, newest first."""
        for i in range(10):
            event_log.emit(Event(
                type="seq", source="test",
                data={"i": i},
                timestamp=f"2026-01-01T00:00:{i:02d}Z",
            ))
        results = event_log.query(limit=3)
        assert len(results) == 3
        # Newest first
        assert results[0]["data"]["i"] == 9
        assert results[1]["data"]["i"] == 8
        assert results[2]["data"]["i"] == 7


class TestEventLogThreadSafety:
    def test_concurrent_emits(self, event_log):
        """10 threads emitting simultaneously — no corruption."""
        errors = []

        def emitter(i):
            try:
                event_log.emit(Event(type="test", source=f"thread-{i}", data={"i": i}))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=emitter, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(event_log.query(limit=100)) == 10

    def test_concurrent_reads_during_emits(self, event_log):
        """Readers get consistent data while emitters are active."""
        event_log.emit(Event(type="seed", source="test"))
        errors = []

        def reader():
            try:
                results = event_log.query(limit=100)
                assert len(results) >= 1  # at least the seed
            except Exception as e:
                errors.append(e)

        def emitter(i):
            try:
                event_log.emit(Event(type="test", source=f"thread-{i}"))
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=reader) for _ in range(5)]
            + [threading.Thread(target=emitter, args=(i,)) for i in range(5)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

    def test_lock_prevents_corruption(self, event_log):
        """After concurrent ops, event count matches expected."""
        def emitter(i):
            event_log.emit(Event(type="test", source=f"t-{i}"))

        threads = [threading.Thread(target=emitter, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(event_log.query(limit=100)) == 20
