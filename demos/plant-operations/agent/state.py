from __future__ import annotations

from config import MAX_STEPS, MAX_PARAMETER_CHANGES, REPEAT_ACTION_LIMIT


class TaskState:
    """Tracks SRE agent progress and enforces safety limits."""

    def __init__(self, goal: str) -> None:
        self.current_goal: str = goal
        self.step_count: int = 0
        self.last_actions: list[str] = []
        self.parameter_changes: int = 0
        self.alarm_acknowledged: bool = False
        self.alarm_resolved: bool = False
        self.done: bool = False
        self.abort_reason: str | None = None

    def record_action(self, description: str) -> None:
        self.step_count += 1
        self.last_actions.append(description)
        if len(self.last_actions) > REPEAT_ACTION_LIMIT:
            self.last_actions = self.last_actions[-REPEAT_ACTION_LIMIT:]

    def record_parameter_change(self) -> None:
        self.parameter_changes += 1

    def is_within_limits(self) -> bool:
        if self.step_count >= MAX_STEPS:
            self.abort_reason = f"Reached max steps ({MAX_STEPS})"
            return False

        if self.parameter_changes > MAX_PARAMETER_CHANGES:
            self.abort_reason = (
                f"Exceeded max parameter changes ({MAX_PARAMETER_CHANGES})"
            )
            return False

        if (
            len(self.last_actions) >= REPEAT_ACTION_LIMIT
            and len(set(self.last_actions[-REPEAT_ACTION_LIMIT:])) == 1
        ):
            self.abort_reason = (
                f"Last {REPEAT_ACTION_LIMIT} actions were identical: "
                f"'{self.last_actions[-1]}'"
            )
            return False

        return True

    def mark_done(self, reason: str) -> None:
        self.done = True
        self.current_goal = reason

    def summary(self) -> dict:
        return {
            "current_goal": self.current_goal,
            "step_count": self.step_count,
            "parameter_changes": self.parameter_changes,
            "alarm_acknowledged": self.alarm_acknowledged,
            "alarm_resolved": self.alarm_resolved,
            "done": self.done,
            "abort_reason": self.abort_reason,
            "last_actions": list(self.last_actions),
        }
