"""A2A task handler — bridges the A2A protocol to the SRE agent logic.

When an external agent sends a task via A2A, this handler executes the
SRE agent in a background thread and streams status/artifact events back
through the EventQueue.
"""

import asyncio
import json
import uuid

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

from agent import run as run_sre_agent


class SREAgentExecutor(AgentExecutor):
    """Executes the SRE agent in response to an A2A task request."""

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task_id = context.task_id
        context_id = context.context_id

        event_queue.enqueue_event(
            self._make_status_event(
                task_id, context_id, TaskState.working, "SRE agent started.", final=False
            )
        )

        try:
            summary = await asyncio.to_thread(run_sre_agent)

            event_queue.enqueue_event(
                self._make_artifact_event(task_id, context_id, summary)
            )
            event_queue.enqueue_event(
                self._make_status_event(
                    task_id, context_id, TaskState.completed, "SRE agent finished.", final=True
                )
            )
        except Exception as exc:
            event_queue.enqueue_event(
                self._make_status_event(
                    task_id,
                    context_id,
                    TaskState.failed,
                    f"SRE agent failed: {exc}",
                    final=True,
                )
            )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        event_queue.enqueue_event(
            self._make_status_event(
                context.task_id,
                context.context_id,
                TaskState.canceled,
                "Task canceled by request.",
                final=True,
            )
        )

    @staticmethod
    def _make_status_event(
        task_id: str,
        context_id: str,
        state: TaskState,
        message_text: str,
        *,
        final: bool,
    ) -> TaskStatusUpdateEvent:
        return TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            kind="status-update",
            final=final,
            status=TaskStatus(
                state=state,
                message=Message(
                    role=Role.agent,
                    parts=[Part(root=TextPart(text=message_text))],
                    message_id=str(uuid.uuid4()),
                    kind="message",
                ),
            ),
        )

    @staticmethod
    def _make_artifact_event(
        task_id: str, context_id: str, summary_dict: dict
    ) -> TaskArtifactUpdateEvent:
        return TaskArtifactUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            kind="artifact-update",
            artifact=Artifact(
                artifact_id="sre-agent-result",
                name="SRE Agent Execution Summary",
                parts=[Part(root=TextPart(text=json.dumps(summary_dict, indent=2)))],
            ),
        )
