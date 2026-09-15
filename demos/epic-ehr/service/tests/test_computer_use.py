import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from epic_adapter.adapters.computer_use import ComputerUseEpicAdapter
from epic_adapter.config import Settings
from epic_adapter.models import ResourceType


def call(name, values):
    return SimpleNamespace(output=[SimpleNamespace(
        type="function_call", call_id="call-1", name=name,
        arguments=json.dumps(values),
    )])


def settings():
    return replace(
        Settings.from_env(),
        backend="computer-use", computer_use_enabled=True,
        epic_origin="https://epic.example.invalid",
        foundry_endpoint="https://model.example.invalid",
        model_deployment="gpt-6-astra", browser_window_title="",
        browser_cdp_url="http://127.0.0.1:9222", max_browser_steps=3,
    )


class FakeBrowser:
    def __init__(self):
        self.actions = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def screenshot(self):
        return "data:image/jpeg;base64,c3ludGhldGlj"

    def execute(self, name, values):
        self.actions.append((name, values))


class ComputerUseTests(unittest.TestCase):
    def build(self, responses, config=None):
        self.browser = FakeBrowser()
        self.client = Mock()
        self.client.responses.create.side_effect = responses
        return ComputerUseEpicAdapter(
            config or settings(),
            client_factory=lambda: self.client,
            browser_factory=lambda _: self.browser,
        )

    def test_astra_uses_screenshots_actions_and_validates_result(self):
        adapter = self.build([
            call("click", {"x": 20, "y": 30}),
            call("finish", {
                "patient_id": "DEMO-100042",
                "resources": [{
                    "resource_type": "patient", "source_id": "DEMO-100042",
                    "data": {"name": [{"family": "Rivera"}]},
                }],
            }),
        ])
        result = adapter.retrieve("DEMO-100042", [ResourceType.patient])
        self.assertEqual("epic-browser-observed", result[0].provenance.source)
        self.assertEqual([("click", {"x": 20, "y": 30})], self.browser.actions)
        self.assertTrue(self.browser.closed)
        for request in self.client.responses.create.call_args_list:
            self.assertEqual("gpt-6-astra", request.kwargs["model"])
            self.assertFalse(request.kwargs["store"])
            self.assertFalse(request.kwargs["parallel_tool_calls"])

    def test_wrong_patient_fails_instead_of_returning_data(self):
        adapter = self.build([call("finish", {
            "patient_id": "OTHER",
            "resources": [{"resource_type": "patient", "source_id": "OTHER", "data": {}}],
        })])
        with self.assertRaises(ValueError):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])

    def test_other_subject_fails(self):
        adapter = self.build([call("finish", {
            "patient_id": "DEMO-100042",
            "resources": [{
                "resource_type": "ecg", "source_id": "ecg-1",
                "data": {"subject": {"reference": "Patient/OTHER"}},
            }],
        })])
        with self.assertRaises(ValueError):
            adapter.retrieve("DEMO-100042", [ResourceType.ecg])

    def test_model_cannot_type_arbitrary_text(self):
        adapter = self.build([call("type_text", {"text": "change prescription"})])
        with self.assertRaises(ValueError):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])
        self.assertEqual([], self.browser.actions)

    def test_unknown_tool_fails(self):
        adapter = self.build([call("navigate", {"url": "https://other.invalid"})])
        with self.assertRaises(ValueError):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])

    def test_expired_session_stops_without_more_actions(self):
        adapter = self.build([call("stop", {"reason": "session_expired"})])
        with self.assertRaises(RuntimeError):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])
        self.assertEqual([], self.browser.actions)

    def test_action_budget_is_enforced(self):
        adapter = self.build([call("observe", {})] * 3)
        with self.assertRaisesRegex(RuntimeError, "action limit"):
            adapter.retrieve("DEMO-100042", [ResourceType.patient])
        self.assertEqual(3, len(self.browser.actions))

    def test_remote_browser_debugging_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "loopback"):
            replace(settings(), browser_cdp_url="http://10.0.0.1:9222").validate()

    def test_live_opt_in_required(self):
        with self.assertRaises(RuntimeError):
            replace(settings(), computer_use_enabled=False).validate()
