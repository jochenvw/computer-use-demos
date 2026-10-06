import inspect
import json
import os
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from copilot import CopilotClient, ToolInvocation, ToolSet

from epic_adapter.adapters.computer_use import ComputerUseEpicAdapter
from epic_adapter.config import Settings
from epic_adapter.file_catalog import FileCatalog
from epic_adapter.models import ResourceType
from epic_adapter.skill_runner import CopilotSkillRunner


def settings():
    return replace(
        Settings.from_env(), backend="copilot", computer_use_enabled=True,
        epic_origin="https://epic.example.invalid", foundry_endpoint="",
        epic_ready_url_prefix="https://epic.example.invalid/chart",
        model_deployment="gpt-6-astra", browser_window_title="",
        browser_cdp_url="http://127.0.0.1:9222", max_browser_steps=4,
    )


def patient_result(patient_id="TUS-2026-0417"):
    return {"patient_id": patient_id, "resources": [{
        "resource_type": "patient", "source_id": patient_id, "data": {},
    }]}


class FakeBrowser:
    def __init__(self):
        self.actions = []
        self.closed = False
        self.threads = set()

    def __enter__(self):
        self.threads.add(threading.get_ident())
        return self

    def __exit__(self, *args):
        self.threads.add(threading.get_ident())
        self.closed = True

    def screenshot(self):
        self.threads.add(threading.get_ident())
        return "data:image/jpeg;base64,c3ludGhldGlj"

    def execute(self, name, values):
        self.threads.add(threading.get_ident())
        self.actions.append((name, values))


class FakeDesktop:
    def __init__(self):
        self.actions = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def screenshot(self):
        return "data:image/jpeg;base64,c3FsLWRlc2t0b3A="

    def click(self, x, y):
        self.actions.append(("click", {"x": x, "y": y}))

    def press_key(self, key):
        self.actions.append(("press_key", {"key": key}))

    def scroll(self, delta_y):
        self.actions.append(("scroll", {"delta_y": delta_y}))

    def run_query(self, sql):
        self.actions.append(("run_query", {"sql": sql}))


class FakeClient:
    def __init__(self, script):
        self.script = script
        self.results = []
        self.aborted = self.disconnected = self.deleted = self.closed = False
        self.session_id = "test-scoped-session"

    def factory(self, **kwargs):
        inspect.signature(CopilotClient).bind(**kwargs)
        self.client_options = kwargs
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def create_session(self, **kwargs):
        inspect.signature(CopilotClient.create_session).bind(self, **kwargs)
        self.options = kwargs
        self.skill_text = next(Path(kwargs["skill_directories"][0]).rglob("SKILL.md")).read_text()
        self.tools = {tool.name: tool for tool in kwargs["tools"]}
        return self

    async def invoke(self, name, values):
        result = await self.tools[name].handler(ToolInvocation(
            session_id=self.session_id, tool_call_id="call", tool_name=name,
            arguments=values,
        ))
        self.results.append(result)
        return result

    async def send_and_wait(self, prompt, *, timeout):
        self.prompts = getattr(self, "prompts", []) + [json.loads(prompt)]
        if len(self.prompts) > 1:
            for name, values in getattr(self, "followup", []):
                await self.invoke(name, values)
            return
        self.prompt = self.prompts[0]
        self.timeout = timeout
        if callable(self.script):
            await self.script(self)
        else:
            for name, values in self.script:
                await self.invoke(name, values)

    async def abort(self):
        self.aborted = True

    async def disconnect(self):
        self.disconnected = True

    async def delete_session(self, session_id):
        assert session_id == self.session_id
        self.deleted = True


