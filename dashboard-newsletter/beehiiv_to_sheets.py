"""
Beehiiv → Google Sheets integration script.

Fetches newsletter data from the Beehiiv API and inserts a new row
into the Google Sheets spreadsheet used by the Streamlit dashboard.

Usage:
    python beehiiv_to_sheets.py "Newsletter Title Here"
    python beehiiv_to_sheets.py   # will prompt for the title
"""

import os
import re
import sys
from datetime import datetime, timezone

import gspread
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=_env_path, override=True)

BEEHIIV_API_KEY = os.getenv("BEEHIIV_API_KEY", "")
PUBLICATION_ID = os.getenv("BEEHIIV_PUBLICATION_ID", "")
_script_dir = os.path.dirname(os.path.abspath(__file__))
_creds_default = os.path.join(_script_dir, "credentials.json")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", _creds_default)
if not os.path.isabs(GOOGLE_CREDENTIALS_PATH):
    GOOGLE_CREDENTIALS_PATH = os.path.join(_script_dir, GOOGLE_CREDENTIALS_PATH)
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

BEEHIIV_BASE_URL = "https://api.beehiiv.com/v2"

# Star-rating URL patterns (case-insensitive substring match)
# Matched against base_url or url of each click entry.
# Order matters: 5-stars is checked before 1-star to avoid false matches.
STAR_PATTERNS = {
    5: ["newsletter-rating-5-star"],
    4: ["newsletter-rating-4-star"],
    3: ["newsletter-rating-3-star"],
    2: ["newsletter-rating-2-star"],
    1: ["newsletter-rating-1-star"],
}


# -------------------------------------------------------
# Beehiiv API
# -------------------------------------------------------
def beehiiv_get(endpoint, params=None):
    """Make an authenticated GET request to the Beehiiv API."""
    url = f"{BEEHIIV_BASE_URL}{endpoint}"
    headers = {"Authorization": f"Bearer {BEEHIIV_API_KEY}"}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def find_post_by_title(title_query):
    """
    Search for a post whose subject_line or title contains the query string.
    Returns the first matching post dict (with stats), or None.
    """
    page = 1
    while True:
        data = beehiiv_get(
            f"/publications/{PUBLICATION_ID}/posts",
            params={
                "expand[]": "stats",
                "status": "confirmed",
                "page": page,
                "limit": 50,
            },
        )
        posts = data.get("data", [])
        if not posts:
            break

        query_lower = title_query.lower()
        for post in posts:
            subject = (post.get("subject_line") or "").lower()
            title = (post.get("title") or "").lower()
            if query_lower in subject or query_lower in title:
                return post

        # Check pagination
        total_pages = data.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1

    return None


def extract_star_clicks(post):
    """
    Extract unique click counts for each star rating (5 to 1)
    by matching URLs against known patterns.

    Returns dict {5: count, 4: count, 3: count, 2: count, 1: count}
    """
    stars = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    stats = post.get("stats")
    if not stats:
        return stars

    clicks = stats.get("clicks", [])
    if not clicks:
        return stars

    matched_urls = []
    for click_entry in clicks:
        # Prefer base_url (clean, no UTM params), fall back to url
        url = (click_entry.get("base_url") or click_entry.get("url") or "").lower()
        email_stats = click_entry.get("email", {})
        unique_clicks = email_stats.get("unique_clicks", 0) if email_stats else 0

        for star_rating, patterns in STAR_PATTERNS.items():
            if any(pattern in url for pattern in patterns):
                stars[star_rating] = unique_clicks
                matched_urls.append((star_rating, url, unique_clicks))
                break

    if matched_urls:
        print("\nMatched star-rating URLs:")
        for rating, url, clicks_count in sorted(matched_urls, reverse=True):
            print(f"  {rating}*: {clicks_count} unique clicks - {url[:80]}")
    else:
        print("\nNo star-rating URLs matched. Click URLs found:")
        for click_entry in clicks:
            url = click_entry.get("url", "")
            email_stats = click_entry.get("email", {})
            uc = email_stats.get("unique_clicks", 0) if email_stats else 0
            print(f"  {uc:>4} clicks - {url[:100]}")
        print(
            "\nTip: Update STAR_PATTERNS in beehiiv_to_sheets.py to match your rating URLs."
        )

    return stars


def extract_open_rate(post):
    """Extract open rate percentage from post stats."""
    stats = post.get("stats", {})
    email = stats.get("email", {})
    return email.get("open_rate", 0)


def extract_authors(post):
    """Extract authors as comma-separated string."""
    authors = post.get("authors", [])
    return ", ".join(authors) if authors else ""


def extract_date(post):
    """Extract publish date formatted as 'Mon DD, YYYY'."""
    publish_ts = post.get("publish_date") or post.get("displayed_date") or post.get("created")
    if publish_ts:
        dt = datetime.fromtimestamp(publish_ts, tz=timezone.utc)
        return dt.strftime("%b %d, %Y")
    return ""


