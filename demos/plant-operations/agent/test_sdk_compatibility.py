"""Offline SDK regression checks; no model requests or desktop interaction."""

import json
import unittest
from unittest.mock import Mock, patch

import httpx2
from a2a.server.agent_execution.context import RequestContext
from a2a.server.context import ServerCallContext
from a2a.server.events import EventQueue
from a2a.types import TaskState, TaskStatusUpdateEvent
from openai import OpenAI
from PIL import Image
from starlette.testclient import TestClient

import agent
import config
import maintenance_advisor
from a2a_handler import SREAgentExecutor
from a2a_server import build_app
from screen import _encode


class RecordingQueue(EventQueue):
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


class A2AExecutorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = RequestContext(
            call_context=ServerCallContext(), task_id="task", context_id="context"
        )
        self.queue = RecordingQueue()
        self.executor = SREAgentExecutor()

    async def test_completed_events_include_summary(self):
        summary = {"done_reason": "Dry run", "actions": []}
        with patch("a2a_handler.run_sre_agent", return_value=summary) as run:
            await self.executor.execute(self.context, self.queue)
        run.assert_called_once_with()
        self.assertEqual(len(self.queue.events), 4)
        self.assertEqual(self.queue.events[0].id, "task")
        self.assertEqual(
            self.queue.events[1].status.state, TaskState.TASK_STATE_WORKING
        )
        self.assertEqual(
            json.loads(self.queue.events[2].artifact.parts[0].text), summary
        )
        self.assertEqual(
            self.queue.events[3].status.state, TaskState.TASK_STATE_COMPLETED
        )
        for event in self.queue.events[1:]:
            self.assertEqual(event.task_id, "task")
            self.assertEqual(event.context_id, "context")

    async def test_failure_is_reported(self):
        with patch("a2a_handler.run_sre_agent", side_effect=RuntimeError("offline failure")):
            await self.executor.execute(self.context, self.queue)
        self.assertEqual(len(self.queue.events), 3)
        status = self.queue.events[-1].status
        self.assertEqual(status.state, TaskState.TASK_STATE_FAILED)
        self.assertIn("offline failure", status.message.parts[0].text)

    async def test_cancel_event_uses_terminal_state(self):
        await self.executor.cancel(self.context, self.queue)
        self.assertEqual(len(self.queue.events), 1)
        self.assertIsInstance(self.queue.events[0], TaskStatusUpdateEvent)
        self.assertEqual(
            self.queue.events[0].status.state, TaskState.TASK_STATE_CANCELED
        )


class A2AServerTests(unittest.TestCase):
    def test_discovery_and_legacy_alias(self):
        with TestClient(build_app()) as client:
            response = client.get("/.well-known/agent-card.json")
            self.assertEqual(response.status_code, 200)
            card = response.json()
            self.assertEqual(card["supportedInterfaces"][0]["protocolVersion"], "1.0")
            self.assertEqual(card["supportedInterfaces"][0]["protocolBinding"], "JSONRPC")
            self.assertEqual(len(card["skills"]), 3)
            self.assertEqual(client.get("/.well-known/agent.json").json(), card)

    def test_native_and_legacy_jsonrpc_complete_without_running_agent(self):
        summary = {"done_reason": "Offline check", "actions": []}
        for method, role, part in (
            ("SendMessage", "ROLE_USER", {"text": "Check simulator"}),
            ("message/send", "user", {"kind": "text", "text": "Check simulator"}),
        ):
            with self.subTest(method=method):
                message = {"messageId": "request", "role": role, "parts": [part]}
                if method == "message/send":
                    message["kind"] = "message"
                with patch("a2a_handler.run_sre_agent", return_value=summary) as run:
                    with TestClient(build_app()) as client:
                        response = client.post(
                            "/",
                            headers={"A2A-Version": "1.0"} if method == "SendMessage" else {},
                            json={
                                "jsonrpc": "2.0",
                                "id": 1,
                                "method": method,
                                "params": {
                                    "message": message,
                                    "configuration": (
                                        {"blocking": True}
                                        if method == "message/send"
                                        else {"returnImmediately": False}
                                    ),
                                },
                            },
                        )
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertNotIn("error", result, result)
                task = result["result"].get("task", result["result"])
                self.assertIn(task["status"]["state"], ("TASK_STATE_COMPLETED", "completed"))
                self.assertEqual(json.loads(task["artifacts"][0]["parts"][0]["text"]), summary)
                run.assert_called_once_with()