class ComputerUseTests(unittest.TestCase):
    def build(self, calls, config=None):
        self.browser = FakeBrowser()
        self.desktop = FakeDesktop()
        self.client = FakeClient(calls)
        return ComputerUseEpicAdapter(
            config or settings(), client_factory=self.client.factory,
            browser_factory=lambda _: self.browser,
            desktop_factory=lambda *_: self.desktop,
            require_runtime_token=False,
        )

    def test_cli_skill_uses_screenshots_and_scoped_sdk_session(self):
        adapter = self.build([("observe", {}), ("finish", patient_result())])
        result = adapter.retrieve("TUS-2026-0417", [ResourceType.patient])
        self.assertEqual("emr-browser-observed", result[0].provenance.source)
        self.assertTrue(self.browser.closed)
        self.assertEqual(1, len(self.browser.threads))
        options = self.client.options
        self.assertEqual("gpt-6-astra", options["model"])
        self.assertEqual(["emr-browser"], options["custom_agents"][0]["skills"])
        self.assertEqual("empty", self.client.client_options["mode"])
        self.assertFalse(options["enable_config_discovery"])
        self.assertFalse(options["enable_session_store"])
        self.assertIsInstance(options["available_tools"], ToolSet)
        self.assertEqual(
            {
                "custom:click", "custom:finish", "custom:observe",
                "custom:press_key", "custom:scroll", "custom:stop",
                "custom:type_text",
            },
            set(options["available_tools"]),
        )
        self.assertEqual([], self.client.client_options["builtin_plugin_directories"])
        self.assertEqual([], options["plugin_directories"])
        self.assertEqual({}, options["mcp_servers"])
        self.assertFalse(options["enable_mcp_apps"])
        self.assertEqual(
            {"finish", "stop", "observe", "click", "type_text", "press_key", "scroll"},
            set(self.client.tools),
        )
        self.assertIn("name: emr-browser", self.client.skill_text)
        self.assertEqual("c3ludGhldGlj", self.client.results[0].binary_results_for_llm[0].data)
        self.assertTrue(self.client.aborted and self.client.disconnected and self.client.deleted)
        self.assertTrue(self.client.closed)
        self.assertFalse(Path(self.client.client_options["base_directory"]).exists())

    def test_wrong_patient_fails(self):
        adapter = self.build([("observe", {}), ("finish", patient_result("OTHER"))])
        with self.assertRaises(RuntimeError):
            adapter.retrieve("TUS-2026-0417", [ResourceType.patient])

    def test_session_resumes_when_model_ends_turn_after_nudge(self):
        adapter = self.build([("observe", {}), ("stop", {"reason": "unavailable_data"})])
        self.client.followup = [("finish", patient_result())]
        result = adapter.retrieve("TUS-2026-0417", [ResourceType.patient])
        self.assertEqual(1, len(result))
        self.assertEqual(2, len(self.client.prompts))
        self.assertIn("continue", self.client.prompts[1])

    def test_session_fails_after_bounded_continuations(self):
        adapter = self.build([("observe", {})])
        with self.assertRaisesRegex(RuntimeError, "without a validated finish"):
            adapter.retrieve("TUS-2026-0417", [ResourceType.patient])
        self.assertEqual(3, len(self.client.prompts))

    def test_host_assigns_requested_subject(self):
        adapter = self.build([("observe", {}), ("finish", {
            "patient_id": "TUS-2026-0417", "resources": [{
                "resource_type": "ecg", "source_id": "ecg-1",
                "data": {"subject": {"reference": "Patient/OTHER"}},
            }],
        })])
        bundle = adapter.retrieve("TUS-2026-0417", [ResourceType.ecg])
        self.assertEqual(
            {"reference": "Patient/TUS-2026-0417"}, bundle[0].data["subject"]
        )

    def test_host_normalizes_redundant_fhir_identity(self):
        adapter = self.build([("observe", {}), ("finish", {
            "patient_id": "TUS-2026-0417", "resources": [{
                "resource_type": "patient", "source_id": "model-patient",
                "data": {
                    "resourceType": "Patient", "id": "conflicting-model-id",
                    "name": [{"family": "Ricci", "given": ["Anna"]}],
                },
            }, {
                "resource_type": "observations", "source_id": "lab-HB-1",
                "data": {
                    "resourceType": "Observation", "id": "different-id",
                    "status": "final",
                },
            }],
        })])
        bundle = adapter.retrieve(
            "TUS-2026-0417",
            [ResourceType.patient, ResourceType.observations],
        )
        patient, observation = bundle
        self.assertEqual("TUS-2026-0417", patient.source_id)
        self.assertNotIn("resourceType", patient.data)
        self.assertNotIn("id", patient.data)
        self.assertEqual("lab-HB-1", observation.source_id)
        self.assertNotIn("resourceType", observation.data)
        self.assertNotIn("id", observation.data)
        self.assertEqual(
            {"reference": "Patient/TUS-2026-0417"},
            observation.data["subject"],
        )

    def test_model_cannot_type_arbitrary_text_or_recover_from_failure(self):
        adapter = self.build([
            ("type_text", {"text": "change prescription"}),
            ("observe", {}), ("finish", patient_result()),
        ])
        with self.assertRaises(ValueError):
            adapter.retrieve("TUS-2026-0417", [ResourceType.patient])
        self.assertEqual([], self.browser.actions)
        self.assertEqual("denied", self.client.results[-1].result_type)

    def test_strict_host_tool_arguments(self):
        adapter = self.build([("click", {"x": True, "y": 0})])
        with self.assertRaises(RuntimeError):
            adapter.retrieve("TUS-2026-0417", [ResourceType.patient])
        self.assertEqual([], self.browser.actions)

    def test_expired_session_stops(self):
        adapter = self.build([("stop", {"reason": "session_expired"})])
        with self.assertRaisesRegex(RuntimeError, "session_expired"):
            adapter.retrieve("TUS-2026-0417", [ResourceType.patient])

    def test_sql_patient_not_verified_is_recoverable(self):
        observation = {
            "patient_id": "TUS-2026-0417",
            "resources": [{
                "resource_type": "observations",
                "source_id": "lab-HB-1",
                "data": {"status": "final"},
            }],
        }

        async def recover(client):
            stopped = await client.invoke(
                "stop", {"reason": "patient_not_verified"}
            )
            self.assertEqual("failure", stopped.result_type)
            self.assertIn("narrow patient-only SELECT", stopped.error)
            await client.invoke(
                "run_query",
                {"sql": (
                    "SELECT mrn, nome, cognome, data_nascita, paziente_id "
                    "FROM oncologia_demo.paziente "
                    "WHERE mrn = N'TUS-2026-0417'"
                )},
            )
            await client.invoke("finish", observation)

        adapter = self.build(recover)
        result = adapter.retrieve_sql(
            "TUS-2026-0417", [ResourceType.observations],
        )
        self.assertEqual("lab-HB-1", result.resources[0].source_id)

    def synthetic_emr(self, **changes):
        return replace(
            settings(), synthetic_portal_enabled=True,
            epic_origin="http://127.0.0.1:8001",
            epic_ready_url_prefix="http://127.0.0.1:8001/", **changes,
        )

    def test_prompt_has_no_navigation_hints_by_default(self):
        adapter = self.build(
            [("observe", {}), ("finish", patient_result())], config=self.synthetic_emr(),
        )
        adapter.retrieve(
            "TUS-2026-0417", [ResourceType.patient],
            instruction="Retrieve all relevant medical information for patient Anna Ricci.",
            patient_name="Anna Ricci",
        )
        prompt = self.client.options["custom_agents"][0]["prompt"]
        self.assertIn("Data Retrieval Agent of Ospedale di Montalcino", prompt)
        self.assertIn("never where the data is", prompt)
        for hint in ("Operator hint", "Riepilogo", "worklist", "Uitslagen", "OncologiaDemo"):
            self.assertNotIn(hint, prompt)
        self.assertEqual({
            "instruction": "Retrieve all relevant medical information for patient Anna Ricci.",
            "patient_name": "Anna Ricci", "patient_id": "TUS-2026-0417",
            "resources": ["patient"],
        }, self.client.prompt)
        self.assertIn("Output language: English", prompt)
        self.assertIn("Never translate personal names", prompt)

    def test_every_skill_returns_english_but_keeps_names_and_codes(self):
        from epic_adapter.skill_runner import ENGLISH_OUTPUT, SKILL_PROMPTS
        from epic_adapter.tester import packaged_skill_instructions
        for skill, text in SKILL_PROMPTS.items():
            self.assertIn(ENGLISH_OUTPUT, text, skill)
        for skill, text in packaged_skill_instructions().items():
            self.assertIn("English", text, skill)
            self.assertNotIn("source-language", text, skill)
            self.assertNotIn("source language is fine", text, skill)

    def test_navigation_hints_are_operator_opt_in(self):
        adapter = self.build(
            [("observe", {}), ("finish", patient_result())],
            config=self.synthetic_emr(navigation_hints=True),
        )
        adapter.retrieve("TUS-2026-0417", [ResourceType.patient])
        prompt = self.client.options["custom_agents"][0]["prompt"]
        self.assertIn("Operator hint", prompt)
        self.assertIn("worklist", prompt)

    def test_agent_may_type_only_the_requested_name_or_identifier(self):
        adapter = self.build([
            ("type_text", {"text": "Anna Ricci"}),
            ("type_text", {"text": "TUS-2026-0417"}),
            ("observe", {}), ("finish", patient_result()),
        ], config=self.synthetic_emr())
        adapter.retrieve("TUS-2026-0417", [ResourceType.patient], patient_name="Anna Ricci")
        self.assertEqual(
            [("type_text", {"text": "Anna Ricci"}), ("type_text", {"text": "TUS-2026-0417"}),
             ("observe", {})],
            self.browser.actions,
        )
        adapter = self.build([("type_text", {"text": "Antonio Ricci"})], config=self.synthetic_emr())
        with self.assertRaises(ValueError):
            adapter.retrieve("TUS-2026-0417", [ResourceType.patient], patient_name="Anna Ricci")
        self.assertEqual([], self.browser.actions)

    def test_pacs_viewer_returns_preliminary_imaging_report(self):
        report = {
            "patient_id": "TUS-2026-0417",
            "resources": [{
                "resource_type": "imaging", "source_id": "MTL-26-08817",
                "data": {
                    "status": "preliminary",
                    "code": {"coding": [{"system": "http://loinc.org", "code": "18748-4"}]},
                    "conclusion": "Report text: two liver lesions. Preliminary: "
                                  "transcribed by AI, verify against source.",
                },
            }],
        }
        adapter = self.build(
            [("observe", {}), ("click", {"x": 10, "y": 20}), ("finish", report)],
            config=self.synthetic_emr(),
        )
        bundle = adapter.retrieve_pacs("TUS-2026-0417", [ResourceType.imaging])
        self.assertEqual(["pacs-viewer"], self.client.options["custom_agents"][0]["skills"])
        self.assertIn("name: pacs-viewer", self.client.skill_text)
        self.assertEqual("pacs-viewer-observed", bundle.resources[0].provenance.source)
        self.assertEqual(ResourceType.imaging, bundle.resources[0].resource_type)
        self.assertIn("type_text", self.client.tools)
        prompt = self.client.options["custom_agents"][0]["prompt"]
        self.assertIn("Preliminary: transcribed by AI, verify against source.", prompt)
        self.assertIn("no interpretation or diagnosis", prompt.replace("add no ", "no ").replace(
            "interpretation or diagnosis of your own", "interpretation or diagnosis"))

    def test_sql_desktop_writes_query_and_returns_observation(self):
        observation = {
            "patient_id": "TUS-2026-0417",
            "resources": [{
                "resource_type": "observations",
                "source_id": "lab-HB-1",
                "data": {
                    "status": "final",
                    "subject": {"reference": "Patient/TUS-2026-0417"},
                    "code": {"coding": [{"code": "HB", "display": "Emoglobina"}]},
                    "effectiveDateTime": "2026-09-21T08:30:00",
                    "valueQuantity": {"value": 10.4, "unit": "g/dL"},
                },
            }],
        }
        query = (
            "SELECT e.codice, e.valore_numerico FROM oncologia_demo.esame_laboratorio e "
            "JOIN oncologia_demo.paziente p ON p.paziente_id = e.paziente_id "
            "WHERE p.mrn = N'TUS-2026-0417'"
        )
        with tempfile.TemporaryDirectory() as directory:
            adapter = self.build(
                [
                    ("observe", {}),
                    ("run_query", {"sql": "DELETE FROM oncologia_demo.paziente"}),
                    ("run_query", {"sql": query}),
                    ("finish", observation),
                ],
                config=replace(
                    settings(),
                    sql_demo_query=Path(directory) / "Italian Patient Demo.sql",
                    ssms_executable=Path(directory) / "Ssms.exe",
                ),
            )

            result = adapter.retrieve_sql(
                "TUS-2026-0417", [ResourceType.observations],
            )

        self.assertEqual(
            "sql-desktop-observed", result.resources[0].provenance.source
        )
        self.assertEqual("failure", self.client.results[1].result_type)
        self.assertEqual(
            [("run_query", {"sql": f"USE OncologiaDemo;\n{query};\n"})],
            self.desktop.actions,
        )
        self.assertTrue(self.desktop.closed)
        prompt = self.client.options["custom_agents"][0]["prompt"]
        self.assertIn("INFORMATION_SCHEMA", prompt)
        self.assertIn("patient-only query", prompt)
        self.assertIn("exact requested MRN", prompt)
        self.assertNotIn("OncologiaDemo", prompt)
        self.assertIn("MRN", self.client.skill_text)

    def test_action_budget_is_enforced(self):
        adapter = self.build([("observe", {})] * 5)
        with self.assertRaisesRegex(RuntimeError, "action limit"):
            adapter.retrieve("TUS-2026-0417", [ResourceType.patient])
        self.assertEqual(4, len(self.browser.actions))

    def test_timeout_aborts_deletes_and_closes_browser(self):
        async def timeout(client):
            await client.invoke("observe", {})
            raise TimeoutError("synthetic")

        adapter = self.build(timeout)
        with self.assertRaises(TimeoutError):
            adapter.retrieve("TUS-2026-0417", [ResourceType.patient])
        self.assertTrue(self.client.aborted and self.client.deleted and self.browser.closed)

    def test_unexpected_builtin_permission_fails_closed(self):
        async def permission(client):
            decision = client.options["on_permission_request"]({}, {})
            self.assertEqual("denied-by-rules", decision.kind)
            await client.invoke("observe", {})

        adapter = self.build(permission)
        with self.assertRaisesRegex(RuntimeError, "unapproved"):
            adapter.retrieve("TUS-2026-0417", [ResourceType.patient])
        self.assertEqual([], self.browser.actions)

    def test_remote_browser_debugging_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "loopback"):
            replace(settings(), browser_cdp_url="http://10.0.0.1:9222").validate()

    def test_live_opt_in_required(self):
        with self.assertRaises(RuntimeError):
            replace(settings(), computer_use_enabled=False).validate()

    def test_synthetic_portal_requires_explicit_loopback_opt_in(self):
        loopback = replace(
            settings(),
            epic_origin="http://127.0.0.1:8001",
            epic_ready_url_prefix="http://127.0.0.1:8001/",
        )
        with self.assertRaisesRegex(RuntimeError, "loopback HTTP"):
            loopback.validate()
        replace(loopback, synthetic_portal_enabled=True).validate()

    def test_runtime_token_requirement_is_explicit_for_injected_factories(self):
        client = FakeClient([])
        runner = CopilotSkillRunner(
            settings(), client_factory=client.factory, require_runtime_token=True,
        )
        with patch.dict(os.environ, {"COPILOT_GITHUB_TOKEN": ""}):
            with self.assertRaisesRegex(RuntimeError, "COPILOT_GITHUB_TOKEN"):
                runner.retrieve(
                    "local-files", "TUS-2026-0417", [ResourceType.ecg], FileCatalog(()),
                )


