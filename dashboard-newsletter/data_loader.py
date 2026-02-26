# #  poetry run data_loader.py

import pandas as pd
import streamlit as st

# -------------------------------------------------------
# Your Google Sheet public CSV link
# This works because you made the sheet public
# -------------------------------------------------------
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQmwFmfbdEZymO34CFSZ6xsZjLG89GaA8jOs216FsORPcwGk29uJaDLBxYs9HKaIbcS6cQSQWdEJBpm/pub?output=csv"

# -------------------------------------------------------
# Portuguese month names → English
# pandas only understands English dates
# -------------------------------------------------------
MONTH_MAP = {
    "Jan": "Jan", "Fev": "Feb", "Mar": "Mar", "Abr": "Apr",
    "Mai": "May", "Jun": "Jun", "Jul": "Jul", "Ago": "Aug",
    "Set": "Sep", "Out": "Oct", "Nov": "Nov", "Dez": "Dec"
}

def clean_number(value):
    """
    Removes commas and % signs from numbers.
    "1,040.58" → 1040.58
    "49%"      → 49.0
    """
    if pd.isna(value):
        return None
    value = str(value).replace(",", "").replace("%", "").strip()
    try:
        return float(value)
    except:
        return None

def translate_date(date_str):
    """
    Translates Portuguese month abbreviations to English.
    "Fev 11, 2026" → "Feb 11, 2026"
    """
    if pd.isna(date_str):
        return None
    for pt, en in MONTH_MAP.items():
        date_str = str(date_str).replace(pt, en)
    return date_str

@st.cache_data(ttl=3600)
def load_data():
    """
    Loads data from Google Sheets and returns a clean DataFrame.

    @st.cache_data means Streamlit saves the result in memory.
    ttl=3600 means it refreshes automatically every 1 hour.
    This avoids hitting Google Sheets on every page interaction.

    FIX: Renaming columns by POSITION instead of by name.
    This avoids crashes caused by spacing or capitalization
    differences in the Google Sheets published CSV.
    """
    # skiprows=1 skips the first "Means" row in your sheet
    df = pd.read_csv(SHEET_URL, skiprows=1)

    # Rename by position — immune to spacing/capitalization issues
    # This matches exactly the column order in your CSV file
    # AFTER
    df.columns = [
        "title",            # A - Title
        "author",           # B - Author(s)
        "date",             # C - Date
        "audience",         # D - Audience ← NEW
        "opens_pct",        # E - Opens %
        "avg_rating",       # F - Average rating
        "pct_positive",     # G - % 4s and 5s
        "pct_negative",     # H - % 1s
        "stars_5",          # I - 5★ Excellent
        "stars_4",          # J - 4★ Good
        "stars_3",          # K - 3★ Okay
        "stars_2",          # L - 2★ Subpar
        "stars_1",          # M - 1★ Bad
        "unsubscribes",     # N - Unsubscribe clicks
        "tool_starts",      # O - Tool starts
        "topics",           # P - Topics
        "author_excited",   # Q - Author particularly excited?
        "high_value",       # R - Is it a high value read?
        "listacle",         # S - Listacle format?
        "is_general",       # T - Is it general (not niche)?
        "controversial",    # U - Controversial?
        "life_applicable",  # V - Life-applicable?
        "day_posted",       # W - Day posted
        "native_ads_nonsw", # X - Native ads for non-SW projects?
        "native_ads_sw",    # Y - Native ads for SW projects?
        "clicks_pct",       # Z - Clicks %
        "opens_raw",        # AA - Opens Raw
        "clicks_raw",       # AB - Clicks Raw
        "num_ratings",      # AC - Number of ratings
        "views",            # AD - Views on site
    ]

    # List of columns that need number cleaning
    number_cols = [
        "opens_pct", "clicks_pct", "opens_raw", "clicks_raw",
        "views", "unsubscribes", "tool_starts", "avg_rating",
        "pct_positive", "pct_negative", "num_ratings"
    ]

    # Apply clean_number to every value in each column
    for col in number_cols:
        if col in df.columns:
            df[col] = df[col].apply(clean_number)

    # Translate dates and convert to proper datetime type
    df["date"] = df["date"].apply(translate_date)
    df["date"] = pd.to_datetime(df["date"], format="%b %d, %Y", errors="coerce")

    # Remove rows with no date (empty rows from the sheet)
    df = df.dropna(subset=["date"])

    # Sort oldest → newest (essential for timeline charts)
    df = df.sort_values("date").reset_index(drop=True)

    return df

# -------------------------------------------------------
# Reads only the Means row (row 1)
# -------------------------------------------------------
@st.cache_data(ttl=3600)
def load_means():
    """
    Reads ONLY the first row of the sheet (the Means row).

    header=None → pandas does NOT treat row 1 as column names
    nrows=1     → reads only 1 row, faster than loading everything

    Column positions based on your CSV structure:
    iloc[0, 3] → D1 = Opens %
    iloc[0, 4] → E1 = Average Rating
    iloc[0, 5] → F1 = % 4s and 5s
    iloc[0, 6] → G1 = % 1s
    """
    df_means = pd.read_csv(SHEET_URL, header=None, nrows=1)

    avg_open_rate    = clean_number(df_means.iloc[0, 4])  # E1 - Open Rate
    avg_rating       = clean_number(df_means.iloc[0, 5])  # F1 - Average Rating
    avg_pct_positive = clean_number(df_means.iloc[0, 6])  # G1 - % 4s and 5s
    avg_pct_negative = clean_number(df_means.iloc[0, 7])  # H1 - % 1s

    return {
        "avg_open_rate":    avg_open_rate    or 0.0,
        "avg_rating":       avg_rating       or 0.0,
        "avg_pct_positive": avg_pct_positive or 0.0,
        "avg_pct_negative": avg_pct_negative or 0.0,
    }