from __future__ import annotations

from typing import Callable

from ..browser import BrowserSession
from ..config import Settings
from ..models import ClinicalBundle, ClinicalResource, ResourceType
from ..skill_runner import CopilotSkillRunner


class ComputerUseEpicAdapter:
    def __init__(
        self, settings: Settings, *,
        client_factory: Callable | None = None,
        browser_factory: Callable = BrowserSession,
        desktop_factory: Callable | None = None,
        require_runtime_token: bool = True,
    ) -> None:
        runner_options = {
            "client_factory": client_factory,
            "browser_factory": browser_factory,
            "require_runtime_token": require_runtime_token,
        }
        if desktop_factory is not None:
            runner_options["desktop_factory"] = desktop_factory
        self.runner = CopilotSkillRunner(
            settings, **runner_options,
        )

    def retrieve(
        self, patient_id: str, resources: list[ResourceType],
    ) -> list[ClinicalResource]:
        return self.runner.retrieve("epic-browser", patient_id, resources).resources

    def retrieve_sql(
        self, patient_id: str, resources: list[ResourceType],
    ) -> ClinicalBundle:
        return self.runner.retrieve("sql-desktop", patient_id, resources)
