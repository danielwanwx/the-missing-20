"""Resume authorized receipt *drafts* after interruption; never post inventory."""

from contextlib import suppress
from threading import Event, Thread

from the_missing_20.adapters.photo_receiving import PhotoReceiving


class ReceivingDraftWorker:
    def __init__(self, receiving: PhotoReceiving) -> None:
        self.receiving = receiving
        self.closed = Event()
        self.thread: Thread | None = None

    def start(self) -> None:
        if not self.receiving.auto_prepare or self.thread is not None:
            return
        self.thread = Thread(target=self._run, name="receiving-drafts", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.closed.is_set():
            with suppress(ValueError):
                self.receiving.prepare_next_draft()
            if self.closed.wait(30):
                return

    def close(self) -> None:
        self.closed.set()
        if self.thread is not None:
            self.thread.join(timeout=1)
