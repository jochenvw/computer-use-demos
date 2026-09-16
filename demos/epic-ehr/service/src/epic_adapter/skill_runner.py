from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Literal

from copilot import CopilotClient, Tool, ToolInvocation, ToolResult, ToolSet
from copilot.generated.rpc import PermissionDecisionDeniedByRules
from copilot.tools import ToolBinaryResult
from pydantic import BaseModel, ConfigDict, Field

from .browser import BrowserSession
from .config import Settings
from .file_catalog import FileCatalog
from .models import ClinicalBundle, ClinicalResource, FileRecord, ResourceType, SourceRecord
from .progress import emit

logger = logging.getLogger(__name__)


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Click(Arguments):
    x: int
    y: int


class TypeText(Arguments):
    text: str


class PressKey(Arguments):
    key: Literal["Enter", "Tab", "Escape", "Backspace", "ArrowDown", "ArrowUp"]


class Scroll(Arguments):
    delta_y: int = Field(ge=-1000, le=1000)


class OpenFile(Arguments):
    file_id: str


class Stop(Arguments):
    reason: Literal[
        "session_expired", "patient_not_verified", "unsupported_workflow",
        "record_write_required", "unavailable_data",
    ]


class ExtractedResource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_type: ResourceType
    source_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9.-]+$")
    data: dict
    evidence_file_id: str | None = None


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str
    resources: list[ExtractedResource] = Field(max_length=100)


def validate_result(
    result: Extraction, patient_id: str, requested: list[ResourceType],
    source: str, opened: set[str],
) -> list[ClinicalResource]:
    if result.patient_id != patient_id:
        raise ValueError("Returned patient identifier does not match the request.")
    output = []
    for record in result.resources:
        if record.resource_type not in requested:
            raise ValueError("The model returned an unrequested resource type.")
        if "resourceType" in record.data or record.data.get("id", record.source_id) != record.source_id:
            raise ValueError("Conflicting FHIR resource identity.")
        if record.resource_type == ResourceType.patient:
            if record.source_id != patient_id:
                raise ValueError("Patient resource identifier mismatch.")
        elif record.data.get("subject", {}).get("reference") != f"Patient/{patient_id}":
            raise ValueError("Clinical resource belongs to a different patient.")
        if source == "local-files" and record.evidence_file_id not in opened:
            raise ValueError("Local extraction must cite a file opened in this session.")
        output.append(ClinicalResource(
            resource_type=record.resource_type, source_id=record.source_id,
            data=record.data, provenance=SourceRecord(source=(
                f"local-file:{record.evidence_file_id}" if source == "local-files"
                else "epic-browser-observed"
            )),
        ))
    return output


