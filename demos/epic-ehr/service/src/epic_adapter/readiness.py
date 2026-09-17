"""Independent readiness checks for the demo terminal and API.

File-only retrieval must never be reported as blocked by an unavailable or
logged-out browser, so each surface is probed and reported separately.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from .browser import origin_of
from .config import Settings

_CDP_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class ReadinessCheck:
    status: str  # "ready", "not_ready", or "not_applicable"
    detail: str


def _api_readiness(settings: Settings) -> ReadinessCheck:
    if not settings.bearer_token or settings.bearer_token.startswith("replace-"):
        return ReadinessCheck("not_ready", "API bearer token is not configured.")
    return ReadinessCheck("ready", "API is accepting authenticated requests.")


def _files_readiness(settings: Settings) -> ReadinessCheck:
    if not settings.file_roots:
        return ReadinessCheck("not_ready", "No approved file roots are configured.")
    missing = [str(root) for root in settings.file_roots if not root.is_dir()]
    if missing:
        return ReadinessCheck(
            "not_ready", f"Missing or inaccessible file root(s): {', '.join(missing)}"
        )
    return ReadinessCheck("ready", "All approved file roots are accessible.")


def _cdp_get(url: str) -> dict | list:
    with urllib.request.urlopen(url, timeout=_CDP_TIMEOUT_SECONDS) as response:  # noqa: S310 loopback-only CDP endpoint
        return json.load(response)


def _browser_readiness(settings: Settings) -> ReadinessCheck:
    if settings.backend not in {"copilot", "computer-use"} or not settings.computer_use_enabled:
        return ReadinessCheck("not_applicable", "Browser retrieval is disabled for this backend.")
    cdp = urlsplit(settings.browser_cdp_url)
    if cdp.hostname not in {"127.0.0.1", "localhost"}:
        return ReadinessCheck("not_ready", "Browser CDP endpoint is not loopback-only.")
    try:
        _cdp_get(f"{settings.browser_cdp_url}/json/version")
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return ReadinessCheck("not_ready", "The dedicated browser is not reachable.")
    return ReadinessCheck("ready", "The dedicated browser is connected.")


def _login_readiness(settings: Settings) -> ReadinessCheck:
    if settings.backend not in {"copilot", "computer-use"} or not settings.computer_use_enabled:
        return ReadinessCheck("not_applicable", "Browser retrieval is disabled for this backend.")
    try:
        targets = _cdp_get(f"{settings.browser_cdp_url}/json/list")
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return ReadinessCheck("not_ready", "Cannot inspect the browser to confirm login.")
    origin_matches = [
        target for target in targets
        if isinstance(target, dict) and target.get("type") == "page"
        and origin_of(target.get("url", "")) == origin_of(settings.epic_origin)
    ]
    if len(origin_matches) != 1:
        return ReadinessCheck(
            "not_ready",
            "Exactly one Epic tab must be open on the approved origin.",
        )
    current_url = origin_matches[0].get("url", "")
    if not current_url.startswith(settings.epic_ready_url_prefix):
        return ReadinessCheck(
            "not_ready",
            "The Epic tab is not on the configured authenticated chart URL prefix.",
        )
    return ReadinessCheck("ready", "The Epic tab is on the authenticated chart URL prefix.")


def check_readiness(settings: Settings) -> dict[str, ReadinessCheck]:
    """Report readiness for each independent demo surface.

    File-only retrieval readiness never depends on browser or login state.
    """
    return {
        "api": _api_readiness(settings),
        "files": _files_readiness(settings),
        "browser": _browser_readiness(settings),
        "epic_login": _login_readiness(settings),
    }
