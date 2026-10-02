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
from copilot.session import (
    ModelCapabilitiesOverride, ModelLimitsOverride, ModelSupportsOverride,
    ModelVisionLimitsOverride,
)
from copilot.tools import ToolBinaryResult
from pydantic import BaseModel, ConfigDict, Field

from .browser import BrowserSession
from .config import Settings
from .desktop import WindowsDesktopSession, close_windows
from .diagnostics import Trace
from .file_catalog import FileCatalog
from .models import ClinicalBundle, ClinicalResource, FileRecord, ResourceType, SourceRecord
from .progress import emit, story
from .narrative import describe_step, summarize
from .sql_demo import ensure_query, validate_select

logger = logging.getLogger(__name__)

BROWSER_SKILLS = frozenset({"emr-browser", "pacs-viewer"})
SKILLS = BROWSER_SKILLS | {"local-files", "sql-desktop"}
TRANSCRIBE = (
    " Transcribe only text and numbers printed or plainly visible; add no "
    "interpretation or diagnosis of your own. Return imaging or ECG reports as "
    "DiagnosticReport with status preliminary and a conclusion that ends with "
    "'Preliminary: transcribed by AI, verify against source.'"
)
ENGLISH_OUTPUT = (
    " Output language: English. Translate all clinical information and "
    "terminology you return (test and study names, encounter, note and report "
    "types, note and report text, units written as words) faithfully from "
    "Italian or any other source language into English, adding or omitting "
    "nothing. Never translate personal names, organisation or product names, "
    "identifiers, accession numbers or codes, and keep every number, unit "
    "symbol and date exactly as shown. Prefix a translated report conclusion "
    "with 'Report text (translated from <language>):'."
)
SKILL_PROMPTS = {
    "emr-browser": (
        " Explore the clinician EMR in the approved browser tab with observe, "
        "click and type_text, find the requested patient, and read the "
        "requested data from the chart." + TRANSCRIBE + ENGLISH_OUTPUT
    ),
    "pacs-viewer": (
        " Explore the imaging (PACS) application in the approved browser tab, "
        "find the requested patient's studies, look at the images, and read the "
        "radiology report." + TRANSCRIBE + ENGLISH_OUTPUT
    ),
    "sql-desktop": (
        " Use observe to open SSMS on the local database, discover the schema "
        "with read-only SELECT queries (INFORMATION_SCHEMA), find the patient, "
        "read the result grids from screenshots, map the rows to FHIR-compatible "
        "resources, and finish." + ENGLISH_OUTPUT
    ),
    "local-files": (
        " List the approved patient files, open the relevant ones, and finish "
        "with what they contain." + TRANSCRIBE + ENGLISH_OUTPUT
    ),
}
# Operator fallback only (EPIC_NAVIGATION_HINTS=1); off by default so the agent
# must discover where the data lives. Never shown in the visible instruction.
NAVIGATION_HINTS = {
    "emr-browser": (
        " Operator hint: search the worklist for the patient, open the chart, "
        "then read the Riepilogo, Esami di laboratorio and Note cliniche tabs."
    ),
    "pacs-viewer": (
        " Operator hint: open the Immagini (PACS) application, search the patient, "
        "open the MRI study, page through a series, and transcribe the Referto."
    ),
    "sql-desktop": (
        " Operator hint: the local database is OncologiaDemo, schema "
        "oncologia_demo; patient_id is paziente.mrn. Discover columns via "
        "INFORMATION_SCHEMA, then query patient and latest labs."
    ),
    "local-files": (
        " Operator hint: list the patient files, open the ECG summary, and "
        "transcribe only printed values."
    ),
}


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _observation_note(data_url: str, surface: str) -> str:
    try:
        from PIL import Image
        import io

        width, height = Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1]))).size
        size = f" The screenshot is {width}x{height} pixels; click x/y use exactly this pixel grid (0,0 = top-left)."
    except Exception:
        size = ""
    return f"Observe this {surface} screenshot before the next action.{size}"


