#  poetry run data_loader.py

#print("1, 2, 11, 2")

# utils/data_loader.py
# This file is responsible for ONE thing only:
# reading and cleaning data from Google Sheets

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
    """
    # skiprows=1 skips the first "Means" row in your sheet
    df = pd.read_csv(SHEET_URL, skiprows=1)

    # Rename columns to simple snake_case names
    # This makes the code easier to read and type
    df = df.rename(columns={
        "Title":                    "title",
        "Author(s)":                "author",
        "Date":                     "date",
        "Opens %":                  "opens_pct",
        "Clicks %":                 "clicks_pct",
        "Opens Raw":                "opens_raw",
        "Clicks Raw":               "clicks_raw",
        "Views on site":            "views",
        "Unsubscribe clicks":       "unsubscribes",
        "Tool starts":              "tool_starts",
        "Average rating":           "avg_rating",
        "% 4s and 5s":              "pct_positive",
        "% 1s":                     "pct_negative",
        "Number of ratings":        "num_ratings",
    })

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