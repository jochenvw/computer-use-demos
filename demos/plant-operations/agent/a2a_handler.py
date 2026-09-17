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
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

from agent import run as run_sre_agent


class SREAgentExecutor(AgentExecutor):
    """Executes the SRE agent in response to an A2A task request."""

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task_id = context.task_id
        context_id = context.context_id

        if context.current_task is None:
            await event_queue.enqueue_event(
                Task(
                    id=task_id,
                    context_id=context_id,
                    status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                    history=[context.message] if context.message is not None else [],
                )
            )

        await event_queue.enqueue_event(
            self._make_status_event(
                task_id, context_id, TaskState.TASK_STATE_WORKING, "SRE agent started."
            )
        )

        try:
            summary = await asyncio.to_thread(run_sre_agent)

            await event_queue.enqueue_event(
                self._make_artifact_event(task_id, context_id, summary)
            )
            await event_queue.enqueue_event(
                self._make_status_event(
                    task_id, context_id, TaskState.TASK_STATE_COMPLETED, "SRE agent finished."
                )
            )
        except Exception as exc:
            await event_queue.enqueue_event(
                self._make_status_event(
                    task_id,
                    context_id,
                    TaskState.TASK_STATE_FAILED,
                    f"SRE agent failed: {exc}",
                )
            )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        await event_queue.enqueue_event(
            self._make_status_event(
                context.task_id,
                context.context_id,
                TaskState.TASK_STATE_CANCELED,
                "Task canceled by request.",
            )
        )

    @staticmethod
    def _make_status_event(
        task_id: str,
        context_id: str,
        state: int,
        message_text: str,
    ) -> TaskStatusUpdateEvent:
        return TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=state,
                message=Message(
                    role=Role.ROLE_AGENT,
                    parts=[Part(text=message_text)],
                    message_id=str(uuid.uuid4()),
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
            artifact=Artifact(
                artifact_id="sre-agent-result",
                name="SRE Agent Execution Summary",
                parts=[Part(text=json.dumps(summary_dict, indent=2))],
            ),
        )
