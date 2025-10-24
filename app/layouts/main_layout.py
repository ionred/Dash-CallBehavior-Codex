"""Dash layout definitions."""
from __future__ import annotations

from dash import dcc, html


def layout() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="load-task-id"),
            dcc.Store(id="load-result-store"),
            dcc.Store(id="create-task-id"),
            dcc.Store(id="upload-store"),
            dcc.Interval(id="progress-interval", interval=1_000, n_intervals=0, disabled=True),
            html.Div(
                [
                    html.Button(
                        "\u21bb",
                        id="refresh-events",
                        className="btn icon",
                        title="Refresh events",
                    ),
                    dcc.Dropdown(id="event-dropdown", placeholder="Select event"),
                    dcc.Dropdown(id="subgroup-dropdown", placeholder="Select subgroup"),
                    html.Button("Load Data", id="load-data", className="btn primary", disabled=True),
                    html.Button("Clear", id="clear-data", className="btn", disabled=True),
                    html.Button("Create New Event", id="open-create-modal", className="btn link"),
                ],
                className="controls",
            ),
            html.Div(id="progress-container", className="progress-container"),
            html.Div(
                [
                    html.Div(dcc.Graph(id="line-chart"), className="graph"),
                    html.Div(dcc.Graph(id="bar-chart"), className="graph"),
                ],
                id="graphs",
                className="graphs hidden",
            ),
            html.Div(
                [
                    html.Div(id="description-card", className="card"),
                    html.Div(id="top-queues-card", className="card"),
                ],
                id="cards",
                className="cards hidden",
            ),
            html.Div(
                [
                    dcc.Dropdown(id="queue-dropdown", clearable=False),
                ],
                id="queue-filter-container",
                className="queue-filter hidden",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2("Create New Event"),
                                    html.Button("\u2715", id="close-create-modal", className="btn close"),
                                ],
                                className="modal-header",
                            ),
                            html.Div(
                                [
                                    dcc.Input(id="new-event-name", type="text", placeholder="Event name"),
                                    dcc.Input(id="new-subgroup", type="text", placeholder="Subgroup"),
                                    dcc.Textarea(id="new-description", placeholder="Description"),
                                    html.Div(
                                        [
                                            dcc.DatePickerSingle(id="new-event-date", display_format="YYYY-MM-DD"),
                                            dcc.DatePickerSingle(id="new-monitor-start", display_format="YYYY-MM-DD"),
                                            dcc.DatePickerSingle(id="new-monitor-end", display_format="YYYY-MM-DD"),
                                        ],
                                        className="date-pickers",
                                    ),
                                    dcc.Upload(
                                        id="account-upload",
                                        children=html.Div(["Drag and drop CSV or click to upload"]),
                                        multiple=False,
                                        className="upload",
                                    ),
                                    html.Div(id="upload-feedback", className="feedback"),
                                    dcc.RadioItems(
                                        id="event-strategy",
                                        options=[
                                            {"label": "Create new", "value": "new"},
                                            {"label": "Overwrite existing", "value": "overwrite"},
                                            {"label": "Append accounts", "value": "append"},
                                        ],
                                        value="new",
                                        className="strategy",
                                    ),
                                    html.Div(id="create-progress", className="progress-container"),
                                ],
                                className="modal-body",
                            ),
                            html.Div(
                                [
                                    html.Button("Cancel", id="cancel-create", className="btn"),
                                    html.Button("Submit", id="submit-create", className="btn primary", disabled=True),
                                ],
                                className="modal-footer",
                            ),
                        ],
                        className="modal-content",
                    )
                ],
                id="create-modal",
                className="modal hidden",
            ),
        ],
        className="app-container",
    )

