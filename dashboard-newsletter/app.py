# poetry run streamlit run app.py
# This is the main file of your Streamlit dashboard
# Run with: poetry run streamlit run app.py

import streamlit as st
import plotly.express as px
import pandas as pd
import sys

# Tells Python to look in the current folder for modules
sys.path.insert(0, ".")

from data_loader import load_data, load_means

# -------------------------------------------------------
# PAGE CONFIGURATION
# This must be the FIRST streamlit command in the file
# -------------------------------------------------------
st.set_page_config(
    page_title="Newsletter Dashboard",
    page_icon="📧",
    layout="wide"  # uses the full width of the screen
)

# -------------------------------------------------------
# LOAD DATA
# -------------------------------------------------------
df = load_data()

means = load_means()
avg_open = means["avg_open_rate"]  # comes from cell D1 of your sheet
# -------------------------------------------------------
# HEADER
# -------------------------------------------------------
st.title("📧 Newsletter Performance Dashboard")
st.markdown("Interactive timeline of newsletter metrics")
st.divider()

# -------------------------------------------------------
# TOP KPI CARDS
# These show the most important numbers at a glance
# -------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

with col1:
    avg_opens = df["opens_pct"].mean()
    st.metric(label="Avg Open Rate", value=f"{avg_opens:.1f}%")

with col2:
    avg_clicks = df["clicks_pct"].mean()
    st.metric(label="Avg Click Rate", value=f"{avg_clicks:.2f}%")

with col3:
    avg_rating = df["avg_rating"].mean()
    st.metric(label="Avg Rating", value=f"{avg_rating:.2f} ⭐")

with col4:
    total_emails = len(df)
    st.metric(label="Total Newsletters", value=total_emails)

st.divider()

# -------------------------------------------------------
# SIDEBAR FILTERS
# The sidebar lets the user filter the data
# -------------------------------------------------------
st.sidebar.header("🔍 Filters")

# Date range filter
min_date = df["date"].min().date()
max_date = df["date"].max().date()

date_range = st.sidebar.date_input(
    "Date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# Author filter
all_authors = ["All"] + sorted(df["author"].dropna().unique().tolist())
selected_author = st.sidebar.selectbox("Author", all_authors)

# Apply filters to the dataframe
filtered_df = df.copy()

if len(date_range) == 2:
    filtered_df = filtered_df[
        (filtered_df["date"].dt.date >= date_range[0]) &
        (filtered_df["date"].dt.date <= date_range[1])
    ]

if selected_author != "All":
    filtered_df = filtered_df[filtered_df["author"] == selected_author]

st.sidebar.markdown(f"**{len(filtered_df)} newsletters** selected")

# -------------------------------------------------------
# CHART 1 — Open Rate Over Time
# -------------------------------------------------------
# -------------------------------------------------------
# CHART 1 — Open Rate Over Time
# -------------------------------------------------------
st.subheader("📬 Open (%)")

# Create a new column in the dataframe with that average value
# Every row gets the same number — this creates a flat horizontal line
filtered_df["avg_opens_line"] = avg_open

# Build the chart with TWO lines using go (Graph Objects)
# px.line only draws one line easily — go gives us full control
import plotly.graph_objects as go

fig1 = go.Figure()

# LINE 1 — The actual Open Rate per newsletter (blue)
fig1.add_trace(go.Scatter(
    x=filtered_df["date"],
    y=filtered_df["opens_pct"],
    mode="lines+markers",       # line AND dots
    name="Open %",              # this is the legend label
    line=dict(color="#4C9BE8", width=2),
    marker=dict(size=8),
    hovertemplate="<b>%{customdata[0]}</b><br>Author: %{customdata[1]}<br>Open Rate: %{y:.1f}%<extra></extra>",
    customdata=filtered_df[["title", "author"]].values
))

# LINE 2 — The average line (red, dashed)
fig1.add_trace(go.Scatter(
    x=filtered_df["date"],
    y=filtered_df["avg_opens_line"],
    mode="lines",               # only line, no dots
    name=f"Average Open % Across All Newsletters",  # legend label
    line=dict(color="#E8554C", width=2, dash="dash"),  # dashed red line
))

fig1.update_layout(
    hovermode="x unified",
    legend=dict(
        orientation="h",        # horizontal legend
        yanchor="bottom",
        y=-0.3,                 # places legend below the chart
        xanchor="left",
        x=0
    ),
    xaxis_title="Date",
    yaxis_title="Open Rate (%)",
)

st.plotly_chart(fig1, use_container_width=True)

# -------------------------------------------------------
# CHART 2 — Click Rate Over Time
# -------------------------------------------------------
st.subheader("🖱️ Click Rate Over Time (%)")

fig2 = px.line(
    filtered_df,
    x="date",
    y="clicks_pct",
    hover_name="title",
    hover_data={"author": True, "clicks_pct": ":.2f"},
    markers=True,
    labels={"date": "Date", "clicks_pct": "Click Rate (%)"},
)
fig2.update_traces(line_color="#F4845F", marker_size=8)
fig2.update_layout(hovermode="x unified")
st.plotly_chart(fig2, use_container_width=True)

# -------------------------------------------------------
# CHART 3 — Average Rating Over Time
# -------------------------------------------------------
st.subheader("⭐ Average Rating Over Time")

fig3 = px.bar(
    filtered_df,
    x="date",
    y="avg_rating",
    hover_name="title",
    hover_data={"author": True, "avg_rating": ":.2f"},
    labels={"date": "Date", "avg_rating": "Average Rating"},
    color="avg_rating",
    color_continuous_scale="Blues",
)
fig3.update_layout(coloraxis_showscale=False)
st.plotly_chart(fig3, use_container_width=True)

# -------------------------------------------------------
# CHART 4 — Raw Opens and Clicks Over Time
# -------------------------------------------------------
st.subheader("📊 Raw Opens & Clicks Over Time")

fig4 = px.line(
    filtered_df,
    x="date",
    y=["opens_raw", "clicks_raw"],
    hover_name="title",
    markers=True,
    labels={"date": "Date", "value": "Count", "variable": "Metric"},
)
fig4.update_layout(hovermode="x unified")
st.plotly_chart(fig4, use_container_width=True)

# -------------------------------------------------------
# DATA TABLE
# Shows the raw data at the bottom so the user can inspect it
# -------------------------------------------------------
st.divider()
st.subheader("📋 Raw Data Table")

st.dataframe(
    filtered_df[["date", "title", "author", "opens_pct", "clicks_pct", "avg_rating", "opens_raw", "clicks_raw"]].sort_values("date", ascending=False),
    use_container_width=True,
    hide_index=True,
)