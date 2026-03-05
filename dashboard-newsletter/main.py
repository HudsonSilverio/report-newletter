# #  poetry run main.py - temporary test
# Run with: poetry run python main.py

import sys
sys.path.insert(0, ".")  # so Python can find the utils folder

from data_loader import load_data
import streamlit as st

# We call load_data but outside Streamlit for testing
# So we bypass the cache decorator temporarily
import pandas as pd

SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQmwFmfbdEZymO34CFSZ6xsZjLG89GaA8jOs216FsORPcwGk29uJaDLBxYs9HKaIbcS6cQSQWdEJBpm/pub?gid=0&single=true&output=csv"

df = pd.read_csv(SHEET_URL, skiprows=1)

print("=== COLUMNS ===")
print(df.columns.tolist())

print("\n=== FIRST 3 ROWS ===")
print(df.head(3))

print("\n=== SHAPE (rows x columns) ===")
print(df.shape)