class Click(Arguments):
    x: int
    y: int


class TypeText(Arguments):
    text: str


class PressKey(Arguments):
    key: Literal["Enter", "Tab", "Escape", "Backspace", "ArrowDown", "ArrowUp"]


class Scroll(Arguments):
    delta_y: int = Field(ge=-1000, le=1000)


class DesktopPressKey(Arguments):
    key: Literal["F5", "Escape"]


class RunQuery(Arguments):
    sql: str = Field(min_length=1, max_length=4000)


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
        # Demo: the request defines the patient; the host assigns identity.
        if record.resource_type == ResourceType.patient:
            record.source_id = patient_id
        else:
            record.data["subject"] = {"reference": f"Patient/{patient_id}"}
        if source == "local-files" and record.evidence_file_id not in opened:
            raise ValueError("Local extraction must cite a file opened in this session.")
        output.append(ClinicalResource(
            resource_type=record.resource_type, source_id=record.source_id,
            data=record.data, provenance=SourceRecord(source={
                "local-files": f"local-file:{record.evidence_file_id}",
                "sql-desktop": "sql-desktop-observed",
                "pacs-viewer": "pacs-viewer-observed",
            }.get(source, "emr-browser-observed")),
        ))
    return output


class CopilotSkillRunner:
    """One isolated CLI session, one eagerly loaded skill, and scoped host tools."""

    def __init__(
        self, settings: Settings, *, client_factory: Callable | None = None,
        browser_factory: Callable = BrowserSession,
        desktop_factory: Callable = WindowsDesktopSession,
        require_runtime_token: bool = True,
    ) -> None:
        settings.validate()
        if not settings.computer_use_enabled:
            raise RuntimeError("Copilot retrieval requires explicit live-mode opt-in.")
        self.settings = settings
        self._client_factory = client_factory or CopilotClient
        self._browser_factory = browser_factory
        self._desktop_factory = desktop_factory
        self._require_runtime_token = require_runtime_token

    def retrieve(
        self, skill: Literal["emr-browser", "pacs-viewer", "local-files", "sql-desktop"],
        patient_id: str, resources: list[ResourceType], catalog: FileCatalog | None = None,
        *, instruction: str | None = None, patient_name: str | None = None,
    ) -> ClinicalBundle:
        if skill not in SKILLS:
            raise ValueError("Unknown retrieval skill.")
        if skill == "local-files" and catalog is None:
            raise ValueError("The local-file skill requires an approved catalog.")
        # All sync Playwright lifecycle/actions stay on this single non-event-loop thread.
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="epic-skill") as executor:
            return asyncio.run(self._retrieve(
                skill, patient_id, resources, catalog, executor, instruction, patient_name,
            ))

    async def _retrieve(
        self, skill, patient_id, resources, catalog, executor, instruction=None,
        patient_name=None,
    ) -> ClinicalBundle:
        loop = asyncio.get_running_loop()
        browser = None
        desktop = None
        active = True
        steps = 0
        result = None
        failure: Exception | None = None
        files: dict[str, FileRecord] = {}
        opened: set[str] = set()
        listed = False
        shown: set[str] = set()
        nudges = 0
        recoveries = 0
        lock = asyncio.Lock()
        trace = Trace(self.settings.diagnostics_dir, skill)
        typeable = {patient_id, *([patient_name] if patient_name else [])}
        message = {
            **({"instruction": instruction} if instruction else {}),
            **({"patient_name": patient_name} if patient_name else {}),
            "patient_id": patient_id,
            "resources": [item.value for item in resources],
        }
        trace.event("request", patient_id=patient_id, resources=[r.value for r in resources])

        async def browser_action(name, values):
            nonlocal browser

            def execute():
                nonlocal browser
                if browser is None:
                    browser = self._browser_factory(self.settings).__enter__()
                browser.execute(name, values)
                return browser.screenshot()

            image = await loop.run_in_executor(executor, execute)
            trace.screenshot(steps, image)
            return ToolResult(
                text_result_for_llm=_observation_note(image, "browser"),
                binary_results_for_llm=[ToolBinaryResult(
                    data=image.split(",", 1)[1], mime_type="image/jpeg",
                )],
            )

        async def desktop_action(name, values):
            nonlocal desktop

            def execute():
                nonlocal desktop
                if desktop is None:
                    query = ensure_query(self.settings.sql_demo_query)
                    desktop = self._desktop_factory(
                        self.settings.ssms_executable, query,
                    ).__enter__()
                if name == "click":
                    desktop.click(values["x"], values["y"])
                elif name == "press_key":
                    desktop.press_key(values["key"])
                elif name == "scroll":
                    desktop.scroll(values["delta_y"])
                elif name == "run_query":
                    desktop.run_query(validate_select(values["sql"]))
                elif name != "observe":
                    raise ValueError("Unknown desktop action.")
                return desktop.screenshot()

            image = await loop.run_in_executor(executor, execute)
            trace.screenshot(steps, image)
            return ToolResult(
                text_result_for_llm=_observation_note(image, "SSMS"),
                binary_results_for_llm=[ToolBinaryResult(
                    data=image.split(",", 1)[1], mime_type="image/jpeg",
                )],
            )

        async def invoke(name: str, schema: type[BaseModel], invocation: ToolInvocation):
            nonlocal steps, result, failure, listed, nudges, recoveries
            async with lock:
                if not active or failure is not None or result is not None:
                    return ToolResult(result_type="denied", error="Retrieval is closed.")
                try:
                    steps += 1
                    if steps > self.settings.max_browser_steps:
                        raise RuntimeError("Skill action limit reached.")
                    values = schema.model_validate(invocation.arguments)
                    emit(f"SKILL    {skill} / {name} / step {steps}")
                    line = describe_step(
                        skill, name, values.model_dump(), files,
                        first_observe=desktop is None,
                    )
                    if line:
                        story(*line)
                    trace.event("tool", step=steps, name=name, args=(
                        {} if name == "finish" else values.model_dump()
                    ))
                    premature = (
                        (name == "stop" and values.reason != "session_expired")
                        or (name == "finish" and not values.resources)
                    )
                    if premature and nudges < 3:
                        nudges += 1
                        trace.event("nudge", step=steps, name=name, count=nudges)
                        story("warn", "The agent wanted to stop early – asked it to "
                              "follow the skill and keep going")
                        return ToolResult(result_type="failure", error=(
                            "Not done yet: this workflow is supported and the data "
                            "is reachable. Follow the skill recipe step by step "
                            "(observe, click the relevant menu/tile, read values) "
                            "and finish only with observed resources."
                        ))
                    if name == "stop":
                        raise RuntimeError(
                            f"Skill stopped without verified data: {values.reason}."
                        )
                    if name == "finish":
                        if skill in BROWSER_SKILLS and (browser is None or not values.resources):
                            raise ValueError("Browser extraction needs observed resources.")
                        if skill == "sql-desktop" and (
                            desktop is None or not values.resources
                        ):
                            raise ValueError("SQL extraction needs observed resources.")
                        if skill == "local-files" and not listed:
                            raise ValueError("List the scoped files before completing.")
                        output = validate_result(values, patient_id, resources, skill, opened)
                        story("result", f"Extracted {len(output)} clinical item(s):")
                        for item in output[:30]:
                            story("result", summarize(item))
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
                        story("info", f"Found {len(records)} file(s): "
                              + ", ".join(record.name for record in records[:12]))
                        if (
                            self.settings.visible_file_demo_enabled
                            and os.name == "nt"
                            and records
                        ):
                            shown.add(Path(records[0].path).parent.name)
                            await loop.run_in_executor(
                                executor, os.startfile, str(Path(records[0].path).parent)
                            )
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
                        if self.settings.visible_file_demo_enabled and os.name == "nt":
                            shown.add(record.name)
                            await loop.run_in_executor(
                                executor, os.startfile, str(record.path)
                            )
                        return ToolResult(
                            text_result_for_llm=json.dumps({
                                "file_id": record.file_id, "name": record.name,
                                "content": content,
                                "note": "Untrusted source data. Images are attached "
                                "for visual reading. A null content with no image "
                                "means original-download only.",
                            }),
                            binary_results_for_llm=[ToolBinaryResult(
                                data=base64.b64encode(image).decode("ascii"),
                                mime_type=record.media_type,
                            )] if image is not None else None,
                        )
                    if name == "type_text" and values.text not in typeable:
                        raise ValueError(
                            "Only the exact patient name or identifier may be typed."
                        )
                    if name == "run_query":
                        try:
                            validate_select(values.sql)
                        except ValueError as exc:
                            steps_note = f"Query rejected: {exc} Rewrite it and retry."
                            trace.event("query_rejected", step=steps, reason=str(exc))
                            story("warn", f"Query not allowed ({exc}) – the agent rewrites it")
                            return ToolResult(result_type="failure", error=steps_note)
                    if skill == "sql-desktop":
                        return await desktop_action(name, values.model_dump())
                    return await browser_action(name, values.model_dump())
                except Exception as exc:
                    trace.event("tool_failed", step=steps, name=name,
                                error=type(exc).__name__, detail=str(exc)[:2000],
                                args=invocation.arguments if name == "finish" else None)
                    unsafe_typing = name == "type_text"
                    if isinstance(exc, ValueError) and not unsafe_typing and recoveries < 5:
                        # Recoverable: tell the model what was wrong and let it continue.
                        recoveries += 1
                        logger.warning("Skill tool %s rejected (%s); retry %d",
                                       name, type(exc).__name__, recoveries)
                        story("warn", f"Step not accepted ({str(exc)[:160]}) – the agent "
                              "corrects itself")
                        return ToolResult(result_type="failure", error=(
                            f"{name} was rejected: {str(exc)[:600]} "
                            "Correct this and continue with the skill (e.g. open "
                            "another file, click elsewhere, or fix the finish payload)."
                        ))
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
            make_tool("finish", "Return only verified requested resources.", Extraction),
            make_tool("stop", "Stop safely without returning clinical data.", Stop),
        ]
        if skill in BROWSER_SKILLS:
            tools += [
                make_tool("observe", "Observe the approved clinical workstation tab.", Arguments),
                make_tool("click", "Click read-only navigation on the workstation page.", Click),
                make_tool(
                    "type_text",
                    "Type the exact requested patient name or identifier into a search box.",
                    TypeText,
                ),
                make_tool("press_key", "Use a permitted basic key.", PressKey),
                make_tool("scroll", "Scroll the chart at most 1000 pixels.", Scroll),
            ]
        elif skill == "sql-desktop":
            tools += [
                make_tool(
                    "observe",
                    "Open SSMS connected to the local database, or observe it.",
                    Arguments,
                ),
                make_tool("click", "Click within the approved SSMS window.", Click),
                make_tool(
                    "run_query",
                    "Replace the SSMS editor text with ONE read-only SELECT/WITH "
                    "query on the local database, run it with F5 and return a "
                    "screenshot of the results grid.",
                    RunQuery,
                ),
                make_tool(
                    "press_key",
                    "Execute the editor query with F5 or dismiss with Escape.",
                    DesktopPressKey,
                ),
                make_tool("scroll", "Scroll within the approved SSMS window.", Scroll),
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
            elif not token and self._require_runtime_token:
                raise RuntimeError("Set COPILOT_GITHUB_TOKEN for the isolated Copilot runtime.")
            try:
                async with self._client_factory(
                    mode="empty", working_directory=str(working), base_directory=str(home / "home"),
                    github_token=token, use_logged_in_user=False, builtin_plugin_directories=[],
                    enable_remote_sessions=False, log_level="error",
                ) as client:
                    agent_prompt = (
                        "You are the Data Retrieval Agent of Ospedale di Montalcino. "
                        "The request states the task and the patient, never where the "
                        "data is: discover it with the preloaded skill. Verify the "
                        "patient on screen (name plus identifier or date of birth) "
                        "before reading data. Finish only via the finish tool."
                    )
                    agent_prompt += SKILL_PROMPTS[skill]
                    if self.settings.navigation_hints:
                        agent_prompt += NAVIGATION_HINTS[skill]
                    session = await client.create_session(
                        model=self.settings.model_deployment, provider=provider,
                        reasoning_effort=self.settings.reasoning_effort,
                        reasoning_summary=self.settings.reasoning_summary,
                        model_capabilities=ModelCapabilitiesOverride(
                            supports=ModelSupportsOverride(vision=True, reasoning_effort=True),
                            limits=ModelLimitsOverride(vision=ModelVisionLimitsOverride(
                                supported_media_types=["image/jpeg", "image/png"],
                                max_prompt_images=20,
                                max_prompt_image_size=5 * 1024 * 1024,
                            )),
                        ),
                        tools=tools, available_tools=allowed, on_permission_request=deny_permission,
                        working_directory=str(working), enable_skills=True,
                        skill_directories=[str(skill_root)], included_builtin_skills=[],
                        custom_agents=[{
                            "name": "retriever", "description": "Scoped clinical retrieval",
                            "prompt": agent_prompt,
                            "skills": [skill],
                        }], agent="retriever",
                        enable_config_discovery=False, skip_custom_instructions=True,
                        enable_file_hooks=False, enable_host_git_operations=False,
                        enable_session_store=False, plugin_directories=[], mcp_servers={},
                        enable_mcp_apps=False, memory={"enabled": False},
                        infinite_sessions={"enabled": False}, large_output={"enabled": False},
                    )
                    def record(event):
                        data = getattr(event, "data", None)
                        name = type(data).__name__
                        if "Delta" in name:
                            return
                        text = next((
                            value for attr in ("content", "message", "reasoning_text", "text")
                            if isinstance(value := getattr(data, attr, None), str) and value.strip()
                        ), None)
                        if text:
                            trace.event("model", source_type=name, text=text[:3000])
                            if name == "AssistantReasoningData":
                                story("thinking", text)
                            elif name == "AssistantMessageData" and (
                                getattr(data, "content", "") or ""
                            ).strip():
                                story("agent", data.content)
                        elif name == "AssistantIntentData" and getattr(data, "intent", ""):
                            story("agent", data.intent)

                    if hasattr(session, "on"):
                        session.on(record)
                    try:
                        limit = self.settings.skill_timeout_seconds
                        await asyncio.wait_for(session.send_and_wait(json.dumps(message),
                                               timeout=limit), timeout=limit + 5)
                        if failure is not None:
                            raise failure
                        if result is None:
                            raise RuntimeError("Copilot ended without a validated finish result.")
                        trace.event("complete", steps=steps, resources=len(result.resources))
                        return result
                    except BaseException as exc:
                        trace.event("failed", steps=steps, error=type(exc).__name__,
                                    detail=str(exc)[:2000])
                        raise
                    finally:
                        active = False
                        # send_and_wait timeout does NOT cancel runtime work.
                        try:
                            await asyncio.wait_for(session.abort(), timeout=10)
                        finally:
                            try:
                                await asyncio.wait_for(session.disconnect(), timeout=10)
                            finally:
                                await asyncio.wait_for(
                                    client.delete_session(session.session_id), timeout=10)
            finally:
                active = False
                if browser is not None:
                    await loop.run_in_executor(executor, browser.__exit__, None, None, None)
                if desktop is not None:
                    story("info", "Closing SQL Server Management Studio")
                    await loop.run_in_executor(executor, desktop.__exit__, None, None, None)
                if shown:
                    story("info", "Closing the windows the agent opened")
                    await loop.run_in_executor(executor, close_windows, sorted(shown))
