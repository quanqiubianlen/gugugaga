"""Background task scheduler for autonomous agent operation.

Manages periodic tasks so the agent can take initiative:
- Morning/startup greeting
- Periodic system status checks
- Memory consolidation suggestions
- Idle check-ins when the user hasn't interacted in a while
"""

import time
from datetime import datetime
from typing import Any, Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class BackgroundScheduler(QObject):
    """Schedules autonomous agent tasks on configurable intervals.

    Signals
    -------
    check_in : str
        Emitted when the agent should initiate a conversation with a message.
    periodic_task : str
        Emitted with a task name when a scheduled task fires.
    """

    check_in = pyqtSignal(str)
    periodic_task = pyqtSignal(str, dict)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._enabled = True
        self._last_user_interaction = time.time()
        self._startup_time = time.time()
        self._tasks: list[dict[str, Any]] = []
        self._greeted_today = False

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(30_000)

        self._schedule_default_tasks()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def idle_seconds(self) -> float:
        return time.time() - self._last_user_interaction

    def user_interacted(self) -> None:
        self._last_user_interaction = time.time()

    def add_task(
        self,
        name: str,
        interval_seconds: int,
        callback: Callable[[], None] | None = None,
        start_hour: int | None = None,
        end_hour: int | None = None,
        cooldown_seconds: int = 0,
    ) -> None:
        self._tasks.append({
            "name": name,
            "interval": interval_seconds,
            "callback": callback,
            "start_hour": start_hour,
            "end_hour": end_hour,
            "cooldown": cooldown_seconds,
            "last_fired": 0.0,
        })

    def remove_task(self, name: str) -> None:
        self._tasks = [t for t in self._tasks if t["name"] != name]

    def _schedule_default_tasks(self) -> None:
        self.add_task(
            name="morning_greeting",
            interval_seconds=600,
            start_hour=6,
            end_hour=12,
            cooldown_seconds=86_400,
        )
        self.add_task(
            name="idle_checkin",
            interval_seconds=1800,
            cooldown_seconds=3600,
        )
        self.add_task(
            name="memory_consolidation",
            interval_seconds=600,
            start_hour=20,
            end_hour=22,
            cooldown_seconds=86_400,
        )

    def _tick(self) -> None:
        if not self._enabled:
            return

        now = time.time()
        hour = datetime.now().hour

        for task in self._tasks:
            if task["start_hour"] is not None and hour < task["start_hour"]:
                continue
            if task["end_hour"] is not None and hour >= task["end_hour"]:
                continue

            elapsed = now - task["last_fired"]
            if elapsed < task["interval"]:
                continue

            if task["cooldown"] > 0 and elapsed < task["cooldown"]:
                continue

            task["last_fired"] = now
            self._execute_task(task["name"])

    def _execute_task(self, name: str) -> None:
        if name == "morning_greeting":
            if not self._greeted_today:
                self._greeted_today = True
                now = datetime.now()
                self.check_in.emit(
                    f"早上好！现在是 {now.strftime('%H:%M')}，今天有什么我可以帮你的吗？"
                )
        elif name == "idle_checkin":
            if self.idle_seconds >= 1800:
                idle_min = int(self.idle_seconds / 60)
                self.check_in.emit(
                    f"你已经 {idle_min} 分钟没找我聊天了，需要我做点什么吗？"
                )
        elif name == "memory_consolidation":
            self.check_in.emit(
                "今天快结束了！要不要我帮你总结一下今天学到的东西，或者把重要的内容存进长期记忆？"
            )
        else:
            self.periodic_task.emit(name, {})

    def reset_daily(self) -> None:
        self._greeted_today = False

