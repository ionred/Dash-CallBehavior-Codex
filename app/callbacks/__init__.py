"""Dash callbacks for the application."""
from __future__ import annotations

import base64
from datetime import date
from typing import Any, Dict

from dash import Dash, Input, Output, State, no_update
import dash

from app.services.event_service import EventService, LoadResult
from app.services.progress_manager import progress_manager
from app.services.task_runner import run_background
from app.utils.csv_validation import format_validation_errors, validate_account_csv


def register_callbacks(app: Dash, event_service: EventService) -> None:
    """Register Dash callbacks."""

    @app.callback(
        Output("event-dropdown", "options"),
        Output("event-dropdown", "value"),
        Output("subgroup-dropdown", "options"),
        Output("subgroup-dropdown", "value"),
        Input("refresh-events", "n_clicks"),
        Input("load-result-store", "data"),
        prevent_initial_call=False,
    )
    def refresh_event_options(refresh_clicks: int | None, load_result_data: dict | None):
        options = event_service.get_event_options(force_refresh=bool(refresh_clicks))
        event_options = [{"label": event, "value": event} for event in options.events]
        event_value = no_update
        subgroup_options = []
        subgroup_value = None
        if load_result_data:
            event_value = load_result_data.get("event")
            subgroup = load_result_data.get("subgroup")
            subgroup_options = [
                {"label": sg, "value": sg} for sg in options.subgroups_by_event.get(event_value, [])
            ]
            if subgroup and subgroup in options.subgroups_by_event.get(event_value, []):
                subgroup_value = subgroup
        return event_options, event_value, subgroup_options, subgroup_value

    @app.callback(
        Output("subgroup-dropdown", "options"),
        Output("subgroup-dropdown", "value"),
        Output("load-data", "disabled"),
        Input("event-dropdown", "value"),
        State("event-dropdown", "options"),
    )
    def update_subgroup_options(selected_event: str | None, event_options: list[dict]):
        if not selected_event:
            return [], None, True
        options = event_service.get_event_options()
        subgroups = options.subgroups_by_event.get(selected_event, [])
        subgroup_options = [{"label": sg, "value": sg} for sg in subgroups]
        subgroup_value = None
        if len(subgroups) == 1:
            subgroup_value = subgroups[0]
        load_enabled = bool(subgroup_value)
        return subgroup_options, subgroup_value, not load_enabled

    @app.callback(
        Output("load-data", "disabled"),
        Input("event-dropdown", "value"),
        Input("subgroup-dropdown", "value"),
        Input("load-result-store", "data"),
        Input("load-task-id", "data"),
    )
    def enable_load_button(
        event_value: str | None,
        subgroup_value: str | None,
        load_result_data: dict | None,
        load_task_id: str | None,
    ) -> bool:
        if load_task_id:
            return True
        if not event_value or not subgroup_value:
            return True
        if load_result_data and load_result_data.get("event") == event_value and load_result_data.get("subgroup") == subgroup_value:
            return True
        return False

    @app.callback(
        Output("load-task-id", "data"),
        Output("load-data", "children"),
        Output("progress-container", "children"),
        Input("load-data", "n_clicks"),
        State("event-dropdown", "value"),
        State("subgroup-dropdown", "value"),
        State("load-task-id", "data"),
        prevent_initial_call=True,
    )
    def start_load_task(
        n_clicks: int,
        event_value: str | None,
        subgroup_value: str | None,
        existing_task_id: str | None,
    ):
        if existing_task_id:
            progress_manager.update_progress(existing_task_id, "Cancellation requested…")
            progress_manager.cancel_task(existing_task_id)
            return existing_task_id, "Load Data", ["Cancelling current load…"]

        if not event_value or not subgroup_value:
            return no_update, no_update, ""

        task_id = progress_manager.create_task()

        def task_runner() -> None:
            event_service.load_event_data(task_id, event_value, subgroup_value)

        run_background(task_id, task_runner)
        return task_id, "Cancel", ["Loading accounts for event…"]

    @app.callback(
        Output("progress-container", "children"),
        Output("load-data", "children"),
        Output("load-result-store", "data"),
        Output("graphs", "className"),
        Output("cards", "className"),
        Output("queue-filter-container", "className"),
        Output("load-task-id", "data"),
        Input("progress-interval", "n_intervals"),
        State("load-task-id", "data"),
        State("event-dropdown", "value"),
        State("subgroup-dropdown", "value"),
        prevent_initial_call=True,
    )
    def monitor_progress(n_intervals: int, task_id: str | None, event_value: str | None, subgroup_value: str | None):
        if not task_id:
            return "", "Load Data", no_update, "graphs hidden", "cards hidden", "queue-filter hidden", None

        progress = progress_manager.get_progress(task_id)
        if not progress:
            return "", "Load Data", no_update, "graphs hidden", "cards hidden", "queue-filter hidden", None

        messages = html_list(progress.messages)

        if progress.has_error:
            progress_manager.remove_task(task_id)
            return (
                messages,
                "Load Data",
                None,
                "graphs hidden",
                "cards hidden",
                "queue-filter hidden",
                None,
            )

        if not progress.is_complete:
            return messages, "Cancel", no_update, no_update, no_update, no_update, task_id

        result: LoadResult | None = progress.result  # type: ignore[assignment]
        progress_manager.remove_task(task_id)
        if not result:
            return messages, "Load Data", None, "graphs hidden", "cards hidden", "queue-filter hidden", None

        payload = serialize_load_result(result)
        return (
            messages,
            "Load Data",
            payload,
            "graphs",
            "cards",
            "queue-filter",
            None,
        )

    def html_list(messages: list[str]) -> list[str]:
        return [html.Div(message) for message in messages]

    from dash import html

    @app.callback(
        Output("progress-interval", "disabled"),
        Input("load-task-id", "data"),
        Input("create-task-id", "data"),
        Input("progress-interval", "n_intervals"),
        prevent_initial_call=False,
    )
    def toggle_interval(load_task_id: str | None, create_task_id: str | None, _n: int):
        for task_id in (load_task_id, create_task_id):
            if task_id:
                progress = progress_manager.get_progress(task_id)
                if progress and not progress.is_complete and not progress.has_error:
                    return False
        return True

    @app.callback(
        Output("line-chart", "figure"),
        Output("bar-chart", "figure"),
        Output("description-card", "children"),
        Output("top-queues-card", "children"),
        Output("queue-dropdown", "options"),
        Output("queue-dropdown", "value"),
        Input("load-result-store", "data"),
        prevent_initial_call=True,
    )
    def render_results(load_result_data: dict | None):
        if not load_result_data:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, [], None
        line_chart = load_result_data.get("line_chart", [])
        bar_chart = load_result_data.get("bar_chart", [])
        description = load_result_data.get("description")
        top_queues = load_result_data.get("top_queues", [])
        queue_options = load_result_data.get("queue_options", [])
        queue_dropdown_options = [{"label": option, "value": option} for option in queue_options]
        figure_line = {
            "data": [
                {
                    "x": [item["call_date"] for item in line_chart],
                    "y": [item["call_count"] for item in line_chart],
                    "type": "scatter",
                    "mode": "lines+markers",
                    "name": "Call count",
                }
            ],
            "layout": {"title": "Calls by Date"},
        }
        figure_bar = {
            "data": [
                {
                    "x": [item["queue"] for item in bar_chart],
                    "y": [item["call_count"] for item in bar_chart],
                    "type": "bar",
                    "name": "Call count",
                }
            ],
            "layout": {"title": "Calls by Queue"},
        }
        description_children = [
            html.H3(description.get("event_name", "")),
            html.P(description.get("description", "")),
            html.P(f"Event date: {description.get('event_date')}") if description else None,
            html.P(
                f"Monitoring: {description.get('monitor_start')} to {description.get('monitor_end')}"
            )
            if description
            else None,
        ]
        top_queue_children = [html.H3("Top Queues")]
        for item in top_queues:
            top_queue_children.append(
                html.P(f"{item['queue']}: {item['count']} calls ({item['percentage']}%)")
            )
        return figure_line, figure_bar, description_children, top_queue_children, queue_dropdown_options, queue_options[0] if queue_options else None

    @app.callback(
        Output("line-chart", "figure"),
        Output("bar-chart", "figure"),
        Input("queue-dropdown", "value"),
        State("load-result-store", "data"),
        prevent_initial_call=True,
    )
    def filter_queue(queue_value: str | None, load_result_data: dict | None):
        if not load_result_data or not queue_value:
            return dash.no_update, dash.no_update
        counts_by_queue_date = load_result_data.get("counts_by_queue_date", {})
        total_calls_by_queue = load_result_data.get("total_calls_by_queue", {})
        line_data = counts_by_queue_date.get(queue_value, {}) if queue_value != "All" else load_result_data.get("line_chart", [])
        if queue_value == "All":
            line_chart = load_result_data.get("line_chart", [])
            bar_chart = load_result_data.get("bar_chart", [])
        else:
            line_chart = [
                {"call_date": date_key, "call_count": count}
                for date_key, count in sorted(line_data.items())
            ]
            bar_chart = [{"queue": queue_value, "call_count": total_calls_by_queue.get(queue_value, 0)}]
        figure_line = {
            "data": [
                {
                    "x": [item["call_date"] for item in line_chart],
                    "y": [item["call_count"] for item in line_chart],
                    "type": "scatter",
                    "mode": "lines+markers",
                    "name": "Call count",
                }
            ],
            "layout": {"title": "Calls by Date"},
        }
        figure_bar = {
            "data": [
                {
                    "x": [item["queue"] for item in bar_chart],
                    "y": [item["call_count"] for item in bar_chart],
                    "type": "bar",
                }
            ],
            "layout": {"title": "Calls by Queue"},
        }
        return figure_line, figure_bar

    @app.callback(
        Output("clear-data", "disabled"),
        Input("load-result-store", "data"),
        Input("event-dropdown", "value"),
        Input("subgroup-dropdown", "value"),
    )
    def update_clear_button(load_result_data: dict | None, event_value: str | None, subgroup_value: str | None):
        if load_result_data:
            return False
        if event_value or subgroup_value:
            return False
        return True

    @app.callback(
        Output("load-result-store", "data"),
        Output("graphs", "className"),
        Output("cards", "className"),
        Output("queue-filter-container", "className"),
        Output("event-dropdown", "value"),
        Output("subgroup-dropdown", "value"),
        Input("clear-data", "n_clicks"),
        State("event-dropdown", "value"),
        State("subgroup-dropdown", "value"),
        prevent_initial_call=True,
    )
    def clear_data(n_clicks: int, event_value: str | None, subgroup_value: str | None):
        return None, "graphs hidden", "cards hidden", "queue-filter hidden", None, None

    @app.callback(
        Output("create-modal", "className"),
        Input("open-create-modal", "n_clicks"),
        Input("close-create-modal", "n_clicks"),
        Input("cancel-create", "n_clicks"),
        State("create-modal", "className"),
        State("create-task-id", "data"),
        prevent_initial_call=True,
    )
    def toggle_modal(
        open_clicks: int | None,
        close_clicks: int | None,
        cancel_clicks: int | None,
        class_name: str,
        create_task_id: str | None,
    ) -> str:
        trigger = dash.callback_context.triggered_id
        if trigger == "open-create-modal":
            return "modal"
        if trigger == "cancel-create" and create_task_id:
            progress_manager.update_progress(create_task_id, "Cancellation requested…")
            progress_manager.cancel_task(create_task_id)
        return "modal hidden"

    @app.callback(
        Output("upload-feedback", "children"),
        Output("submit-create", "disabled"),
        Output("upload-store", "data"),
        Input("account-upload", "contents"),
        State("account-upload", "filename"),
        State("account-upload", "last_modified"),
        prevent_initial_call=True,
    )
    def validate_upload(contents: str, filename: str, last_modified: int):
        if not contents:
            return "No file uploaded", True, None
        content_type, content_string = contents.split(",", 1)
        decoded = base64.b64decode(content_string)
        validation = validate_account_csv(decoded)
        if not validation.is_valid:
            return format_validation_errors(validation.errors), True, None
        payload = {
            "accounts": validation.account_numbers,
            "filename": filename,
        }
        return f"{len(validation.account_numbers)} accounts validated from {filename}", False, payload

    @app.callback(
        Output("create-progress", "children"),
        Output("load-result-store", "data"),
        Output("progress-container", "children"),
        Output("create-modal", "className"),
        Output("create-task-id", "data"),
        Input("submit-create", "n_clicks"),
        State("upload-store", "data"),
        State("new-event-name", "value"),
        State("new-subgroup", "value"),
        State("new-description", "value"),
        State("new-event-date", "date"),
        State("new-monitor-start", "date"),
        State("new-monitor-end", "date"),
        State("event-strategy", "value"),
        prevent_initial_call=True,
    )
    def submit_event(
        n_clicks: int,
        upload_payload: dict | None,
        event_name: str,
        subgroup: str,
        description: str,
        event_date_value: str,
        monitor_start_value: str,
        monitor_end_value: str,
        strategy: str,
    ):
        if not upload_payload:
            return "Upload account numbers before submitting.", no_update, no_update, no_update, no_update

        if not all([event_name, subgroup, event_date_value, monitor_start_value, monitor_end_value]):
            return "Provide event name, subgroup, and all dates before submitting.", no_update, no_update, no_update, no_update

        task_id = progress_manager.create_task()
        event_date_obj = date.fromisoformat(event_date_value)
        monitor_start_obj = date.fromisoformat(monitor_start_value)
        monitor_end_obj = date.fromisoformat(monitor_end_value)

        def task_runner() -> None:
            event_service.create_or_update_event(
                task_id,
                event_name=event_name,
                subgroup=subgroup,
                description=description or "",
                event_date=event_date_obj,
                monitor_start=monitor_start_obj,
                monitor_end=monitor_end_obj,
                account_numbers=upload_payload["accounts"],
                strategy=strategy,
            )

        run_background(task_id, task_runner)
        return ["Starting event creation…"], no_update, no_update, "modal", task_id

    @app.callback(
        Output("create-progress", "children"),
        Output("load-result-store", "data"),
        Output("progress-container", "children"),
        Output("create-modal", "className"),
        Output("create-task-id", "data"),
        Input("progress-interval", "n_intervals"),
        State("create-task-id", "data"),
        prevent_initial_call=True,
    )
    def monitor_create_progress(n_intervals: int, task_id: str | None):
        if not task_id:
            return no_update, no_update, no_update, no_update, no_update
        progress = progress_manager.get_progress(task_id)
        if not progress:
            return no_update, no_update, no_update, no_update, no_update
        messages = [html.Div(msg) for msg in progress.messages]
        if progress.has_error:
            progress_manager.remove_task(task_id)
            return messages, no_update, progress.error_message, "modal", None
        if not progress.is_complete:
            return messages, no_update, no_update, "modal", task_id
        result: LoadResult | None = progress.result  # type: ignore[assignment]
        progress_manager.remove_task(task_id)
        if not result:
            return messages, no_update, no_update, "modal hidden", None
        payload = serialize_load_result(result)
        return messages, payload, [html.Div("Event created successfully.")], "modal hidden", None

    def serialize_load_result(result: LoadResult) -> Dict[str, Any]:
        metadata = result.event_metadata
        return {
            "event": metadata.event_name,
            "subgroup": metadata.subgroup,
            "description": {
                "event_name": metadata.event_name,
                "description": metadata.description,
                "event_date": metadata.event_date.isoformat(),
                "monitor_start": metadata.monitor_start.isoformat(),
                "monitor_end": metadata.monitor_end.isoformat(),
            },
            "line_chart": result.line_chart,
            "bar_chart": result.bar_chart,
            "queue_options": result.queue_options,
            "top_queues": result.top_queues,
            "counts_by_queue_date": result.counts_by_queue_date,
            "total_calls_by_queue": result.total_calls_by_queue,
        }

