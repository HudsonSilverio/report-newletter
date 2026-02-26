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
st.title("Clearer Thinking Newsletter Dashboard")
st.markdown("Interactive timeline of newsletter metrics")
st.divider()

# -------------------------------------------------------
# HEADER — Latest Newsletter + Comparison with Averages
# -------------------------------------------------------

# Gets the most recent newsletter (last row after sorting by date)
latest = df.sort_values("date", ascending=False).iloc[0]

st.subheader("Latest Newsletter")
st.markdown(f"### {latest['title']}")
st.markdown(f"**Author:** {latest['author']} &nbsp;&nbsp;|&nbsp;&nbsp; **Sent on:** {latest['date'].strftime('%b %d, %Y')} &nbsp;&nbsp;|&nbsp;&nbsp; **Audience:** {latest['audience']}")

st.divider()

# 4 columns — one for each metric
col1, col2, col3, col4 = st.columns(4)

with col1:
    # delta shows the difference between latest and the all-time average
    # if positive → green arrow, if negative → red arrow
    st.metric(
        label="Opens %",
        value=f"{latest['opens_pct']:.1f}%",
        delta=f"{latest['opens_pct'] - means['avg_open_rate']:.1f}% vs avg {means['avg_open_rate']:.2f}%"
    )

with col2:
    st.metric(
        label="Average Rating",
        value=f"{latest['avg_rating']:.1f}",
        delta=f"{latest['avg_rating'] - means['avg_rating']:.2f} vs avg {means['avg_rating']:.2f}"
    )

with col3:
    st.metric(
        label="% 4s and 5s",
        value=f"{latest['pct_positive']:.0f}%",
        delta=f"{latest['pct_positive'] - means['avg_pct_positive']:.0f}% vs avg {means['avg_pct_positive']:.0f}%"
    )

with col4:
    delta_negative = latest['pct_negative'] - means['avg_pct_negative']
    st.metric(
        label="% 1s",
        value=f"{latest['pct_negative']:.0f}%",
        delta=delta_negative,  # passing a NUMBER, not a string
        delta_color="normal"
    )

st.divider()

st.subheader("Historical data")

st.sidebar.header("🔍 Filters")

# Date range filter
min_date = df["date"].min().date()
max_date = df["date"].max().date()

start_date = st.sidebar.date_input(
    "Start",
    value=min_date,
    min_value=min_date,
    max_value=max_date
)

end_date = st.sidebar.date_input(
    "End",
    value=max_date,
    min_value=min_date,
    max_value=max_date
)

# Author filter
all_authors = ["All"] + sorted(df["author"].dropna().unique().tolist())
selected_author = st.sidebar.selectbox("Author", all_authors)

# Apply filters to the dataframe
filtered_df = df.copy()

filtered_df = filtered_df[
    (filtered_df["date"].dt.date >= start_date) &
    (filtered_df["date"].dt.date <= end_date)
]

if selected_author != "All":
    filtered_df = filtered_df[filtered_df["author"] == selected_author]

st.sidebar.markdown(f"**{len(filtered_df)} newsletters** selected")


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
    hovertemplate="<b>%{customdata[0]}</b><br>Open Rate: %{y:.1f}%<br>Author: %{customdata[1]}<extra></extra>",
    customdata=filtered_df[["title", "author"]].values
))

