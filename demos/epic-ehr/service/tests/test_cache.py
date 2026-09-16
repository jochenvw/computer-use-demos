import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from epic_adapter.audit import AuditWriter
from epic_adapter.cache import RetrievalCache
from epic_adapter.jobs import JobService
from epic_adapter.models import ClinicalBundle, RetrievalRequest


def wait(job):
    for _ in range(200):
        if job.status in {"complete", "failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError("Job did not finish.")


class CacheTests(unittest.TestCase):
    def test_ttl_lru_bytes_and_deep_copy(self):
        clock = Mock(return_value=0)
        cache = RetrievalCache(max_entries=2, ttl_seconds=5, max_bytes=200, clock=clock)
        bundle = ClinicalBundle(patient_id="P1", resources=[], files=[])
        cache.put(("a",), bundle)
        bundle.patient_id = "mutated"
        self.assertEqual("P1", cache.get(("a",)).bundle.patient_id)
        cache.get(("a",)).bundle.patient_id = "also-mutated"
        self.assertEqual("P1", cache.get(("a",)).bundle.patient_id)
        cache.put(("b",), bundle)
        cache.get(("a",))
        cache.put(("c",), bundle)
        self.assertIsNone(cache.get(("b",)))
        clock.return_value = 5
        self.assertIsNone(cache.get(("a",)))
        self.assertIsNone(cache.get(("c",)))
        tiny = RetrievalCache(max_bytes=1)
        entry = tiny.put(("a",), bundle)
        self.assertIsNone(tiny.get(("a",)))
        self.assertEqual(entry.collected_at, entry.expires_at)

    def test_total_byte_budget_evicts_lru_entries(self):
        cache = RetrievalCache(max_entries=10, ttl_seconds=60, max_bytes=80)
        bundle = ClinicalBundle(patient_id="P1", resources=[], files=[])
        cache.put(("a",), bundle)
        cache.put(("b",), bundle)
        self.assertIsNone(cache.get(("a",)))
        self.assertIsNotNone(cache.get(("b",)))

    def test_key_is_scoped_and_order_independent(self):
        request = RetrievalRequest(patient_id="P1", resources=["ecg", "patient"])
        key = RetrievalCache.key(request, "caller", "backend")
        self.assertEqual(key, RetrievalCache.key(request.model_copy(update={
            "resources": list(reversed(request.resources)), "bypass_cache": True,
        }), "caller", "backend"))
        for updated, caller, backend in [
            ({"patient_id": "P2"}, "caller", "backend"),
            ({}, "other", "backend"), ({}, "caller", "other"),
            ({"observation_codes": ["85354-9"]}, "caller", "backend"),
        ]:
            self.assertNotEqual(key, RetrievalCache.key(
                request.model_copy(update=updated), caller, backend,
            ))
        self.assertNotEqual(key, RetrievalCache.key(
            RetrievalRequest(patient_id="P1", source="ehr", resources=["ecg", "patient"]),
            "caller", "backend",
        ))

    def test_job_hit_bypass_failure_and_concurrent_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter, catalog = Mock(), Mock()
            adapter.retrieve.return_value = []
            catalog.find.return_value = []
            jobs = JobService(adapter, catalog, AuditWriter(Path(directory) / "audit.jsonl"))
            request = RetrievalRequest(patient_id="P1")
            first = wait(jobs.create(request, "caller"))
            self.assertEqual("miss", first.cache_status)
            second = wait(jobs.create(request, "caller"))
            self.assertEqual("hit", second.cache_status)
            self.assertEqual(first.collected_at, second.collected_at)
            self.assertEqual(1, adapter.retrieve.call_count)
            self.assertEqual(1, catalog.find.call_count)
            bypass = request.model_copy(update={"bypass_cache": True})
            fresh = wait(jobs.create(bypass, "caller"))
            self.assertEqual("bypass", fresh.cache_status)
            self.assertEqual(2, adapter.retrieve.call_count)
            after = wait(jobs.create(request, "caller"))
            self.assertEqual(fresh.collected_at, after.collected_at)
            adapter.retrieve.side_effect = RuntimeError("synthetic")
            failed = wait(jobs.create(bypass, "caller"))
            self.assertEqual("failed", failed.status)
            self.assertIsNone(failed.bundle)
            self.assertEqual("failed", wait(jobs.create(request, "caller")).status)
            adapter.retrieve.side_effect = None
            adapter.retrieve.reset_mock()
            catalog.find.reset_mock()
            a, b = jobs.create(request, "other"), jobs.create(request, "other")
            self.assertEqual("complete", wait(a).status)
            self.assertEqual("complete", wait(b).status)
            self.assertEqual({"miss", "hit"}, {a.cache_status, b.cache_status})
            adapter.retrieve.assert_called_once()
            catalog.find.assert_called_once()

    def test_job_refetches_after_actual_ttl_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = Mock(return_value=0)
            adapter, catalog = Mock(), Mock()
            adapter.retrieve.return_value = []
            catalog.find.return_value = []
            jobs = JobService(
                adapter, catalog, AuditWriter(Path(directory) / "audit.jsonl"),
                cache=RetrievalCache(ttl_seconds=1, clock=clock),
            )
            request = RetrievalRequest(patient_id="P1", source="ehr")
            self.assertEqual("miss", wait(jobs.create(request, "caller")).cache_status)
            self.assertEqual("hit", wait(jobs.create(request, "caller")).cache_status)
            clock.return_value = 1
            self.assertEqual("miss", wait(jobs.create(request, "caller")).cache_status)
            self.assertEqual(2, adapter.retrieve.call_count)
            catalog.find.assert_not_called()

    def test_file_skill_is_cached_without_any_catalog_or_model_work_on_hit(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter, catalog, file_skill = Mock(), Mock(), Mock()
            file_skill.return_value = ClinicalBundle(patient_id="P1", resources=[], files=[])
            jobs = JobService(
                adapter, catalog, AuditWriter(Path(directory) / "audit.jsonl"),
                file_retriever=file_skill, backend_scope="copilot",
            )
            request = RetrievalRequest(patient_id="P1", source="files", resources=["ecg"])
            self.assertEqual("miss", wait(jobs.create(request, "caller")).cache_status)
            self.assertEqual("hit", wait(jobs.create(request, "caller")).cache_status)
            file_skill.assert_called_once()
            adapter.retrieve.assert_not_called()
            catalog.find.assert_not_called()

    def test_live_file_skill_failure_does_not_fall_back_to_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter, catalog, file_skill = Mock(), Mock(), Mock()
            file_skill.side_effect = RuntimeError("synthetic")
            jobs = JobService(
                adapter, catalog, AuditWriter(Path(directory) / "audit.jsonl"),
                file_retriever=file_skill, backend_scope="copilot",
            )
            request = RetrievalRequest(patient_id="P1", source="files", resources=["ecg"])
            self.assertEqual("failed", wait(jobs.create(request, "caller")).status)
            file_skill.assert_called_once()
            adapter.retrieve.assert_not_called()
            catalog.find.assert_not_called()
