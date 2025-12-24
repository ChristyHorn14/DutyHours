#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Duty Hours Dashboard (geofence logs)

Key fix vs prior version:
- Duty hours are computed ONLY from valid Arrived -> Left sessions per Location.
- Long calls are allowed up to ~40 hours (buffered to 45) to avoid phantom multi-day gaps.
"""

import pandas as pd
from datetime import timedelta
import dash
from dash import dcc, html, Input, Output
import plotly.express as px


# ----------------------------
# Data ingest
# ----------------------------

def read_data(url: str):
    """Read an xlsx published URL (Google Sheets -> output=xlsx) and return {sheet_name: df}."""
    if url.endswith("xlsx"):
        xls = pd.ExcelFile(url)
        data_dict = {}
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name, header=None)
            df.columns = ["DateandTime", "ArrivedLeft", "Address", "Location"]
            data_dict[sheet_name] = df
        return data_dict
    return None


# URLs of input files
urls = [
    # SNGH/CHKD
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRJLmScGNhDn3mbvK_p70EWYiT3GjBR-zu-Aj7CvtjlTXFlAWN-2moM9NnDauqx3HpoAVm9E3I14hTl/pub?output=xlsx",
    # CHKD Concert Drive
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vS83REQuNZP0bIeYtG2IsRO3258pTYbOSB-54xxGzuzG05JtuIogdYpsXdpwtu8dP-K-GKqDj6f0ww-/pub?output=xlsx",
    # Princess Anne Clinic
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSroGmVZhp_KSqCsoybYavTc756Bw-pmW3cYl-QVQQgc7HUXhG_Heng61PdFDhqjbdJie709v4nLWHr/pub?output=xlsx",
    # Med Spa
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vStqLb5FKbYEHQhJt3gPf8caZRbdIsCudJ4rgP21zG-25i5p0f8IHxwY0NYEpsJkjx9Cz61WmH_y6q0/pub?output=xlsx",
    # PSCT
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vS1BtBOQgupdLdSy3dZh7rZpTvG7TkoswSg9tK298wt497189ueiuuWqbVYtRY5A6xlhkfkvp5NK3EL/pub?output=xlsx",
    # CHKD Chesapeake
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSQmW9rM4OXUVqgIo4p9gB0z1ySSQPTOBFuBBRr8wjPLXjK0uTtMOWmzFFMgUsVCqiqlNBovOptIHnr/pub?output=xlsx",
]

# Read all sheets from all URLs
dfs = []
for url in urls:
    data_dict = read_data(url)
    if isinstance(data_dict, dict):
        for df_ in data_dict.values():
            dfs.append(df_)
    elif isinstance(data_dict, pd.DataFrame):
        dfs.append(data_dict)

combined_df = pd.concat(dfs, ignore_index=True)
combined_df = combined_df[["DateandTime", "ArrivedLeft", "Address", "Location"]].copy()

# Save raw combined data (optional, useful for debugging)
combined_df.to_csv("combined_data.csv", index=False)

# Parse datetime
data = combined_df.copy()

# This matches your Google Timeline export style:
# e.g., "December 11, 2025 at 05:46AM"
data["DateandTime"] = pd.to_datetime(
    data["DateandTime"],
    format="%B %d, %Y at %I:%M%p",
    errors="coerce",
)

# Drop rows that failed to parse
data = data.dropna(subset=["DateandTime"])

# Sort
data = data.sort_values(by=["Location", "DateandTime"]).reset_index(drop=True)

# De-dupe: keep unique events (Location+DateandTime+ArrivedLeft is safer than DateandTime alone)
data = data.drop_duplicates(subset=["Location", "DateandTime", "ArrivedLeft"], keep="first")


# ----------------------------
# Session pairing (Arrived -> Left)
# ----------------------------

MAX_SHIFT_HOURS = 45  # real max ≈ 40, with a buffer to avoid false rejects

def pair_arrive_left(g: pd.DataFrame) -> pd.DataFrame:
    """
    For one Location:
    - Pair each 'Left location' with the most recent unmatched 'Arrived at location'.
    - Allow long stints up to MAX_SHIFT_HOURS.
    - Ignore unmatched arrivals/lefts (prevents phantom multi-day spikes).
    """
    g = g.sort_values("DateandTime").copy()

    open_start = None
    open_addr = None
    open_loc = None
    rows = []

    for t, event, addr, loc in zip(g["DateandTime"], g["ArrivedLeft"], g["Address"], g["Location"]):
        if event == "Arrived at location":
            # Keep the most recent arrival; overwrites duplicates/noise.
            open_start = t
            open_addr = addr
            open_loc = loc

        elif event == "Left location" and open_start is not None:
            hours = (t - open_start).total_seconds() / 3600.0

            if 0 < hours <= MAX_SHIFT_HOURS:
                rows.append(
                    {
                        # Attribute session to start time (works well for weekly/day grouping)
                        "DateandTime": open_start,
                        "Location": open_loc,
                        "Address": open_addr,
                        "TimeElapsed": hours,
                    }
                )

            # Close the session either way
            open_start = None
            open_addr = None
            open_loc = None

    return pd.DataFrame(rows)

df = (
    data.groupby("Location", group_keys=False)
    .apply(pair_arrive_left)
    .reset_index(drop=True)
)

# Save clean sessions (optional)
df.to_csv("combined_datawtimes.csv", index=False)

# If you want a quick sanity check in the console:
if not df.empty:
    print("Longest valid session (hrs):", df["TimeElapsed"].max())
    print("Total duty hours in dataset:", df["TimeElapsed"].sum())


# ----------------------------
# Dash app
# ----------------------------

# Date picker range defaults (last 30 days)
if df.empty:
    # fallback so app doesn't crash if no data
    min_date = (pd.Timestamp.today() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    max_date = (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
else:
    min_date = (df["DateandTime"].max() + timedelta(days=-30)).strftime("%Y-%m-%d")
    max_date = (df["DateandTime"].max() + timedelta(days=1)).strftime("%Y-%m-%d")

app = dash.Dash(__name__)

colors = {
    "background": "#f9f9f9",
    "text": "#333333",
    "accent": "#007bff",
}

app.layout = html.Div(
    style={"backgroundColor": colors["background"], "fontFamily": "Arial, sans-serif"},
    children=[
        html.H1(
            children="Duty Hours Dashboard",
            style={"textAlign": "center", "color": colors["accent"], "marginTop": "40px"},
        ),
        html.Div(
            [
                html.Label("Select Date Range", style={"color": colors["text"], "marginRight": "10px"}),
                dcc.DatePickerRange(
                    id="date-range-picker",
                    start_date=min_date,
                    end_date=max_date,
                    display_format="YYYY-MM-DD",
                    style={"marginRight": "20px"},
                ),
            ],
            style={"marginBottom": "30px", "marginTop": "20px", "textAlign": "center"},
        ),
        html.Div([dcc.Graph(id="graph1", style={"height": "400px"})], style={"marginBottom": "40px", "textAlign": "center"}),
        html.Div([dcc.Graph(id="graph2", style={"height": "400px"})], style={"marginBottom": "40px", "textAlign": "center"}),
        html.Div([dcc.Graph(id="graph4", style={"height": "400px"})], style={"marginBottom": "40px", "textAlign": "center"}),
        html.Div([dcc.Graph(id="graph3", style={"height": "400px"})], style={"marginBottom": "40px", "textAlign": "center"}),
    ],
)

@app.callback(
    [Output("graph1", "figure"),
     Output("graph2", "figure"),
     Output("graph3", "figure"),
     Output("graph4", "figure")],
    [Input("date-range-picker", "start_date"),
     Input("date-range-picker", "end_date")]
)
def update_graphs(start_date, end_date):
    filtered_df = df[(df["DateandTime"] >= start_date) & (df["DateandTime"] <= end_date)].copy()

    total_duty_hours = float(filtered_df["TimeElapsed"].sum()) if not filtered_df.empty else 0.0

    duty_hours_by_day = (
        filtered_df.groupby(filtered_df["DateandTime"].dt.date)["TimeElapsed"].sum()
        if not filtered_df.empty else pd.Series(dtype=float)
    )

    duty_hours_by_location = (
        filtered_df.groupby("Location")["TimeElapsed"].sum()
        if not filtered_df.empty else pd.Series(dtype=float)
    )

    # Week number (00-53). If you truly want Monday-Sunday,
    # this is acceptable; for ISO weeks you can switch to dt.isocalendar().week
    duty_hours_by_week = (
        filtered_df.groupby(filtered_df["DateandTime"].dt.strftime("%W"))["TimeElapsed"].sum()
        if not filtered_df.empty else pd.Series(dtype=float)
    )

    fig1 = px.bar(
        x=["Total Duty Hours"],
        y=[total_duty_hours],
        text=[round(total_duty_hours)],
        labels={"x": "Date Range", "y": "Duty Hours"},
        title="Duty Hours per Specified Time Period",
        color_discrete_sequence=[colors["accent"]],
    )
    fig1.update_traces(texttemplate="%{text}", textposition="inside")
    fig1.update_layout(plot_bgcolor=colors["background"], paper_bgcolor=colors["background"], font_color=colors["text"])

    fig2 = px.bar(
        x=duty_hours_by_day.index.astype(str) if not duty_hours_by_day.empty else [],
        y=duty_hours_by_day.values if not duty_hours_by_day.empty else [],
        text=duty_hours_by_day.values.round() if not duty_hours_by_day.empty else [],
        labels={"x": "Day", "y": "Duty Hours"},
        title="Duty Hours per Specified Time Period by Day",
        color_discrete_sequence=[colors["accent"]],
    )
    fig2.update_traces(texttemplate="%{text}", textposition="inside")
    fig2.update_layout(plot_bgcolor=colors["background"], paper_bgcolor=colors["background"], font_color=colors["text"])

    fig3 = px.bar(
        x=duty_hours_by_location.index if not duty_hours_by_location.empty else [],
        y=duty_hours_by_location.values if not duty_hours_by_location.empty else [],
        text=duty_hours_by_location.values.round() if not duty_hours_by_location.empty else [],
        labels={"x": "Location", "y": "Duty Hours"},
        title="Duty Hours per Specified Time Period by Location",
        color_discrete_sequence=[colors["accent"]],
    )
    fig3.update_traces(texttemplate="%{text}", textposition="inside")
    fig3.update_layout(plot_bgcolor=colors["background"], paper_bgcolor=colors["background"], font_color=colors["text"])

    fig4 = px.bar(
        x=duty_hours_by_week.index.astype(str) if not duty_hours_by_week.empty else [],
        y=duty_hours_by_week.values if not duty_hours_by_week.empty else [],
        text=duty_hours_by_week.values.round() if not duty_hours_by_week.empty else [],
        labels={"x": "Week", "y": "Duty Hours"},
        title="Duty Hours per Specified Time Period by Week (Monday to Sunday)",
        color_discrete_sequence=[colors["accent"]],
    )
    fig4.update_traces(texttemplate="%{text}", textposition="inside")
    fig4.update_layout(plot_bgcolor=colors["background"], paper_bgcolor=colors["background"], font_color=colors["text"])

    return fig1, fig2, fig3, fig4


# For Gunicorn compatibility
server = app.server

# If you run locally, uncomment:
# if __name__ == "__main__":
#     app.run_server(debug=True)
