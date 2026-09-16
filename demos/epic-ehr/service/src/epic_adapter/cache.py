from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from .models import ClinicalBundle, RetrievalRequest


@dataclass
class CacheEntry:
    bundle: ClinicalBundle
    collected_at: datetime
    expires_at: datetime
    deadline: float
    size: int


class RetrievalCache:
    """Format-neutral LRU; access is serialized by the job service's retrieval lock."""

    def __init__(
        self, *, max_entries: int = 16, ttl_seconds: int = 900,
        max_bytes: int = 8 * 1024 * 1024, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min(max_entries, ttl_seconds, max_bytes) <= 0:
            raise ValueError("Cache limits must be positive.")
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.max_bytes = max_bytes
        self._clock = clock
        self._entries: OrderedDict[tuple, CacheEntry] = OrderedDict()
        self._total_bytes = 0

    @staticmethod
    def key(request: RetrievalRequest, caller: str, backend: str) -> tuple:
        return (
            caller, backend, request.patient_id, request.source.value,
            tuple(sorted({value.value for value in request.resources})),
            tuple(sorted(set(request.observation_codes))),
        )

    def invalidate(self, key: tuple) -> None:
        self._drop(key)

    def get(self, key: tuple) -> CacheEntry | None:
        self._expire()
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)
            return self._copy(entry)
        return None

    def _expire(self) -> None:
        now = self._clock()
        for key, entry in list(self._entries.items()):
            if entry.deadline <= now:
                self._drop(key)

    def _drop(self, key: tuple) -> None:
        entry = self._entries.pop(key, None)
        if entry is not None:
            self._total_bytes -= entry.size

    @staticmethod
    def _copy(entry: CacheEntry) -> CacheEntry:
        return CacheEntry(
            entry.bundle.model_copy(deep=True), entry.collected_at,
            entry.expires_at, entry.deadline, entry.size,
        )

    def put(self, key: tuple, bundle: ClinicalBundle) -> CacheEntry:
        self._expire()
        self.invalidate(key)
        now = datetime.now(timezone.utc)
        # Include hidden paths in the budget, but never expose them in API output.
        size = len(bundle.model_dump_json().encode()) + sum(
            len(file.path.encode()) for file in bundle.files
        )
        entry = CacheEntry(
            bundle.model_copy(deep=True), now,
            now + timedelta(seconds=self.ttl_seconds),
            self._clock() + self.ttl_seconds, size,
        )
        if size <= self.max_bytes:
            self._entries[key] = entry
            self._total_bytes += size
            while len(self._entries) > self.max_entries or self._total_bytes > self.max_bytes:
                _, removed = self._entries.popitem(last=False)
                self._total_bytes -= removed.size
        else:
            # This response is valid, but is not eligible for reuse.
            entry.expires_at = now
        return self._copy(entry)
