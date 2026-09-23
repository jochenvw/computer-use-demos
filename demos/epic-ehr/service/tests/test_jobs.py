import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from epic_adapter.audit import AuditWriter
from epic_adapter.file_catalog import FileCatalog
from epic_adapter.jobs import JobService, ServiceDrainingError
from epic_adapter.models import (
    ClinicalBundle,
    ClinicalResource,
    ResourceType,
    RetrievalRequest,
    SourceRecord,
)


class JobRoutingTests(unittest.TestCase):
    def run_job(self, source):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        patient = root / "DEMO-100042"
        patient.mkdir()
        (patient / "ecg.xml").write_text("synthetic")
        self.adapter = Mock()
        self.adapter.retrieve.return_value = []
        self.catalog = Mock(wraps=FileCatalog((root,)))
        self.jobs = JobService(self.adapter, self.catalog, AuditWriter(root / "audit.jsonl"))
        job = self.jobs.create(RetrievalRequest(
            patient_id="DEMO-100042", source=source,
        ), "test")
        for _ in range(100):
            if job.status in {"complete", "failed"}:
                break
            time.sleep(0.01)
        self.assertEqual("complete", job.status)
        return job

    def test_files_only_never_calls_ehr_model(self):
        job = self.run_job("files")
        self.adapter.retrieve.assert_not_called()
        self.assertEqual(1, len(job.bundle.files))

    def test_ehr_only_never_searches_files(self):
        job = self.run_job("ehr")
        self.catalog.find.assert_not_called()
        self.adapter.retrieve.assert_called_once()
        self.assertEqual([], job.bundle.files)

    def test_both_routes_to_both_sources(self):
        self.run_job("both")
        self.adapter.retrieve.assert_called_once()
        self.catalog.find.assert_called_once()

    def test_sql_routes_only_to_database_retriever(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        adapter = Mock()
        database = Mock(return_value=ClinicalBundle(
            patient_id="DEMO-100042", resources=[], files=[],
        ))
        catalog = Mock()
        jobs = JobService(
            adapter,
            catalog,
            AuditWriter(root / "audit.jsonl"),
            database_retriever=database,
        )

        job = jobs.create(RetrievalRequest(
            patient_id="DEMO-100042", source="sql",
        ), "test")
        for _ in range(100):
            if job.status in {"complete", "failed"}:
                break
            time.sleep(0.01)

        self.assertEqual("complete", job.status)
        database.assert_called_once()
        adapter.retrieve.assert_not_called()
        catalog.find.assert_not_called()

    def test_observation_code_filter_ignores_malformed_shapes(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        adapter = Mock()
        adapter.retrieve.return_value = [
            ClinicalResource(
                resource_type=ResourceType.observations,
                source_id="bad",
                data={"code": "85354-9", "component": ["not an object"]},
                provenance=SourceRecord(source="test"),
            ),
            ClinicalResource(
                resource_type=ResourceType.observations,
                source_id="bp",
                data={"component": [{
                    "code": {"coding": [{"code": "85354-9"}]},
                    "valueString": "120/80",
                }]},
                provenance=SourceRecord(source="test"),
            ),
        ]
        jobs = JobService(adapter, Mock(), AuditWriter(root / "audit.jsonl"))
        job = jobs.create(RetrievalRequest(
            patient_id="DEMO-100042", source="ehr",
            resources=["observations"], observation_codes=["85354-9"],
        ), "test")
        for _ in range(100):
            if job.status in {"complete", "failed"}:
                break
            time.sleep(0.01)
        self.assertEqual("complete", job.status)
        self.assertEqual(["bp"], [resource.source_id for resource in job.bundle.resources])

    def test_drain_blocks_new_jobs_after_active_work_finishes(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        release = threading.Event()
        adapter = Mock()
        def retrieve(*_):
            release.wait(2)
            return []
        adapter.retrieve.side_effect = retrieve
        jobs = JobService(adapter, Mock(), AuditWriter(root / "audit.jsonl"))
        job = jobs.create(RetrievalRequest(
            patient_id="DEMO-100042", source="ehr",
        ), "test")
        for _ in range(100):
            if job.status == "running":
                break
            time.sleep(0.01)
        drained = []
        thread = threading.Thread(target=lambda: drained.append(jobs.drain(2)))
        thread.start()
        time.sleep(0.05)
        with self.assertRaises(ServiceDrainingError):
            jobs.create(RetrievalRequest(
                patient_id="DEMO-100042", source="ehr",
            ), "test")
        release.set()
        thread.join(2)
        self.assertEqual([True], drained)
        status = jobs.service_status()
        self.assertFalse(status["accepting_jobs"])
        self.assertEqual(0, status["active_jobs"])
        self.assertGreater(status["process_id"], 0)

    def test_failed_drain_resumes_job_acceptance(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        release = threading.Event()
        adapter = Mock()
        def retrieve(*_):
            release.wait(2)
            return []
        adapter.retrieve.side_effect = retrieve
        jobs = JobService(adapter, Mock(), AuditWriter(root / "audit.jsonl"))
        jobs.create(RetrievalRequest(
            patient_id="DEMO-100042", source="ehr",
        ), "test")
        self.assertFalse(jobs.drain(0.01))
        self.assertTrue(jobs.service_status()["accepting_jobs"])
        release.set()
        for _ in range(100):
            if jobs.service_status()["active_jobs"] == 0:
                break
            time.sleep(0.01)
