import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class ReleaseAssetTests(unittest.TestCase):
    def test_workflow_is_tagged_attested_and_least_privilege(self):
        workflow = (ROOT / ".github/workflows/epic-release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('tags:\n      - "epic-v*"', workflow)
        self.assertIn("actions/attest-build-provenance@v3", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)

    def test_launcher_verifies_exact_release_and_drains_before_update(self):
        launcher = (
            ROOT / "demos/epic-ehr/launcher/Start-EpicDemo.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("gh attestation verify", launcher)
        self.assertIn("/v1/admin/drain", launcher)
        self.assertIn("Approved channel", launcher)
        self.assertNotIn("/releases/latest", launcher)
        self.assertNotIn("Set-Content -LiteralPath $envFile", launcher)

    def test_archive_builder_uses_tracked_files_and_blocks_runtime_state(self):
        builder = (
            ROOT / "demos/epic-ehr/release/build-release.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("git -C $repositoryRoot ls-files", builder)
        for forbidden in (r"\.env", r"audit\.jsonl", "BrowserProfile", r"\.venv"):
            self.assertIn(forbidden, builder)
        self.assertIn("dependencyLockSha256", builder)


if __name__ == "__main__":
    unittest.main()
