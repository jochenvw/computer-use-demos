from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    bearer_token: str
    backend: str
    fixture_root: Path
    file_roots: tuple[Path, ...]
    computer_use_enabled: bool
    browser_window_title: str
    foundry_endpoint: str
    model_deployment: str
    audit_path: Path
    browser_cdp_url: str = "http://127.0.0.1:9222"
    epic_origin: str = ""
    epic_ready_url_prefix: str = ""
    max_browser_steps: int = 40
    skill_timeout_seconds: int = 180
    reasoning_effort: str = "low"
    reasoning_summary: str = "concise"
    cache_ttl_seconds: int = 900
    cache_max_entries: int = 16
    cache_max_bytes: int = 8 * 1024 * 1024
    synthetic_portal_enabled: bool = False
    navigation_hints: bool = False
    visible_file_demo_enabled: bool = False
    ssms_executable: Path = Path(
        r"C:\Program Files (x86)\Microsoft SQL Server Management Studio 20"
        r"\Common7\IDE\Ssms.exe"
    )
    sql_demo_query: Path = Path(r"C:\EpicDemo\shared\Italian Patient Demo.sql")
    asset_roots: tuple[Path, ...] = ()
    diagnostics_dir: Path | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        service_root = Path(__file__).resolve().parents[2]
        fixture_root = Path(
            os.environ.get("EPIC_FIXTURE_ROOT", service_root.parent / "fixtures")
        ).resolve()
        raw_roots = os.environ.get("EPIC_FILE_ROOTS", str(fixture_root / "files"))
        if raw_roots.strip().lower() == "none":
            raw_roots = ""
        file_roots = tuple(
            Path(value.strip()).resolve()
            for value in raw_roots.split(os.pathsep)
            if value.strip()
        )
        return cls(
            bearer_token=os.environ.get("API_BEARER_TOKEN", ""),
            backend=os.environ.get("EPIC_BACKEND", "fixture").lower(),
            fixture_root=fixture_root,
            file_roots=file_roots,
            computer_use_enabled=os.environ.get(
                "EPIC_COMPUTER_USE_ENABLED", ""
            ) == "1",
            browser_window_title=os.environ.get(
                "EPIC_BROWSER_WINDOW_TITLE", ""
            ),
            foundry_endpoint=os.environ.get("AZURE_AI_FOUNDRY_ENDPOINT", ""),
            model_deployment=os.environ.get(
                "MODEL_DEPLOYMENT", "gpt-6-astra"
            ),
            audit_path=Path(
                os.environ.get("EPIC_AUDIT_PATH", service_root / "audit.jsonl")
            ).resolve(),
            browser_cdp_url=os.environ.get(
                "EPIC_BROWSER_CDP_URL", "http://127.0.0.1:9222"
            ),
            epic_origin=os.environ.get("EPIC_ORIGIN", "").rstrip("/"),
            epic_ready_url_prefix=os.environ.get(
                "EPIC_READY_URL_PREFIX", ""
            ).rstrip("/"),
            max_browser_steps=int(os.environ.get("EPIC_MAX_BROWSER_STEPS", "40")),
            skill_timeout_seconds=int(os.environ.get("EPIC_SKILL_TIMEOUT_SECONDS", "180")),
            reasoning_effort=os.environ.get("EPIC_REASONING_EFFORT", "low").lower(),
            reasoning_summary=os.environ.get("EPIC_REASONING_SUMMARY", "concise").lower(),
            cache_ttl_seconds=int(os.environ.get("EPIC_CACHE_TTL_SECONDS", "900")),
            cache_max_entries=int(os.environ.get("EPIC_CACHE_MAX_ENTRIES", "16")),
            cache_max_bytes=int(os.environ.get("EPIC_CACHE_MAX_BYTES", "8388608")),
            synthetic_portal_enabled=os.environ.get(
                "EPIC_SYNTHETIC_PORTAL", ""
            ) == "1",
            navigation_hints=os.environ.get("EPIC_NAVIGATION_HINTS", "") == "1",
            visible_file_demo_enabled=os.environ.get(
                "EPIC_VISIBLE_FILE_DEMO", ""
            ) == "1",
            ssms_executable=Path(os.environ.get(
                "EPIC_SSMS_EXECUTABLE",
                r"C:\Program Files (x86)\Microsoft SQL Server Management Studio 20"
                r"\Common7\IDE\Ssms.exe",
            )),
            asset_roots=tuple(
                Path(value.strip()).resolve()
                for value in os.environ.get("EPIC_ASSET_ROOTS", "").split(os.pathsep)
                if value.strip()
            ),
            diagnostics_dir=(
                Path(os.environ["EPIC_DIAGNOSTICS_DIR"]).resolve()
                if os.environ.get("EPIC_DIAGNOSTICS_DIR") else None
            ),
            sql_demo_query=Path(os.environ.get(
                "EPIC_SQL_DEMO_QUERY",
                r"C:\EpicDemo\shared\Italian Patient Demo.sql",
            )),
        )

    def validate(self) -> None:
        if self.backend not in {"fixture", "copilot", "computer-use"}:
            raise RuntimeError("EPIC_BACKEND must be fixture, copilot, or computer-use.")
        if min(self.cache_ttl_seconds, self.cache_max_entries, self.cache_max_bytes) <= 0:
            raise RuntimeError("Cache limits must be positive.")
        if not 1 <= self.skill_timeout_seconds <= 600:
            raise RuntimeError("EPIC_SKILL_TIMEOUT_SECONDS must be between 1 and 600.")
        if self.reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise RuntimeError("EPIC_REASONING_EFFORT must be low, medium, high, xhigh or max.")
        if self.reasoning_summary not in {"none", "concise", "detailed"}:
            raise RuntimeError("EPIC_REASONING_SUMMARY must be none, concise or detailed.")
        if self.backend in {"copilot", "computer-use"}:
            missing = [
                name
                for name, value in {
                    "EPIC_COMPUTER_USE_ENABLED=1": self.computer_use_enabled,
                    "EPIC_ORIGIN": self.epic_origin,
                    "EPIC_READY_URL_PREFIX": self.epic_ready_url_prefix,
                }.items()
                if not value
            ]
            if missing:
                raise RuntimeError(
                    "Live Epic backend is disabled or incomplete: "
                    + ", ".join(missing)
                )
            origin = urlsplit(self.epic_origin)
            loopback_training = (
                self.synthetic_portal_enabled
                and origin.scheme == "http"
                and origin.hostname in {"127.0.0.1", "localhost"}
                and bool(origin.port)
            )
            if ((origin.scheme != "https" and not loopback_training)
                    or not origin.hostname
                    or origin.username or origin.password
                    or origin.path or origin.query or origin.fragment):
                raise RuntimeError(
                    "EPIC_ORIGIN must be an exact HTTPS origin with no path, "
                    "or an explicit loopback HTTP origin in synthetic EMR mode."
                )
            ready_url = urlsplit(self.epic_ready_url_prefix)
            ready_port = ready_url.port
            ready_suffix = (
                f":{ready_port}"
                if ready_port and ready_port != (443 if ready_url.scheme == "https" else 80)
                else ""
            )
            ready_origin = (
                f"{ready_url.scheme}://{(ready_url.hostname or '').lower()}{ready_suffix}"
            )
            if ((ready_url.scheme != "https" and not loopback_training)
                    or not ready_url.hostname
                    or ready_url.username or ready_url.password
                    or ready_url.query or ready_url.fragment
                    or ready_origin != self.epic_origin.lower()):
                raise RuntimeError(
                    "EPIC_READY_URL_PREFIX must be an HTTPS URL on EPIC_ORIGIN "
                    "with no credentials, query, or fragment."
                )
            cdp = urlsplit(self.browser_cdp_url)
            if (cdp.scheme != "http" or cdp.hostname not in {"127.0.0.1", "localhost"}
                    or cdp.username or cdp.password or cdp.path or cdp.query
                    or cdp.fragment or not cdp.port):
                raise RuntimeError("EPIC_BROWSER_CDP_URL must be a loopback HTTP port.")
            endpoint = urlsplit(self.foundry_endpoint)
            if self.foundry_endpoint and (endpoint.scheme != "https" or not endpoint.hostname
                    or endpoint.username or endpoint.password
                    or endpoint.query or endpoint.fragment):
                raise RuntimeError("The model endpoint must be an HTTPS resource endpoint.")
            if "/projects/" in endpoint.path:
                raise RuntimeError(
                    "Use the Azure OpenAI resource endpoint, not a Foundry project URL."
                )
            if not 1 <= self.max_browser_steps <= 100:
                raise RuntimeError("EPIC_MAX_BROWSER_STEPS must be between 1 and 100.")