# LINE 2 — The average line (red, dashed)
fig1.add_trace(go.Scatter(
    x=filtered_df["date"],
    y=filtered_df["avg_opens_line"],
    mode="lines",               # only line, no dots
    name=f"Average All",  # legend label
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
# CHART 2 — Average Rating Over Time
# -------------------------------------------------------
st.subheader("⭐ Average Rating")

avg_rating_mean = means["avg_rating"]
filtered_df["avg_rating_line"] = avg_rating_mean

fig2 = go.Figure()

fig2.add_trace(go.Scatter(
    x=filtered_df["date"],
    y=filtered_df["avg_rating"],
    mode="lines+markers",
    name="Average Rating",
    line=dict(color="#4C9BE8", width=2),
    marker=dict(size=8, symbol="circle"),
    hovertemplate="<b>%{customdata[0]}</b><br>Average Rating: %{y:.2f}<br>Author: %{customdata[1]}<extra></extra>",
    customdata=filtered_df[["title", "author"]].values
))

fig2.add_trace(go.Scatter(
    x=filtered_df["date"],
    y=filtered_df["avg_rating_line"],
    mode="lines",
    name=f"Average All",
    line=dict(color="#E8554C", width=2, dash="dash"),
))

fig2.update_layout(
    hovermode="x unified",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.3,
        xanchor="left",
        x=0
    ),
)

st.plotly_chart(fig2, use_container_width=True)

# -------------------------------------------------------
# CHART 3 — % Positive Ratings Over Time
# -------------------------------------------------------
st.subheader("👍 % Positive Ratings (4s and 5s)")

avg_pct_positive_mean = means["avg_pct_positive"]
filtered_df["avg_pct_positive_line"] = avg_pct_positive_mean

fig3 = go.Figure()

# LINE 1 — The actual % Positive per newsletter (green)
fig3.add_trace(go.Scatter(
    x=filtered_df["date"],
    y=filtered_df["pct_positive"],
    mode="lines+markers",
    name="4s And 5s %",
    line=dict(color="#4C9BE8", width=2),
    marker=dict(size=8, symbol="circle"),
    hovertemplate="<b>%{customdata[0]}</b><br>% Positive: %{y:.1f}%<br>Author: %{customdata[1]}<extra></extra>",
    customdata=filtered_df[["title", "author"]].values
))

# LINE 2 — The global mean from cell F1 (red dashed)
fig3.add_trace(go.Scatter(
    x=filtered_df["date"],
    y=filtered_df["avg_pct_positive_line"],
    mode="lines",
    name="Average All %",
    line=dict(color="#E8554C", width=2, dash="dash"),
))

fig3.update_layout(
    hovermode="x unified",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.3,
        xanchor="left",
        x=0
    ),
)

st.plotly_chart(fig3, use_container_width=True)

# -------------------------------------------------------
# CHART 4 — % Negative Ratings Over Time
# -------------------------------------------------------
st.subheader("👎 % Negative Ratings (1s)")

avg_pct_negative_mean = means["avg_pct_negative"]
filtered_df["avg_pct_negative_line"] = avg_pct_negative_mean

fig4 = go.Figure()

# LINE 1 — The actual % Negative per newsletter (red)
fig4.add_trace(go.Scatter(
    x=filtered_df["date"],
    y=filtered_df["pct_negative"],
    mode="lines+markers",
    name="% (1s)",
    line=dict(color="#4C9BE8", width=2),
    marker=dict(size=8, symbol="circle"),
    hovertemplate="<b>%{customdata[0]}</b><br>% Negative: %{y:.1f}%<br>Author: %{customdata[1]}<extra></extra>",
    customdata=filtered_df[["title", "author"]].values
))

# LINE 2 — The global mean from cell G1 (dashed)
fig4.add_trace(go.Scatter(
    x=filtered_df["date"],
    y=filtered_df["avg_pct_negative_line"],
    mode="lines",
    name="Average All %",
    line=dict(color="#E8554C", width=2, dash="dash"),
))

fig4.update_layout(
    hovermode="x unified",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.3,
        xanchor="left",
        x=0
    ),
)

st.plotly_chart(fig4, use_container_width=True)

# # -------------------------------------------------------
# # DATA TABLE
# # Shows the raw data at the bottom so the user can inspect it
# # -------------------------------------------------------
# st.divider()
# st.subheader("📋 Raw Data Table")

# st.dataframe(
#     filtered_df[["date", "title", "author", "opens_pct", "clicks_pct", "avg_rating", "opens_raw", "clicks_raw"]].sort_values("date", ascending=False),
#     use_container_width=True,
#     hide_index=True,
# )