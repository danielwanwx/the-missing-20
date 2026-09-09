from __future__ import annotations

import base64
import hashlib
import io
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from the_missing_20.adapters.photo_receiving import PhotoReceiving


def _photo(color: str) -> str:
    payload = io.BytesIO()
    Image.new("RGB", (80, 80), color).save(payload, format="PNG")
    return base64.b64encode(payload.getvalue()).decode()


def _reader(_photo: bytes) -> dict[str, Any]:
    return {
        "assessment": {
            "visibility": "clear",
            "countable": True,
            "objects": [{"x": 0.5, "y": 0.5, "description": "one carton"}],
            "receiving_unit": "carton",
            "item_code": "",
            "supplier_lot": "",
            "label_declared_quantity": None,
            "issues": [],
            "visible_condition": "no_visible_damage",
            "next_photo": "",
        }
    }


class _ConcurrentReader(PhotoReceiving):
    """Pause the first public read so two service instances start at one version."""

    def __init__(
        self,
        database: Path,
        barrier: threading.Barrier,
        reader: Any = _reader,
    ) -> None:
        super().__init__(database, reader)
        self._barrier = barrier
        self._gate_lock = threading.Lock()
        self._gate_open = True

    def current(self, capture_id: str) -> dict[str, Any]:
        state = super().current(capture_id)
        with self._gate_lock:
            wait = self._gate_open and threading.current_thread() is not threading.main_thread()
            if wait:
                self._gate_open = False
        if wait:
            self._barrier.wait(timeout=5)
        return state


