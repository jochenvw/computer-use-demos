import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class ReleaseAssetTests(unittest.TestCase):
    def test_workflow_is_tagged_signed_and_least_privilege(self):
        workflow = (ROOT / ".github/workflows/epic-release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('tags:\n      - "epic-v*"', workflow)
        self.assertIn("sigstore/cosign-installer@v3.10.0", workflow)
        self.assertIn("cosign sign-blob", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertNotIn("attestations: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)

    def test_launcher_verifies_exact_release_and_drains_before_update(self):
        launcher = (
            ROOT / "demos/epic-ehr/launcher/Start-EpicDemo.ps1"
        ).read_text(encoding="utf-8")
        bootstrap = (
            ROOT / "demos/epic-ehr/launcher/Bootstrap-EpicDemo.ps1"
        ).read_text(encoding="utf-8")
        installer = (
            ROOT / "demos/epic-ehr/infra/install-agent.ps1"
        ).read_text(encoding="utf-8")
        live_launcher = (
            ROOT / "demos/epic-ehr/service/live.ps1"
        ).read_text(encoding="utf-8")
        tunnel_host = (
            ROOT / "demos/epic-ehr/infra/host-demo-tunnel.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("cosign verify-blob", launcher)
        self.assertIn("--certificate-identity", launcher)
        self.assertIn("cosign-windows-amd64", launcher)
        self.assertIn(r"Microsoft\WinGet\Links", bootstrap)
        self.assertIn("Sigstore.Cosign_*", launcher)
        self.assertIn("Sigstore.Cosign_*", bootstrap)
        self.assertIn("$cosign = Get-CosignPath", bootstrap)
        self.assertNotIn("$LASTEXITCODE -ne 0", bootstrap)
        self.assertIn("--native-tls", launcher)
        self.assertIn("$attempt -le 5", launcher)
        self.assertIn("--native-tls", installer)
        self.assertIn("$attempt -le 5", installer)
        self.assertIn("Epic Live Demo", installer)
        self.assertIn("browser.ps1", live_launcher)
        self.assertIn("run.ps1", live_launcher)
        self.assertNotIn("-WithTunnel", live_launcher)
        self.assertIn("/v1/admin/drain", launcher)
        self.assertIn("Approved channel", launcher)
        self.assertNotIn("/releases/latest", launcher)
        self.assertNotIn("Set-Content -LiteralPath $envFile", launcher)
        self.assertIn("EpicDemoRemoteApiTunnel", tunnel_host)
        self.assertIn("Unregister-ScheduledTask", tunnel_host)

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
