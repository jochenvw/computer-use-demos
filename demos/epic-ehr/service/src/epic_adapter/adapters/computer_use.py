from __future__ import annotations

from typing import Callable

from ..browser import BrowserSession
from ..config import Settings
from ..models import ClinicalResource, ResourceType
from ..skill_runner import CopilotSkillRunner


class ComputerUseEpicAdapter:
    def __init__(
        self, settings: Settings, *,
        client_factory: Callable | None = None,
        browser_factory: Callable = BrowserSession,
        require_runtime_token: bool = True,
    ) -> None:
        self.runner = CopilotSkillRunner(
            settings, client_factory=client_factory, browser_factory=browser_factory,
            require_runtime_token=require_runtime_token,
        )

    def retrieve(
        self, patient_id: str, resources: list[ResourceType],
    ) -> list[ClinicalResource]:
        return self.runner.retrieve("epic-browser", patient_id, resources).resources
