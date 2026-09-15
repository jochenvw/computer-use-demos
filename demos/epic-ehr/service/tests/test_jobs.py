import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from epic_adapter.audit import AuditWriter
from epic_adapter.file_catalog import FileCatalog
from epic_adapter.jobs import JobService
from epic_adapter.models import RetrievalRequest


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
