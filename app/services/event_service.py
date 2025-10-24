"""Domain services for event and call history operations."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Sequence

import pandas as pd

from config import AppConfig
from app.data_access.sql_repository import (
    CallHistoryRecord,
    EventListing,
    SqlRepository,
)
from app.services.cache_service import CacheService
from app.services.progress_manager import progress_manager
from app.utils.formatting import format_int

logger = logging.getLogger(__name__)


@dataclass
class EventMetadata:
    event_name: str
    subgroup: str
    event_date: date
    monitor_start: date
    monitor_end: date
    description: str


@dataclass
class EventOptions:
    events: List[str]
    subgroups_by_event: Dict[str, List[str]]
    metadata: Dict[tuple[str, str], EventMetadata]


@dataclass
class LoadResult:
    event_metadata: EventMetadata
    total_calls: int
    account_count: int
    line_chart: List[dict]
    bar_chart: List[dict]
    queue_options: List[str]
    top_queues: List[dict]
    counts_by_queue_date: Dict[str, Dict[str, int]]
    total_calls_by_queue: Dict[str, int]


class EventService:
    """Coordinates operations required by the Dash callbacks."""

    def __init__(self, config: AppConfig, repository: SqlRepository, cache_service: CacheService) -> None:
        self._config = config
        self._repository = repository
        self._cache = cache_service

    # ------------------------------------------------------------------
    # Event listings
    # ------------------------------------------------------------------
    def get_event_options(self, force_refresh: bool = False) -> EventOptions:
        cached = None if force_refresh else self._cache.get_event_listings()
        if cached:
            return cached

        listings = self._repository.fetch_event_listings()
        options = self._build_options(listings)
        self._cache.set_event_listings(options)
        return options

    def _build_options(self, listings: Sequence[EventListing]) -> EventOptions:
        events: Dict[str, List[str]] = defaultdict(list)
        metadata: Dict[tuple[str, str], EventMetadata] = {}
        for listing in listings:
            event_name = listing.event_name
            subgroup = listing.subgroup
            events[event_name].append(subgroup)
            metadata[(event_name.lower(), subgroup.lower())] = EventMetadata(
                event_name=event_name,
                subgroup=subgroup,
                event_date=date.fromisoformat(str(listing.event_date)),
                monitor_start=date.fromisoformat(str(listing.monitor_start)),
                monitor_end=date.fromisoformat(str(listing.monitor_end)),
                description=listing.description or "",
            )

        sorted_events = sorted(events.keys(), key=str.lower)
        subgroups_by_event = {
            event: sorted(subgroups, key=str.lower) for event, subgroups in events.items()
        }
        return EventOptions(events=sorted_events, subgroups_by_event=subgroups_by_event, metadata=metadata)

    # ------------------------------------------------------------------
    # Load event data
    # ------------------------------------------------------------------
    def load_event_data(self, task_id: str, event_name: str, subgroup: str) -> LoadResult:
        event_key = (event_name.lower(), subgroup.lower())
        options = self.get_event_options(force_refresh=False)
        metadata = options.metadata.get(event_key)
        if not metadata:
            raise ValueError("Selected event metadata is not available.")

        cached_payload: LoadResult | None = self._cache.get_raw_data(event_name, subgroup)
        if cached_payload:
            progress_manager.update_progress(task_id, "Using cached call history results.")
            progress_manager.complete_task(task_id, cached_payload)
            return cached_payload

        progress_manager.update_progress(task_id, "Loading accounts for event…")
        accounts = self._repository.fetch_accounts(event_name, subgroup)
        account_numbers = [account.account_number for account in accounts]
        account_count = len(account_numbers)
        progress_manager.update_progress(
            task_id,
            f"Inserting {format_int(account_count)} account records for call history query…",
        )
        if progress_manager.is_cancelled(task_id):
            raise RuntimeError("Task cancelled")

        temp_table = self._repository.insert_temp_accounts(account_numbers)
        progress_manager.update_progress(
            task_id,
            "Querying call history for "
            f"{format_int(account_count)} accounts from dates {metadata.monitor_start} to {metadata.monitor_end}…",
        )

        if progress_manager.is_cancelled(task_id):
            raise RuntimeError("Task cancelled")

        call_history = self._repository.query_call_history(
            temp_table, str(metadata.monitor_start), str(metadata.monitor_end)
        )
        total_calls = len(call_history)
        progress_manager.update_progress(
            task_id,
            f"{format_int(total_calls)} calls found for dates {metadata.monitor_start} to {metadata.monitor_end}. Rendering data…",
        )

        if progress_manager.is_cancelled(task_id):
            raise RuntimeError("Task cancelled")

        payload = self._build_load_result(metadata, account_count, call_history)
        self._cache.set_raw_data(event_name, subgroup, payload)
        progress_manager.complete_task(task_id, payload)
        return payload

    def _build_load_result(
        self,
        metadata: EventMetadata,
        account_count: int,
        call_history: Sequence[CallHistoryRecord],
    ) -> LoadResult:
        if not call_history:
            return LoadResult(
                event_metadata=metadata,
                total_calls=0,
                account_count=account_count,
                line_chart=[],
                bar_chart=[],
                queue_options=["All"],
                top_queues=[],
                counts_by_queue_date={},
                total_calls_by_queue={},
            )

        df = pd.DataFrame(
            {
                "queue": [record.queue_name or "Unknown" for record in call_history],
                "talk_time": [record.talk_time for record in call_history],
                "call_date": [record.call_date for record in call_history],
            }
        )
        df["call_date"] = pd.to_datetime(df["call_date"]).dt.date
        counts_by_date = df.groupby("call_date").size().reset_index(name="call_count").sort_values("call_date")
        line_chart = [
            {"call_date": row.call_date.isoformat(), "call_count": int(row.call_count)}
            for row in counts_by_date.itertuples()
        ]

        counts_by_queue = df.groupby("queue").size().reset_index(name="call_count")
        counts_by_queue = counts_by_queue.sort_values("call_count", ascending=False)
        bar_chart = [
            {"queue": row.queue, "call_count": int(row.call_count)}
            for row in counts_by_queue.itertuples()
        ]

        queue_options = ["All"] + [row.queue for row in counts_by_queue.itertuples()]

        total_calls = int(counts_by_queue["call_count"].sum())
        top_queues = []
        for row in counts_by_queue.head(3).itertuples():
            percentage = (row.call_count / total_calls) * 100 if total_calls else 0
            top_queues.append(
                {
                    "queue": row.queue,
                    "count": int(row.call_count),
                    "percentage": round(percentage, 2),
                }
            )

        grouped = df.groupby(["queue", "call_date"]).size().to_dict()
        counts_by_queue_date: Dict[str, Dict[str, int]] = defaultdict(dict)
        for (queue, call_date), value in grouped.items():
            counts_by_queue_date[str(queue)][str(call_date)] = int(value)

        total_calls_by_queue = {
            str(row.queue): int(row.call_count) for row in counts_by_queue.itertuples()
        }

        return LoadResult(
            event_metadata=metadata,
            total_calls=len(call_history),
            account_count=account_count,
            line_chart=line_chart,
            bar_chart=bar_chart,
            queue_options=queue_options,
            top_queues=top_queues,
            counts_by_queue_date=dict(counts_by_queue_date),
            total_calls_by_queue=total_calls_by_queue,
        )


    def filter_graphs(self, load_result: LoadResult, queue_selection: str) -> tuple[List[dict], List[dict]]:
        """Return chart data filtered by queue selection."""

        if queue_selection.lower() == "all":
            return load_result.line_chart, load_result.bar_chart

        queue_key = None
        for option in load_result.queue_options:
            if option.lower() == queue_selection.lower():
                queue_key = option
                break
        if not queue_key:
            return [], []

        counts_by_date = load_result.counts_by_queue_date.get(queue_key, {})
        line_chart = [
            {"call_date": date_key, "call_count": count}
            for date_key, count in sorted(counts_by_date.items())
        ]
        bar_chart = [{"queue": queue_key, "call_count": load_result.total_calls_by_queue.get(queue_key, 0)}]
        return line_chart, bar_chart

    # ------------------------------------------------------------------
    # Create event workflow
    # ------------------------------------------------------------------
    def get_existing_event_summary(self, event_name: str, subgroup: str) -> dict:
        options = self.get_event_options(force_refresh=False)
        metadata = options.metadata.get((event_name.lower(), subgroup.lower()))
        account_count = self._repository.get_event_account_count(event_name, subgroup)
        return {
            "exists": metadata is not None,
            "account_count": account_count,
            "metadata": metadata,
        }

    def create_or_update_event(
        self,
        task_id: str,
        *,
        event_name: str,
        subgroup: str,
        description: str,
        event_date: date,
        monitor_start: date,
        monitor_end: date,
        account_numbers: Sequence[str],
        strategy: str,
    ) -> LoadResult:
        if not account_numbers:
            raise ValueError("No account numbers were provided.")

        normalized_strategy = strategy.lower()
        valid_strategies = {"new", "overwrite", "append"}
        if normalized_strategy not in valid_strategies:
            raise ValueError("Unknown event creation strategy.")

        progress_manager.update_progress(task_id, "Starting event creation workflow…")
        if progress_manager.is_cancelled(task_id):
            raise RuntimeError("Task cancelled")
        connection = self._repository.begin_transaction()
        call_history: Sequence[CallHistoryRecord] = []
        try:
            existing_event = self._repository.event_exists(connection, event_name, subgroup)
            existing_account_count = self._repository.count_event_accounts(connection, event_name, subgroup)

            if existing_event and normalized_strategy == "new":
                raise ValueError("Event already exists.")

            if existing_event and normalized_strategy == "overwrite":
                progress_manager.update_progress(task_id, "Removing existing event details…")
                if progress_manager.is_cancelled(task_id):
                    raise RuntimeError("Task cancelled")
                self._repository.delete_event_accounts(connection, event_name, subgroup)
                self._repository.delete_event_listing(connection, event_name, subgroup)

            if not existing_event and existing_account_count:
                progress_manager.update_progress(task_id, "Clearing orphaned account records…")
                if progress_manager.is_cancelled(task_id):
                    raise RuntimeError("Task cancelled")
                self._repository.delete_event_accounts(connection, event_name, subgroup)

            if normalized_strategy in {"new", "overwrite"} or not existing_event:
                progress_manager.update_progress(task_id, "Writing event listing entry…")
                if progress_manager.is_cancelled(task_id):
                    raise RuntimeError("Task cancelled")
                self._repository.upsert_event_listing(
                    connection,
                    event_name,
                    subgroup,
                    str(event_date),
                    str(monitor_start),
                    str(monitor_end),
                    description,
                )
            else:
                progress_manager.update_progress(task_id, "Retaining existing event listing entry…")

            if normalized_strategy == "append" and existing_event:
                progress_manager.update_progress(task_id, "Appending new account numbers…")
                if progress_manager.is_cancelled(task_id):
                    raise RuntimeError("Task cancelled")
                self._repository.append_event_accounts(connection, event_name, subgroup, account_numbers)
            else:
                progress_manager.update_progress(task_id, "Inserting account numbers…")
                if progress_manager.is_cancelled(task_id):
                    raise RuntimeError("Task cancelled")
                self._repository.insert_event_accounts(connection, event_name, subgroup, account_numbers)

            progress_manager.update_progress(task_id, "Loading call history for new event…")
            if progress_manager.is_cancelled(task_id):
                raise RuntimeError("Task cancelled")
            temp_table = self._repository.insert_temp_accounts(account_numbers)
            call_history = self._repository.query_call_history(
                temp_table, str(monitor_start), str(monitor_end)
            )

            progress_manager.update_progress(task_id, "Aggregating call history for member research…")
            if progress_manager.is_cancelled(task_id):
                raise RuntimeError("Task cancelled")
            self._repository.delete_member_research(connection, event_name, subgroup)
            member_research_records = self._build_member_research_records(
                event_name, subgroup, call_history
            )
            if member_research_records:
                self._repository.insert_member_research(connection, member_research_records)

            self._repository.commit(connection)
            progress_manager.update_progress(task_id, "Finalizing event creation…")
        except Exception as exc:  # noqa: BLE001
            self._repository.rollback(connection)
            progress_manager.fail_task(task_id, str(exc))
            raise

        self._cache.set_event_listings(None)
        self._cache.delete_raw_data(event_name, subgroup)

        load_result = self._build_load_result(
            EventMetadata(
                event_name=event_name,
                subgroup=subgroup,
                event_date=event_date,
                monitor_start=monitor_start,
                monitor_end=monitor_end,
                description=description,
            ),
            len(account_numbers),
            call_history,
        )

        self._cache.set_raw_data(event_name, subgroup, load_result)
        progress_manager.complete_task(task_id, load_result)
        return load_result

    def _build_member_research_records(
        self,
        event_name: str,
        subgroup: str,
        call_history: Sequence[CallHistoryRecord],
    ) -> List[tuple[str, str, str, str, int, float]]:
        if not call_history:
            return []

        df = pd.DataFrame(
            {
                "queue": [record.queue_name or "Unknown" for record in call_history],
                "talk_time": [record.talk_time for record in call_history],
                "call_date": [record.call_date for record in call_history],
            }
        )
        df["call_date"] = pd.to_datetime(df["call_date"]).dt.date
        grouped = df.groupby(["queue", "call_date"])
        results: List[tuple[str, str, str, str, int, float]] = []
        for (queue, call_date), frame in grouped:
            results.append(
                (
                    event_name,
                    subgroup,
                    str(queue),
                    call_date.isoformat(),
                    int(frame.shape[0]),
                    float(frame["talk_time"].mean() if not frame["talk_time"].empty else 0.0),
                )
            )
        return results

