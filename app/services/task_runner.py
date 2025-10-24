"""Background task execution utilities."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from app.services.progress_manager import progress_manager

_executor = ThreadPoolExecutor(max_workers=4)


def run_background(task_id: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    def _runner() -> None:
        try:
            func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            progress_manager.fail_task(task_id, str(exc))
        finally:
            pass

    _executor.submit(_runner)