# -------------------------------------------------------
# Google Sheets
# -------------------------------------------------------
def get_sheets_client():
    """Authenticate with Google Sheets using service account credentials."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=scopes)
    return gspread.authorize(creds)


def insert_row_to_sheet(title, author, date_str, open_rate, stars):
    """
    Insert a new data row at position 3 (below header) in the Google Sheet.
    Also inserts formulas and updates the Means row AVERAGE ranges.
    """
    client = get_sheets_client()
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1

    # Build the row (columns A through N)
    # A=Title, B=Author, C=Date, D=Audience(blank), E=Opens%,
    # F=formula, G=formula, H=formula,
    # I=5*, J=4*, K=3*, L=2*, M=1*, N=formula
    row = [
        title,                          # A - Title
        author,                         # B - Author(s)
        date_str,                       # C - Date
        "All Subscribers",              # D - Audience
        open_rate,                      # E - Opens %
        "",                             # F - placeholder for formula
        "",                             # G - placeholder for formula
        "",                             # H - placeholder for formula
        stars[5],                       # I - 5* Excellent
        stars[4],                       # J - 4* Good
        stars[3],                       # K - 3* Okay
        stars[2],                       # L - 2* Subpar
        stars[1],                       # M - 1* Bad
        "",                             # N - placeholder for formula
    ]

    # Insert the new row at position 3 (pushes existing rows down)
    sheet.insert_row(row, index=3)

    # Set formulas in the new row 3
    # F3: Average rating rounded to 1 decimal (e.g. 3.1)
    # G3: % positive (4s & 5s) as percentage (e.g. 43%)
    # H3: % negative (1s) as percentage (e.g. 18%)
    # N3: Total ratings
    formulas = {
        "F3": "=ROUND(5*(I3/N3)+4*(J3/N3)+3*(K3/N3)+2*(L3/N3)+1*(M3/N3),1)",
        "G3": "=SUM(I3:J3)/N3",
        "H3": "=M3/N3",
        "N3": "=SUM(I3:M3)",
    }
    for cell, formula in formulas.items():
        sheet.update_acell(cell, formula)

    # Format G3 and H3 as percentage (0% format, e.g. 43%, 18%)
    sheet.format("G3", {"numberFormat": {"type": "PERCENT", "pattern": "0%"}})
    sheet.format("H3", {"numberFormat": {"type": "PERCENT", "pattern": "0%"}})

    # Update Means row (row 1) AVERAGE formulas to include the new row
    update_means_formulas(sheet)

    print(f"\nRow inserted at position 3 in the spreadsheet.")


def update_means_formulas(sheet):
    """
    Update the AVERAGE formulas in row 1 (Means row) to include
    the expanded data range after inserting a new row.

    Reads current formulas, finds the AVERAGE range end row,
    and increments it by 1.
    """
    means_cells = ["E1", "F1", "G1", "H1"]

    for cell_addr in means_cells:
        try:
            # Get the current formula
            current = sheet.acell(cell_addr, value_render_option="FORMULA").value
            if not current or not current.startswith("="):
                continue

            # Update range end: e.g. AVERAGE(E3:E35) → AVERAGE(E3:E36)
            updated = _increment_range_end(current)
            if updated != current:
                sheet.update_acell(cell_addr, updated)
                print(f"  Updated {cell_addr}: {current} -> {updated}")
        except Exception as e:
            print(f"  Warning: Could not update {cell_addr}: {e}")


def _increment_range_end(formula):
    """
    Increment the end row number in range references within a formula.
    E.g. 'AVERAGE(E3:E35)' → 'AVERAGE(E3:E36)'
    """
    def replace_range(match):
        col1 = match.group(1)
        row1 = match.group(2)
        col2 = match.group(3)
        row2 = int(match.group(4))
        return f"{col1}{row1}:{col2}{row2 + 1}"

    # Match patterns like E3:E35, F3:F35, etc.
    return re.sub(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", replace_range, formula)


# -------------------------------------------------------
# Main
# -------------------------------------------------------
def main():
    # Validate configuration
    missing = []
    if not BEEHIIV_API_KEY:
        missing.append("BEEHIIV_API_KEY")
    if not PUBLICATION_ID:
        missing.append("BEEHIIV_PUBLICATION_ID")
    if not GOOGLE_SHEET_ID:
        missing.append("GOOGLE_SHEET_ID")
    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        missing.append(f"Google credentials file ({GOOGLE_CREDENTIALS_PATH})")

    if missing:
        print("Missing configuration:")
        for m in missing:
            print(f"  - {m}")
        print("\nPlease check your .env file and credentials setup.")
        sys.exit(1)

    # Get newsletter title from CLI arg or prompt
    if len(sys.argv) > 1:
        title_query = " ".join(sys.argv[1:])
    else:
        title_query = input("Enter the newsletter title (or part of it): ").strip()

    if not title_query:
        print("No title provided. Exiting.")
        sys.exit(1)

    # Search for the post
    print(f"\nSearching for: \"{title_query}\"...")
    post = find_post_by_title(title_query)

    if not post:
        print("Post not found. Try a different search term.")
        sys.exit(1)

    # Extract data
    title = post.get("subject_line") or post.get("title", "")
    author = extract_authors(post)
    date_str = extract_date(post)
    open_rate = extract_open_rate(post)
    stars = extract_star_clicks(post)

    # Show summary
    print(f"\nFound post:")
    print(f"  Title:    {title}")
    print(f"  Author:   {author or '(none)'}")
    print(f"  Date:     {date_str}")
    print(f"  Opens %:  {open_rate}")
    print(f"  5*: {stars[5]}  4*: {stars[4]}  3*: {stars[3]}  2*: {stars[2]}  1*: {stars[1]}")

    # Confirm before inserting
    confirm = input("\nInsert this data into Google Sheets? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        sys.exit(0)

    # Insert into Google Sheets
    insert_row_to_sheet(title, author, date_str, open_rate, stars)
    print("Done!")


if __name__ == "__main__":
    main()
