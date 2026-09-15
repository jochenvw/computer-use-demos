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
    model_api_key: str = ""
    max_browser_steps: int = 40

    @classmethod
    def from_env(cls) -> "Settings":
        service_root = Path(__file__).resolve().parents[2]
        fixture_root = Path(
            os.environ.get("EPIC_FIXTURE_ROOT", service_root.parent / "fixtures")
        ).resolve()
        raw_roots = os.environ.get("EPIC_FILE_ROOTS", str(fixture_root / "files"))
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
            model_api_key=os.environ.get("AZURE_API_KEY", ""),
            max_browser_steps=int(os.environ.get("EPIC_MAX_BROWSER_STEPS", "40")),
        )

    def validate(self) -> None:
        if self.backend not in {"fixture", "computer-use"}:
            raise RuntimeError("EPIC_BACKEND must be fixture or computer-use.")
        if self.backend == "computer-use":
            missing = [
                name
                for name, value in {
                    "EPIC_COMPUTER_USE_ENABLED=1": self.computer_use_enabled,
                    "EPIC_ORIGIN": self.epic_origin,
                    "AZURE_AI_FOUNDRY_ENDPOINT": self.foundry_endpoint,
                }.items()
                if not value
            ]
            if missing:
                raise RuntimeError(
                    "Live Epic backend is disabled or incomplete: "
                    + ", ".join(missing)
                )
            origin = urlsplit(self.epic_origin)
            if (origin.scheme != "https" or not origin.hostname
                    or origin.username or origin.password
                    or origin.path or origin.query or origin.fragment):
                raise RuntimeError("EPIC_ORIGIN must be an exact HTTPS origin with no path.")
            cdp = urlsplit(self.browser_cdp_url)
            if (cdp.scheme != "http" or cdp.hostname not in {"127.0.0.1", "localhost"}
                    or cdp.username or cdp.password or cdp.path or cdp.query
                    or cdp.fragment or not cdp.port):
                raise RuntimeError("EPIC_BROWSER_CDP_URL must be a loopback HTTP port.")
            endpoint = urlsplit(self.foundry_endpoint)
            if (endpoint.scheme != "https" or not endpoint.hostname
                    or endpoint.username or endpoint.password
                    or endpoint.query or endpoint.fragment):
                raise RuntimeError("The model endpoint must be an HTTPS resource endpoint.")
            if "/projects/" in endpoint.path:
                raise RuntimeError(
                    "Use the Azure OpenAI resource endpoint, not a Foundry project URL."
                )
            if not 1 <= self.max_browser_steps <= 100:
                raise RuntimeError("EPIC_MAX_BROWSER_STEPS must be between 1 and 100.")