class LocalFileSkillTests(unittest.TestCase):
    def test_file_skill_lists_opens_and_returns_documented_ecg(self):
        async def script(client):
            listed = await client.invoke("list_patient_files", {})
            file_id = json.loads(listed.text_result_for_llm)[0]["file_id"]
            opened = await client.invoke("open_patient_file", {"file_id": file_id})
            self.assertIn("Synthetic sinus tachycardia, rate 104", opened.text_result_for_llm)
            await client.invoke("finish", {
                "patient_id": "TUS-2026-0417", "resources": [{
                    "resource_type": "ecg", "source_id": "local-ecg-1",
                    "evidence_file_id": file_id,
                    "data": {
                        "subject": {"reference": "Patient/TUS-2026-0417"},
                        "conclusion": "Synthetic sinus rhythm",
                    },
                }],
            })

        client = FakeClient(script)
        runner = CopilotSkillRunner(
            settings(), client_factory=client.factory, require_runtime_token=False,
        )
        catalog = FileCatalog((settings().fixture_root / "files",))
        bundle = runner.retrieve("local-files", "TUS-2026-0417", [ResourceType.ecg], catalog)
        self.assertEqual("Synthetic sinus rhythm", bundle.resources[0].data["conclusion"])
        self.assertEqual(1, len(bundle.files))
        self.assertEqual(["local-files"], client.options["custom_agents"][0]["skills"])
        self.assertEqual(
            {"custom:finish", "custom:list_patient_files", "custom:open_patient_file", "custom:stop"},
            set(client.options["available_tools"]),
        )
        self.assertEqual({"list_patient_files", "open_patient_file", "finish", "stop"}, set(client.tools))
        self.assertNotIn(str(settings().fixture_root), json.dumps(client.prompt))

    def test_arbitrary_file_path_is_not_an_accepted_handle(self):
        client = FakeClient([("open_patient_file", {"file_id": "..\\OTHER\\record.xml"})])
        runner = CopilotSkillRunner(
            settings(), client_factory=client.factory, require_runtime_token=False,
        )
        with self.assertRaises(RuntimeError):
            runner.retrieve("local-files", "TUS-2026-0417", [ResourceType.ecg], FileCatalog(()))

    def test_unopened_file_cannot_be_evidence(self):
        client = FakeClient([
            ("list_patient_files", {}), ("finish", {
                "patient_id": "TUS-2026-0417", "resources": [{
                    "resource_type": "ecg", "source_id": "ecg", "evidence_file_id": "invented",
                    "data": {"subject": {"reference": "Patient/TUS-2026-0417"}},
                }],
            }),
        ])
        runner = CopilotSkillRunner(
            settings(), client_factory=client.factory, require_runtime_token=False,
        )
        with self.assertRaises(RuntimeError):
            runner.retrieve("local-files", "TUS-2026-0417", [ResourceType.ecg], FileCatalog(()))

    def test_file_read_limit_and_hash_recheck(self):
        with tempfile.TemporaryDirectory() as directory:
            patient = Path(directory) / "P1"
            patient.mkdir()
            path = patient / "report.json"
            path.write_text("x" * (4 * 1024 * 1024 + 1))
            catalog = FileCatalog((Path(directory),))
            record = catalog.find("P1")[0]
            with self.assertRaisesRegex(ValueError, "read limit"):
                catalog.open_for_skill(record, "P1")
            path.write_text("{}")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                catalog.open_for_skill(record, "P1")
