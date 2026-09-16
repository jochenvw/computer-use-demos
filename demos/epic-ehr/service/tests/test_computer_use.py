import inspect
import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path

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
        model_deployment="gpt-6-astra", browser_window_title="",
        browser_cdp_url="http://127.0.0.1:9222", max_browser_steps=4,
    )


def patient_result(patient_id="DEMO-100042"):
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
        self.prompt = json.loads(prompt)
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
        self.client = FakeClient(calls)
        return ComputerUseEpicAdapter(
            config or settings(), client_factory=self.client.factory,
            browser_factory=lambda _: self.browser,
        )

    def test_cli_skill_uses_screenshots_and_scoped_sdk_session(self):
        adapter = self.build([("observe", {}), ("finish", patient_result())])
        result = adapter.retrieve("DEMO-100042", [ResourceType.patient])
        self.assertEqual("epic-browser-observed", result[0].provenance.source)
        self.assertTrue(self.browser.closed)
        self.assertEqual(1, len(self.browser.threads))
        options = self.client.options
        self.assertEqual("gpt-6-astra", options["model"])
        self.assertEqual(["epic-browser"], options["custom_agents"][0]["skills"])
        self.assertEqual("empty", self.client.client_options["mode"])
        self.assertFalse(options["enable_config_discovery"])
        self.assertFalse(options["enable_session_store"])
        self.assertIsInstance(options["available_tools"], ToolSet)
        self.assertEqual(
            {"finish", "stop", "observe", "click", "type_text", "press_key", "scroll"},
            set(self.client.tools),
        )
        self.assertIn("name: epic-browser", self.client.skill_text)
        self.assertEqual("c3ludGhldGlj", self.client.results[0].binary_results_for_llm[0].data)
        self.assertTrue(self.client.aborted and self.client.disconnected and self.client.deleted)
        self.assertTrue(self.client.closed)
        self.assertFalse(Path(self.client.client_options["base_directory"]).exists())

    def test_wrong_patient_fails(self):
        adapter = self.build([("observe", {}), ("finish", patient_result("OTHER"))])
        with self.assertRaises(ValueError):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])

    def test_other_subject_fails(self):
        adapter = self.build([("observe", {}), ("finish", {
            "patient_id": "DEMO-100042", "resources": [{
                "resource_type": "ecg", "source_id": "ecg-1",
                "data": {"subject": {"reference": "Patient/OTHER"}},
            }],
        })])
        with self.assertRaises(ValueError):
            adapter.retrieve("DEMO-100042", [ResourceType.ecg])

    def test_model_cannot_type_arbitrary_text_or_recover_from_failure(self):
        adapter = self.build([
            ("type_text", {"text": "change prescription"}),
            ("observe", {}), ("finish", patient_result()),
        ])
        with self.assertRaises(ValueError):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])
        self.assertEqual([], self.browser.actions)
        self.assertEqual("denied", self.client.results[-1].result_type)

    def test_strict_host_tool_arguments(self):
        adapter = self.build([("click", {"x": True, "y": 0})])
        with self.assertRaises(ValueError):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])
        self.assertEqual([], self.browser.actions)

    def test_expired_session_stops(self):
        adapter = self.build([("stop", {"reason": "session_expired"})])
        with self.assertRaises(RuntimeError):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])

    def test_action_budget_is_enforced(self):
        adapter = self.build([("observe", {})] * 5)
        with self.assertRaisesRegex(RuntimeError, "action limit"):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])
        self.assertEqual(4, len(self.browser.actions))

    def test_timeout_aborts_deletes_and_closes_browser(self):
        async def timeout(client):
            await client.invoke("observe", {})
            raise TimeoutError("synthetic")

        adapter = self.build(timeout)
        with self.assertRaises(TimeoutError):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])
        self.assertTrue(self.client.aborted and self.client.deleted and self.browser.closed)

    def test_unexpected_builtin_permission_fails_closed(self):
        async def permission(client):
            decision = client.options["on_permission_request"]({}, {})
            self.assertEqual("denied-by-rules", decision.kind)
            await client.invoke("observe", {})

        adapter = self.build(permission)
        with self.assertRaisesRegex(RuntimeError, "unapproved"):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])
        self.assertEqual([], self.browser.actions)

    def test_remote_browser_debugging_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "loopback"):
            replace(settings(), browser_cdp_url="http://10.0.0.1:9222").validate()

    def test_live_opt_in_required(self):
        with self.assertRaises(RuntimeError):
            replace(settings(), computer_use_enabled=False).validate()


class LocalFileSkillTests(unittest.TestCase):
    def test_file_skill_lists_opens_and_returns_documented_ecg(self):
        async def script(client):
            listed = await client.invoke("list_patient_files", {})
            file_id = json.loads(listed.text_result_for_llm)[0]["file_id"]
            opened = await client.invoke("open_patient_file", {"file_id": file_id})
            self.assertIn("Synthetic sinus rhythm", opened.text_result_for_llm)
            await client.invoke("finish", {
                "patient_id": "DEMO-100042", "resources": [{
                    "resource_type": "ecg", "source_id": "local-ecg-1",
                    "evidence_file_id": file_id,
                    "data": {
                        "subject": {"reference": "Patient/DEMO-100042"},
                        "conclusion": "Synthetic sinus rhythm",
                    },
                }],
            })

        client = FakeClient(script)
        runner = CopilotSkillRunner(settings(), client_factory=client.factory)
        catalog = FileCatalog((settings().fixture_root / "files",))
        bundle = runner.retrieve("local-files", "DEMO-100042", [ResourceType.ecg], catalog)
        self.assertEqual("Synthetic sinus rhythm", bundle.resources[0].data["conclusion"])
        self.assertEqual(1, len(bundle.files))
        self.assertEqual(["local-files"], client.options["custom_agents"][0]["skills"])
        self.assertEqual({"list_patient_files", "open_patient_file", "finish", "stop"}, set(client.tools))
        self.assertNotIn(str(settings().fixture_root), json.dumps(client.prompt))

    def test_arbitrary_file_path_is_not_an_accepted_handle(self):
        client = FakeClient([("open_patient_file", {"file_id": "..\\OTHER\\record.xml"})])
        runner = CopilotSkillRunner(settings(), client_factory=client.factory)
        with self.assertRaises(ValueError):
            runner.retrieve("local-files", "DEMO-100042", [ResourceType.ecg], FileCatalog(()))

    def test_unopened_file_cannot_be_evidence(self):
        client = FakeClient([
            ("list_patient_files", {}), ("finish", {
                "patient_id": "DEMO-100042", "resources": [{
                    "resource_type": "ecg", "source_id": "ecg", "evidence_file_id": "invented",
                    "data": {"subject": {"reference": "Patient/DEMO-100042"}},
                }],
            }),
        ])
        runner = CopilotSkillRunner(settings(), client_factory=client.factory)
        with self.assertRaises(ValueError):
            runner.retrieve("local-files", "DEMO-100042", [ResourceType.ecg], FileCatalog(()))

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