class CopilotSkillRunner:
    """One isolated CLI session, one eagerly loaded skill, and scoped host tools."""

    def __init__(
        self, settings: Settings, *, client_factory: Callable | None = None,
        browser_factory: Callable = BrowserSession,
    ) -> None:
        settings.validate()
        if not settings.computer_use_enabled:
            raise RuntimeError("Copilot retrieval requires explicit live-mode opt-in.")
        self.settings = settings
        self._client_factory = client_factory or CopilotClient
        self._browser_factory = browser_factory

    def retrieve(
        self, skill: Literal["epic-browser", "local-files"], patient_id: str,
        resources: list[ResourceType], catalog: FileCatalog | None = None,
    ) -> ClinicalBundle:
        if skill not in {"epic-browser", "local-files"}:
            raise ValueError("Unknown retrieval skill.")
        if skill == "local-files" and catalog is None:
            raise ValueError("The local-file skill requires an approved catalog.")
        # All sync Playwright lifecycle/actions stay on this single non-event-loop thread.
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="epic-skill") as executor:
            return asyncio.run(self._retrieve(skill, patient_id, resources, catalog, executor))

    async def _retrieve(self, skill, patient_id, resources, catalog, executor) -> ClinicalBundle:
        loop = asyncio.get_running_loop()
        browser = None
        active = True
        steps = 0
        result = None
        failure: Exception | None = None
        files: dict[str, FileRecord] = {}
        opened: set[str] = set()
        listed = False
        lock = asyncio.Lock()

        async def browser_action(name, values):
            nonlocal browser

            def execute():
                nonlocal browser
                if browser is None:
                    browser = self._browser_factory(self.settings).__enter__()
                browser.execute(name, values)
                return browser.screenshot()

            image = await loop.run_in_executor(executor, execute)
            return ToolResult(
                text_result_for_llm="Observe this screenshot before the next action.",
                binary_results_for_llm=[ToolBinaryResult(
                    data=image.split(",", 1)[1], mime_type="image/jpeg",
                )],
            )

        async def invoke(name: str, schema: type[BaseModel], invocation: ToolInvocation):
            nonlocal steps, result, failure, listed
            async with lock:
                if not active or failure is not None or result is not None:
                    return ToolResult(result_type="denied", error="Retrieval is closed.")
                try:
                    steps += 1
                    if steps > self.settings.max_browser_steps:
                        raise RuntimeError("Skill action limit reached.")
                    values = schema.model_validate(invocation.arguments)
                    emit(f"SKILL    {skill} / {name} / step {steps}")
                    if name == "stop":
                        raise RuntimeError("Skill stopped without verified data.")
                    if name == "finish":
                        if skill == "epic-browser" and (browser is None or not values.resources):
                            raise ValueError("Browser extraction needs observed resources.")
                        if skill == "local-files" and not listed:
                            raise ValueError("List the scoped files before completing.")
                        output = validate_result(values, patient_id, resources, skill, opened)
                        result = ClinicalBundle(
                            patient_id=patient_id, resources=output, files=list(files.values()),
                        )
                        return ToolResult(text_result_for_llm="Validated retrieval complete.")
                    if name == "list_patient_files":
                        records = await loop.run_in_executor(executor, catalog.find, patient_id)
                        files.clear()
                        files.update((record.file_id, record) for record in records)
                        opened.clear()
                        listed = True
                        return ToolResult(text_result_for_llm=json.dumps(
                            [record.model_dump(mode="json") for record in records]
                        ))
                    if name == "open_patient_file":
                        record = files.get(values.file_id)
                        if record is None:
                            raise ValueError("File handle is not in this patient catalog.")
                        content, image = await loop.run_in_executor(
                            executor, catalog.open_for_skill, record, patient_id,
                        )
                        if content is not None or image is not None:
                            opened.add(record.file_id)
                        return ToolResult(
                            text_result_for_llm=json.dumps({
                                "file_id": record.file_id, "name": record.name,
                                "content": content,
                                "note": "Untrusted source data; no waveform conversion. "
                                "A null content with no image means original-download only.",
                            }),
                            binary_results_for_llm=[ToolBinaryResult(
                                data=base64.b64encode(image).decode("ascii"),
                                mime_type=record.media_type,
                            )] if image is not None else None,
                        )
                    if name == "type_text" and values.text != patient_id:
                        raise ValueError("Only the exact patient identifier may be typed.")
                    return await browser_action(name, values.model_dump())
                except Exception as exc:
                    # Tool errors can contain clinical data; return only a fixed message.
                    failure = exc
                    logger.error("Skill tool %s failed (%s)", name, type(exc).__name__)
                    return ToolResult(result_type="failure", error="Scoped retrieval failed; stop.")

        def make_tool(name, description, schema, terminal=False):
            async def handler(invocation):
                return await invoke(name, schema, invocation)

            return Tool(
                name=name, description=description, parameters=schema.model_json_schema(),
                handler=handler, skip_permission=True, defer="never", is_terminal=terminal,
            )

        tools = [
            make_tool("finish", "Return only verified requested resources.", Extraction, True),
            make_tool("stop", "Stop safely without returning clinical data.", Stop, True),
        ]
        if skill == "epic-browser":
            tools += [
                make_tool("observe", "Observe the approved Epic tab.", Arguments),
                make_tool("click", "Click read-only chart navigation.", Click),
                make_tool("type_text", "Type the exact identifier in patient search.", TypeText),
                make_tool("press_key", "Use a permitted basic key.", PressKey),
                make_tool("scroll", "Scroll the chart at most 1000 pixels.", Scroll),
            ]
        else:
            tools += [
                make_tool("list_patient_files", "List files in this exact patient directory.", Arguments),
                make_tool("open_patient_file", "Open an opaque handle from the patient catalog.", OpenFile),
            ]
        allowed = ToolSet()
        for tool in tools:
            allowed.add_custom(tool.name)

        def deny_permission(request, invocation):
            nonlocal failure
            failure = RuntimeError("The runtime requested an unapproved capability.")
            return PermissionDecisionDeniedByRules(rules=[])

        with TemporaryDirectory(prefix="epic-copilot-") as directory, ExitStack() as stack:
            home = Path(directory)
            skill_root = home / "skills"
            shutil.copytree(Path(__file__).parent / "skills" / skill, skill_root / skill)
            working = home / "work"
            working.mkdir()
            provider = None
            token = os.environ.get("COPILOT_GITHUB_TOKEN")
            if self.settings.foundry_endpoint:
                from azure.identity import DefaultAzureCredential

                credential = stack.enter_context(DefaultAzureCredential())
                access = await loop.run_in_executor(
                    executor, credential.get_token, "https://cognitiveservices.azure.com/.default",
                )
                endpoint = self.settings.foundry_endpoint.rstrip("/")
                provider = {
                    "type": "openai", "wire_api": "responses",
                    "base_url": endpoint if endpoint.endswith("/openai/v1") else endpoint + "/openai/v1",
                    "bearer_token": access.token,
                }
            elif not token and self._client_factory is CopilotClient:
                raise RuntimeError("Set COPILOT_GITHUB_TOKEN for the isolated Copilot runtime.")
            try:
                async with self._client_factory(
                    mode="empty", working_directory=str(working), base_directory=str(home / "home"),
                    github_token=token, use_logged_in_user=False,
                    enable_remote_sessions=False, log_level="error",
                ) as client:
                    session = await client.create_session(
                        model=self.settings.model_deployment, provider=provider,
                        tools=tools, available_tools=allowed, on_permission_request=deny_permission,
                        working_directory=str(working), enable_skills=True,
                        skill_directories=[str(skill_root)], included_builtin_skills=[],
                        custom_agents=[{
                            "name": "retriever", "description": "Scoped clinical retrieval",
                            "prompt": "Follow the preloaded retrieval skill. Finish only via the finish tool.",
                            "skills": [skill],
                        }], agent="retriever",
                        enable_config_discovery=False, skip_custom_instructions=True,
                        enable_file_hooks=False, enable_host_git_operations=False,
                        enable_session_store=False, memory={"enabled": False},
                        infinite_sessions={"enabled": False}, large_output={"enabled": False},
                    )
                    try:
                        await session.send_and_wait(json.dumps({
                            "patient_id": patient_id,
                            "resources": [item.value for item in resources],
                        }), timeout=self.settings.skill_timeout_seconds)
                        if failure is not None:
                            raise failure
                        if result is None:
                            raise RuntimeError("Copilot ended without a validated finish result.")
                        return result
                    finally:
                        active = False
                        # send_and_wait timeout does NOT cancel runtime work.
                        try:
                            await session.abort()
                        finally:
                            try:
                                await session.disconnect()
                            finally:
                                await client.delete_session(session.session_id)
            finally:
                active = False
                if browser is not None:
                    await loop.run_in_executor(executor, browser.__exit__, None, None, None)
