"""Manage long-running task progress for Dash callbacks."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class TaskProgress:
    """Represents the state of a background task."""

    messages: List[str] = field(default_factory=list)
    is_complete: bool = False
    has_error: bool = False
    error_message: Optional[str] = None
    result: Optional[object] = None


class ProgressManager:
    """Thread-safe registry of task progress information."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: Dict[str, TaskProgress] = {}
        self._cancellations: Dict[str, threading.Event] = {}

    def create_task(self) -> str:
        task_id = uuid.uuid4().hex
        with self._lock:
            self._tasks[task_id] = TaskProgress()
            self._cancellations[task_id] = threading.Event()
        return task_id

    def get_progress(self, task_id: str) -> TaskProgress | None:
        with self._lock:
            return self._tasks.get(task_id)

    def update_progress(self, task_id: str, message: str) -> None:
        with self._lock:
            progress = self._tasks.get(task_id)
            if progress:
                progress.messages.append(message)

    def complete_task(self, task_id: str, result: object | None = None) -> None:
        with self._lock:
            progress = self._tasks.get(task_id)
            if progress:
                progress.is_complete = True
                progress.result = result

    def fail_task(self, task_id: str, error_message: str) -> None:
        with self._lock:
            progress = self._tasks.get(task_id)
            if progress:
                progress.has_error = True
                progress.error_message = error_message
                progress.is_complete = True

    def cancel_task(self, task_id: str) -> None:
        with self._lock:
            cancel_event = self._cancellations.get(task_id)
        if cancel_event:
            cancel_event.set()

    def is_cancelled(self, task_id: str) -> bool:
        with self._lock:
            cancel_event = self._cancellations.get(task_id)
            return cancel_event.is_set() if cancel_event else False

    def remove_task(self, task_id: str) -> None:
        with self._lock:
            self._tasks.pop(task_id, None)
            cancel_event = self._cancellations.pop(task_id, None)
            if cancel_event:
                cancel_event.set()


progress_manager = ProgressManager()


ProgressCallback = Callable[[str], None]