class OpenAICompatibilityTests(unittest.TestCase):
    def test_api_key_and_entra_client_factories(self):
        endpoint = "https://example.invalid/api/projects/offline"
        for api_key in ("offline-test", ""):
            with self.subTest(api_key=bool(api_key)):
                credential = Mock()
                with (
                    patch.object(config, "AZURE_AI_FOUNDRY_ENDPOINT", endpoint),
                    patch.object(config, "AZURE_API_KEY", api_key),
                    patch.dict(
                        "os.environ",
                        {"AZURE_AI_FOUNDRY_ENDPOINT": endpoint, "AZURE_API_KEY": api_key},
                    ),
                    patch("azure.identity.DefaultAzureCredential", return_value=credential),
                ):
                    for factory in (agent._get_client, maintenance_advisor._get_client):
                        with factory() as client:
                            self.assertIsInstance(client, OpenAI)
                            self.assertEqual(str(client.base_url), endpoint + "/openai/v1/")
                credential.get_token.assert_not_called()

    def test_responses_dry_run_parses_real_computer_call_models(self):
        for batched in (False, True):
            with self.subTest(batched=batched):
                requests = []
                action = {"type": "click", "x": 20, "y": 30, "button": "left"}
                call = {
                    "type": "computer_call",
                    "id": "computer",
                    "call_id": "call",
                    "status": "completed",
                    "pending_safety_checks": [],
                    "actions" if batched else "action": [action] if batched else action,
                }

                def respond(request):
                    requests.append(json.loads(request.content))
                    return httpx2.Response(
                        200,
                        json={
                            "id": "response",
                            "object": "response",
                            "created_at": 1,
                            "model": "offline",
                            "output": [call],
                            "parallel_tool_calls": False,
                            "tool_choice": "auto",
                            "tools": [],
                        },
                    )

                image = Image.new("RGB", (32, 32), "green")
                screenshot = _encode(image)
                with (
                    OpenAI(
                        api_key="offline-test",
                        base_url="https://example.invalid/openai/v1/",
                        http_client=httpx2.Client(transport=httpx2.MockTransport(respond)),
                    ) as client,
                    patch.object(config, "AZURE_AI_FOUNDRY_ENDPOINT", "https://example.invalid"),
                    patch.object(agent, "_get_client", return_value=client),
                    patch.object(agent, "capture", return_value=(screenshot, image)),
                    patch.object(agent, "execute") as execute,
                    patch.object(agent, "display", agent.DisplayState()),
                ):
                    result = agent.run(dry_run=True)
                execute.assert_not_called()
                self.assertEqual(result["proposed_actions"], ["click"])
                self.assertEqual(result["actions"], [])
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0]["tools"][0]["type"], "computer_use_preview")
                self.assertEqual(
                    requests[0]["input"][0]["content"][1]["image_url"], screenshot
                )

    def test_advisor_chat_completion_uses_real_sdk_transport(self):
        requests = []

        def respond(request):
            requests.append(json.loads(request.content))
            return httpx2.Response(
                200,
                json={
                    "id": "chat",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "offline",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "No action needed."},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )

        with OpenAI(
            api_key="offline-test",
            base_url="https://example.invalid/openai/v1/",
            http_client=httpx2.Client(transport=httpx2.MockTransport(respond)),
        ) as client:
            result = maintenance_advisor.analyze_incidents(client, [])
        self.assertEqual(result, "No action needed.")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["model"], maintenance_advisor.MODEL_DEPLOYMENT)


if __name__ == "__main__":
    unittest.main()