def test_concurrent_upload_is_atomic_and_does_not_leak_a_writer_lock(tmp_path: Path) -> None:
    database = tmp_path / "photo-receiving.sqlite3"
    barrier = threading.Barrier(2)
    first = _ConcurrentReader(database, barrier)
    capture_id = first.create()["id"]
    second = _ConcurrentReader(database, barrier)
    outcomes: list[tuple[PhotoReceiving, dict[str, Any] | Exception]] = []

    def upload(receiver: PhotoReceiving, image: str) -> None:
        try:
            outcomes.append((receiver, receiver.upload(capture_id, image)))
        except Exception as error:  # The public boundary must return a reload conflict, not SQLite.
            outcomes.append((receiver, error))

    threads = [
        threading.Thread(target=upload, args=(first, _photo("red"))),
        threading.Thread(target=upload, args=(second, _photo("blue"))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    successes = [(receiver, value) for receiver, value in outcomes if isinstance(value, dict)]
    conflicts = [(receiver, value) for receiver, value in outcomes if isinstance(value, Exception)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert isinstance(conflicts[0][1], ValueError)
    assert "reload" in str(conflicts[0][1]).lower()

    winner = first.current(capture_id)
    assert hashlib.sha256(first.image(capture_id)).hexdigest() == winner["digest"]
    assert hashlib.sha256(second.image(capture_id)).hexdigest() == winner["digest"]

    # The losing connection rolled its transaction back and releases SQLite's writer lock.
    loser = conflicts[0][0]
    recovered = loser.upload(capture_id, _photo("green"))
    assert recovered["version"] > winner["version"]
    assert hashlib.sha256(first.image(capture_id)).hexdigest() == recovered["digest"]
    assert hashlib.sha256(second.image(capture_id)).hexdigest() == recovered["digest"]
    assert len(first.history(capture_id)["versions"]) == 2


def test_starting_another_instance_does_not_interrupt_active_analysis(tmp_path: Path) -> None:
    database = tmp_path / "photo-receiving.sqlite3"
    reader_started = threading.Event()
    release_reader = threading.Event()
    reader_calls = 0

    def blocking_reader(image: bytes) -> dict[str, Any]:
        nonlocal reader_calls
        reader_calls += 1
        reader_started.set()
        assert release_reader.wait(timeout=30)
        return _reader(image)

    first = PhotoReceiving(database, blocking_reader)
    capture_id = first.create()["id"]
    outcomes: list[dict[str, Any] | Exception] = []

    def upload() -> None:
        try:
            outcomes.append(first.upload(capture_id, _photo("red")))
        except Exception as error:
            outcomes.append(error)

    thread = threading.Thread(target=upload)
    thread.start()
    assert reader_started.wait(timeout=5)

    second = PhotoReceiving(database, _reader)
    assert second.current(capture_id)["status"] == "ANALYZING"
    release_reader.set()
    thread.join(timeout=10)
    assert not thread.is_alive()

    assert len(outcomes) == 1 and isinstance(outcomes[0], dict)
    completed = second.current(capture_id)
    assert completed["status"] == "COUNT_CANDIDATE"
    assert completed["digest"] == outcomes[0]["digest"]
    assert "analysis_claim" not in completed and "analysis_claim" not in outcomes[0]
    assert hashlib.sha256(second.image(capture_id)).hexdigest() == completed["digest"]
    assert reader_calls == 1


def test_abandoned_analysis_is_recovered_after_its_lease_expires(tmp_path: Path) -> None:
    database = tmp_path / "photo-receiving.sqlite3"
    first = PhotoReceiving(database, _reader)
    state = first.create()
    state["analysis_claim"] = {
        "owner": "abandoned-worker",
        "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    first._event(state, "ANALYZING", "model running")
    first.db.close()

    restarted = PhotoReceiving(database, _reader)
    recovered = restarted.current(state["id"])
    assert recovered["status"] == "UNAVAILABLE"
    assert "analysis_claim" not in recovered


def test_expired_owner_cannot_overwrite_new_photo_evidence(
    tmp_path: Path, monkeypatch: Any
) -> None:
    database = tmp_path / "photo-receiving.sqlite3"
    reader_started = threading.Event()
    release_reader = threading.Event()
    old_reader_calls = 0
    new_reader_calls = 0

    def old_reader(image: bytes) -> dict[str, Any]:
        nonlocal old_reader_calls
        old_reader_calls += 1
        reader_started.set()
        assert release_reader.wait(timeout=30)
        return _reader(image)

    def new_reader(image: bytes) -> dict[str, Any]:
        nonlocal new_reader_calls
        new_reader_calls += 1
        return _reader(image)

    monkeypatch.setattr(
        "the_missing_20.adapters.photo_receiving.ANALYSIS_LEASE_SECONDS", 0
    )
    first = PhotoReceiving(database, old_reader)
    capture_id = first.create()["id"]
    old_outcomes: list[dict[str, Any] | Exception] = []

    def old_upload() -> None:
        try:
            old_outcomes.append(first.upload(capture_id, _photo("red")))
        except Exception as error:
            old_outcomes.append(error)

    thread = threading.Thread(target=old_upload)
    thread.start()
    assert reader_started.wait(timeout=5)

    second = PhotoReceiving(database, new_reader)
    assert second.current(capture_id)["status"] == "UNAVAILABLE"
    replacement = second.upload(capture_id, _photo("blue"))
    replacement_digest = replacement["digest"]

    release_reader.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert len(old_outcomes) == 1 and isinstance(old_outcomes[0], ValueError)

    current = second.current(capture_id)
    assert current == replacement
    assert hashlib.sha256(second.image(capture_id)).hexdigest() == replacement_digest
    assert [item["digest"] for item in second.history(capture_id)["versions"]] == [
        hashlib.sha256(first.historical_image(capture_id, 1)).hexdigest(),
        replacement_digest,
    ]
    assert old_reader_calls == new_reader_calls == 1


def test_same_photo_concurrency_runs_reader_once(tmp_path: Path) -> None:
    database = tmp_path / "photo-receiving.sqlite3"
    barrier = threading.Barrier(2)
    calls = 0
    calls_lock = threading.Lock()

    def counting_reader(image: bytes) -> dict[str, Any]:
        nonlocal calls
        with calls_lock:
            calls += 1
        return _reader(image)

    first = _ConcurrentReader(database, barrier, counting_reader)
    capture_id = first.create()["id"]
    second = _ConcurrentReader(database, barrier, counting_reader)
    outcomes: list[dict[str, Any] | Exception] = []
    image = _photo("red")

    def upload(receiver: PhotoReceiving) -> None:
        try:
            outcomes.append(receiver.upload(capture_id, image))
        except Exception as error:
            outcomes.append(error)

    threads = [threading.Thread(target=upload, args=(receiver,)) for receiver in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert sum(isinstance(value, dict) for value in outcomes) == 1
    assert sum(isinstance(value, ValueError) for value in outcomes) == 1
    assert calls == 1
    assert len(first.history(capture_id)["versions"]) == 1


def test_fresh_crash_claim_recovers_on_same_photo_retry_after_expiry(
    tmp_path: Path, monkeypatch: Any
) -> None:
    class SimulatedProcessCrash(BaseException):
        pass

    class ControlledDateTime(datetime):
        current = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)

        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return cls.current

    monkeypatch.setattr(
        "the_missing_20.adapters.photo_receiving.datetime", ControlledDateTime
    )
    database = tmp_path / "photo-receiving.sqlite3"
    image = _photo("red")
    crashed_reader_calls = 0

    def crashing_reader(_image: bytes) -> dict[str, Any]:
        nonlocal crashed_reader_calls
        crashed_reader_calls += 1
        raise SimulatedProcessCrash

    first = PhotoReceiving(database, crashing_reader)
    capture_id = first.create()["id"]
    with pytest.raises(SimulatedProcessCrash):
        first.upload(capture_id, image)
    assert first.current(capture_id)["status"] == "ANALYZING"
    first.db.close()

    retry_reader_calls = 0

    def retry_reader(payload: bytes) -> dict[str, Any]:
        nonlocal retry_reader_calls
        retry_reader_calls += 1
        return _reader(payload)

    ControlledDateTime.current += timedelta(seconds=30)
    restarted = PhotoReceiving(database, retry_reader)
    assert restarted.current(capture_id)["status"] == "ANALYZING"

    ControlledDateTime.current += timedelta(seconds=61)
    completed = restarted.upload(capture_id, image)
    assert completed["status"] == "COUNT_CANDIDATE"
    assert "analysis_claim" not in completed
    assert hashlib.sha256(restarted.image(capture_id)).hexdigest() == completed["digest"]
    history = restarted.history(capture_id)["versions"]
    assert len(history) == 2
    assert [entry["digest"] for entry in history] == [completed["digest"]] * 2
    assert crashed_reader_calls == retry_reader_calls == 1
