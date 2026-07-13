"""
Beehiiv + Wix -> Google Sheets integration script.

Fetches newsletter data from the Beehiiv API, inserts a new row
into the Google Sheets spreadsheet used by the Streamlit dashboard,
and fetches Wix form comments (star ratings) into the Comments tabs.

Usage:
    python beehiiv_to_sheets.py "Newsletter Title Here"
    python beehiiv_to_sheets.py   # will prompt for the title
"""

import os
import re
import smtplib
import sys
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

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

# Wix configuration
WIX_IST_TOKEN = os.getenv("WIX_IST_TOKEN", "")
WIX_SITE_ID = os.getenv("WIX_SITE_ID", "")

WIX_FORM_IDS = {
    5: "f3a3156c-70ab-4fa1-b5d4-612af837bc92",
    4: "b1e62313-8fdd-400f-8f9e-63b290c34b1c",
    3: "dac92d59-eeee-479d-baaf-4ba5e1c8a6e6",
    2: "182b4778-30f2-4430-832a-651a04d53abf",
    1: "54b6519e-09f7-42ba-abc9-49d49b4d482e",
}

WIX_COMMENT_FIELD = "please_write_your_comments_below"

STAR_TAB_NAMES = {
    5: "5\u2605 Comments",
    4: "4\u2605 Comments",
    3: "3\u2605 Comments",
    2: "2\u2605 Comments",
    1: "1\u2605 Comments",
}

# Timezone for date input (matches Wix dashboard display)
INPUT_TZ = ZoneInfo("America/Sao_Paulo")

# Email configuration
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")
SPREADSHEET_URL = os.getenv(
    "SPREADSHEET_URL",
    f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}",
)

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
# Wix Form Submissions
# -------------------------------------------------------
def _parse_single_date(s):
    """
    Parse a single date string like 'Jun 25th, 2026 8:00 PM' to UTC ISO-8601.
    Input is assumed Eastern Time (EST/EDT handled automatically).
    """
    # Remove ordinal suffixes: 1st, 2nd, 3rd, 4th-31th
    s = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', s)
    for fmt in ("%b %d, %Y %I:%M %p", "%b %d, %Y %I %p", "%b %d, %Y"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            dt_eastern = dt.replace(tzinfo=INPUT_TZ)
            dt_utc = dt_eastern.astimezone(timezone.utc)
            return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except ValueError:
            continue
    raise ValueError(f"Could not parse date: '{s}'")


def parse_date_range_split(from_str, to_str):
    """
    Parse two separate date strings (From / To).
    Returns (from_utc, to_utc) as ISO-8601 strings in UTC.
    """
    return _parse_single_date(from_str), _parse_single_date(to_str)


def fetch_wix_comments(form_id, date_from_utc, date_to_utc):
    """
    Fetch all non-empty comments from a Wix form within a date range.
    Uses cursor-based pagination. Returns list of comment strings.
    """
    headers = {
        "Authorization": WIX_IST_TOKEN,
        "wix-site-id": WIX_SITE_ID,
        "Content-Type": "application/json",
    }

    comments = []
    cursor = None

    while True:
        paging = {"limit": 100}
        if cursor:
            paging["cursor"] = cursor

        query_filter = {
            "$and": [
                {"namespace": "wix.form_app.form"},
                {"formId": form_id},
                {"createdDate": {"$gte": date_from_utc}},
                {"createdDate": {"$lte": date_to_utc}},
            ]
        }

        body = {
            "query": {
                "filter": query_filter,
                "sort": [{"fieldName": "createdDate", "order": "DESC"}],
                "cursorPaging": paging,
            },
            "onlyYourOwn": False,
        }

        resp = requests.post(
            "https://www.wixapis.com/form-submission-service/v4/submissions/namespace/query",
            headers=headers,
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for sub in data.get("submissions", []):
            fields = sub.get("submissions", {})
            comment = (fields.get(WIX_COMMENT_FIELD) or "").strip()
            if comment:
                # Replace line breaks with space to keep full text in one cell
                comment = comment.replace("\r\n", " ").replace("\n", " ")
                comments.append(comment)

        # Check pagination
        metadata = data.get("pagingMetadata", data.get("metadata", {}))
        if metadata.get("hasNext"):
            cursors = metadata.get("cursors", {})
            cursor = cursors.get("next")
            if not cursor:
                break
        else:
            break

    return comments


def insert_comments_to_sheets(spreadsheet, title, star_comments):
    """
    Insert comments into each star Comments tab.
    For each star rating, inserts a new column B with:
      B1 = newsletter title
      B2 = count of comments
      B3+ = individual comments
    """
    for star_rating in [5, 4, 3, 2, 1]:
        tab_name = STAR_TAB_NAMES[star_rating]
        comments = star_comments.get(star_rating, [])

        try:
            ws = spreadsheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            print(f"  Tab '{tab_name}' not found, skipping.")
            continue

        # Build column data: [title, count, comment1, comment2, ...]
        col_data = [title, str(len(comments))] + comments

        # Insert as column B (index 2), pushing existing columns right
        ws.insert_cols([col_data], col=2)

        print(f"  {star_rating}* Comments: {len(comments)} comments inserted into '{tab_name}'")


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
    Update ALL formulas in row 1 (Means row) to include
    the newly inserted row 3.

    After insert_row(index=3), Google Sheets auto-adjusts references:
      =AVERAGE(E3:E39) becomes =AVERAGE(E4:E40)
    We need to reset the start back to row 3 so the new row is included:
      =AVERAGE(E4:E40) becomes =AVERAGE(E3:E40)

    Scans every cell in row 1 to catch all formula columns.
    """
    # Read entire row 1 as formulas
    row1 = sheet.get("1:1", value_render_option="FORMULA")
    if not row1 or not row1[0]:
        return

    for col_idx, value in enumerate(row1[0]):
        if not value or not isinstance(value, str) or not value.startswith("="):
            continue

        cell_addr = gspread.utils.rowcol_to_a1(1, col_idx + 1)
        updated = _fix_range_start(value, start_row=3)
        if updated != value:
            try:
                sheet.update_acell(cell_addr, updated)
                print(f"  Updated {cell_addr}: {value} -> {updated}")
            except Exception as e:
                print(f"  Warning: Could not update {cell_addr}: {e}")


def _fix_range_start(formula, start_row=3):
    """
    Reset the start row of range references to include the newly inserted row.
    The end row is left as-is (Google Sheets already adjusted it).
    E.g. 'AVERAGE(E4:E40)' -> 'AVERAGE(E3:E40)'
    """
    def replace_range(match):
        col1 = match.group(1)
        col2 = match.group(3)
        row2 = match.group(4)
        return f"{col1}{start_row}:{col2}{row2}"

    return re.sub(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", replace_range, formula)


# -------------------------------------------------------
# Email Report
# -------------------------------------------------------
def compute_newsletter_metrics(open_rate, stars):
    """Compute derived metrics from raw Beehiiv data."""
    total = sum(stars.values())
    # open_rate from Beehiiv is a decimal (0.452 = 45.2%)
    open_pct = open_rate * 100 if open_rate <= 1 else open_rate
    avg_rating = (
        round(
            (5 * stars[5] + 4 * stars[4] + 3 * stars[3] + 2 * stars[2] + 1 * stars[1])
            / total,
            1,
        )
        if total
        else 0
    )
    pct_positive = round((stars[5] + stars[4]) / total * 100) if total else 0
    pct_negative = round(stars[1] / total * 100) if total else 0
    return {
        "open_pct": round(open_pct, 1),
        "avg_rating": avg_rating,
        "pct_positive": pct_positive,
        "pct_negative": pct_negative,
        "total_ratings": total,
    }


def read_means_from_sheet(sheet):
    """Read averages from row 1 (Means row) of the spreadsheet."""
    row1 = sheet.row_values(1)

    def _parse(val):
        if not val:
            return 0.0
        val = str(val).replace(",", "").replace("%", "").strip()
        try:
            return float(val)
        except ValueError:
            return 0.0

    return {
        "avg_open_rate": _parse(row1[4]) if len(row1) > 4 else 0.0,
        "avg_rating": _parse(row1[5]) if len(row1) > 5 else 0.0,
        "avg_pct_positive": _parse(row1[6]) if len(row1) > 6 else 0.0,
        "avg_pct_negative": _parse(row1[7]) if len(row1) > 7 else 0.0,
    }


def _diff_color(diff):
    """Return inline CSS color: green for positive, red for negative, gray for zero."""
    if diff == 0:
        return "color:#888;"
    if diff > 0:
        return "color:#28a745;font-weight:bold;"
    return "color:#dc3545;font-weight:bold;"


def _fmt_diff(diff, suffix="", plus=True):
    """Format a numeric difference with optional sign and suffix."""
    sign = "+" if diff > 0 and plus else ""
    if suffix == "%":
        return f"{sign}{diff:.0f}%"
    return f"{sign}{diff:.1f}{suffix}"


def build_report_html(title, author, date_str, metrics, means, star_comments, post_url):
    """Build the HTML email body matching the newsletter report template."""

    # Compute differences
    diff_opens = metrics["open_pct"] - means["avg_open_rate"]
    diff_rating = metrics["avg_rating"] - means["avg_rating"]
    diff_positive = metrics["pct_positive"] - means["avg_pct_positive"]
    diff_negative = metrics["pct_negative"] - means["avg_pct_negative"]

    # Build metrics table rows
    metrics_rows = f"""
    <tr>
      <td style="padding:10px 12px;border-bottom:1px solid #eee;">Opens</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;">{metrics['open_pct']:.1f}%</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;">{means['avg_open_rate']:.1f}%</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;{_diff_color(diff_opens)}">{_fmt_diff(diff_opens, '%')}</td>
    </tr>
    <tr>
      <td style="padding:10px 12px;border-bottom:1px solid #eee;">Average Rating</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;">{metrics['avg_rating']:.1f}</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;">{means['avg_rating']:.1f}</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;{_diff_color(diff_rating)}">{_fmt_diff(diff_rating)}</td>
    </tr>
    <tr>
      <td style="padding:10px 12px;border-bottom:1px solid #eee;">4s and 5s</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;">{metrics['pct_positive']}%</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;">{means['avg_pct_positive']:.0f}%</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;{_diff_color(diff_positive)}">{_fmt_diff(diff_positive, '%')}</td>
    </tr>
    <tr>
      <td style="padding:10px 12px;border-bottom:1px solid #eee;">1s</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;">{metrics['pct_negative']}%</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;">{means['avg_pct_negative']:.0f}%</td>
      <td style="text-align:center;padding:10px;border-bottom:1px solid #eee;{_diff_color(diff_negative)}">{_fmt_diff(diff_negative, '%')}</td>
    </tr>
    <tr>
      <td style="padding:10px 12px;">Total Ratings</td>
      <td style="text-align:center;padding:10px;">{metrics['total_ratings']}</td>
      <td style="text-align:center;padding:10px;">—</td>
      <td style="text-align:center;padding:10px;">—</td>
    </tr>
    """

    # Build comments section
    comment_labels = {
        5: "Excellent",
        4: "Good",
        3: "Okay",
        2: "Subpar",
        1: "Bad",
    }
    comments_html = ""
    for star in [5, 4, 3, 2, 1]:
        label = comment_labels[star]
        items = star_comments.get(star, [])
        comments_html += f'<p style="margin:16px 0 4px;"><strong>{label}:</strong></p>\n'
        if items:
            comments_html += "<ul style=\"margin:4px 0;padding-left:24px;\">\n"
            for c in items:
                comments_html += f"  <li style=\"margin-bottom:4px;\">{c}</li>\n"
            comments_html += "</ul>\n"
        else:
            comments_html += '<p style="color:#999;margin:4px 0 0 24px;">( None )</p>\n'

    # Post link
    post_link = f'<a href="{post_url}" style="color:#1a73e8;text-decoration:none;">{title}</a>' if post_url else title

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,Helvetica,sans-serif;color:#333;margin:0;padding:20px;background-color:#f5f5f5;">
<div style="max-width:700px;margin:0 auto;">

  <p style="font-size:15px;">Hi, team!</p>
  <p style="font-size:15px;">Here are the numbers regarding the past newsletter.</p>

  <p style="font-size:15px;">
    <a href="{DASHBOARD_URL}" style="color:#1a73e8;text-decoration:none;">Report Newsletter</a>
    &nbsp;&nbsp;|&nbsp;&nbsp;
    <a href="{SPREADSHEET_URL}" style="color:#1a73e8;text-decoration:none;">CT Newsletter Performance</a>
  </p>

  <p style="font-size:15px;">Post link: {post_link}</p>

  <!-- Performance Card -->
  <div style="background:#ffffff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.12);overflow:hidden;margin:24px 0;">

    <!-- Card Header -->
    <div style="background:#1a1a2e;padding:18px 24px;">
      <h2 style="margin:0;color:#ffffff;font-size:18px;font-weight:600;">Newsletter Performance Report</h2>
    </div>

    <!-- Card Body -->
    <div style="padding:24px;">
      <h3 style="margin:0 0 8px;font-size:20px;color:#222;">{title}</h3>
      <p style="color:#666;font-size:14px;margin:0 0 16px;">
        <strong>Author:</strong> {author}
        &nbsp;&nbsp;|&nbsp;&nbsp;
        <strong>Sent on:</strong> {date_str}
        &nbsp;&nbsp;|&nbsp;&nbsp;
        <strong>Audience:</strong> All Subscribers
      </p>

      <hr style="border:none;border-top:1px solid #eee;margin:16px 0;">

      <h4 style="margin:0 0 12px;color:#555;font-size:15px;">Key Metrics</h4>

      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#f8f9fa;">
            <th style="text-align:left;padding:10px 12px;border-bottom:2px solid #dee2e6;color:#555;">Metric</th>
            <th style="text-align:center;padding:10px;border-bottom:2px solid #dee2e6;color:#555;">Result</th>
            <th style="text-align:center;padding:10px;border-bottom:2px solid #dee2e6;color:#555;">Avg across all newsletters</th>
            <th style="text-align:center;padding:10px;border-bottom:2px solid #dee2e6;color:#555;">Difference</th>
          </tr>
        </thead>
        <tbody>
          {metrics_rows}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Comments Section -->
  <p style="font-size:15px;"><strong>Below are the qualitative feedback we've received for this one:</strong></p>
  {comments_html}

  <br>
  <p style="font-size:15px;">Best,<br>Hudson</p>

</div>
</body>
</html>"""
    return html


def send_report_email(title, html_body):
    """Send the HTML report email via Gmail SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Newsletter Reporting: {title}"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECIPIENT
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"\nReport email sent to {EMAIL_RECIPIENT}")


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

    # Ask for author and post link (user input)
    author = input("Author(s): ").strip()
    post_url_input = input("Post link: ").strip()

    # Get date range for Wix comments
    has_wix = bool(WIX_IST_TOKEN and WIX_SITE_ID)
    date_from_utc = None
    date_to_utc = None

    if has_wix:
        print("\nWix comments date range (Brasilia time).")
        date_from_input = input("From: ").strip()
        if date_from_input:
            date_to_input = input("To: ").strip()
            if date_to_input:
                try:
                    date_from_utc, date_to_utc = parse_date_range_split(
                        date_from_input, date_to_input
                    )
                    print(f"  From (UTC): {date_from_utc}")
                    print(f"  To   (UTC): {date_to_utc}")
                except ValueError as e:
                    print(f"  Error parsing dates: {e}")
                    print("  Skipping Wix comments.")
                    has_wix = False
            else:
                print("  No end date provided. Skipping Wix comments.")
                has_wix = False
        else:
            print("  No date provided. Skipping Wix comments.")
            has_wix = False
    else:
        if not WIX_IST_TOKEN:
            print("\nNote: WIX_IST_TOKEN not set in .env - Wix comments will be skipped.")

    # Search for the post
    print(f"\nSearching for: \"{title_query}\"...")
    post = find_post_by_title(title_query)

    if not post:
        print("Post not found. Try a different search term.")
        sys.exit(1)

    # Extract data
    title = post.get("subject_line") or post.get("title", "")
    date_str = extract_date(post)
    open_rate = extract_open_rate(post)
    stars = extract_star_clicks(post)

    # Fetch Wix comments if configured
    star_comments = {}
    if has_wix:
        print("\nFetching Wix form comments...")
        for star_rating in [5, 4, 3, 2, 1]:
            form_id = WIX_FORM_IDS[star_rating]
            try:
                comments = fetch_wix_comments(form_id, date_from_utc, date_to_utc)
                star_comments[star_rating] = comments
                print(f"  {star_rating}*: {len(comments)} comments found")
            except Exception as e:
                print(f"  {star_rating}*: Error - {e}")
                star_comments[star_rating] = []

    # Show summary
    print(f"\nFound post:")
    print(f"  Title:    {title}")
    print(f"  Author:   {author or '(none)'}")
    print(f"  Date:     {date_str}")
    print(f"  Opens %:  {open_rate}")
    print(f"  5*: {stars[5]}  4*: {stars[4]}  3*: {stars[3]}  2*: {stars[2]}  1*: {stars[1]}")

    if star_comments:
        total_comments = sum(len(c) for c in star_comments.values())
        print(f"\n  Wix comments to insert: {total_comments} total")
        for s in [5, 4, 3, 2, 1]:
            count = len(star_comments.get(s, []))
            if count:
                print(f"    {s}*: {count} comments")

    # Confirm before inserting
    confirm = input("\nInsert this data into Google Sheets? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        sys.exit(0)

    # Insert Beehiiv data into main sheet
    insert_row_to_sheet(title, author, date_str, open_rate, stars)

    # Shared client for subsequent sheet operations
    client = get_sheets_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

    # Insert Wix comments into Comments tabs
    if star_comments:
        print("\nInserting comments into Google Sheets...")
        insert_comments_to_sheets(spreadsheet, title, star_comments)

    # Send report email
    if EMAIL_SENDER and EMAIL_APP_PASSWORD and EMAIL_RECIPIENT:
        print("\nPreparing report email...")
        metrics = compute_newsletter_metrics(open_rate, stars)
        means = read_means_from_sheet(spreadsheet.sheet1)
        html = build_report_html(
            title, author, date_str, metrics, means, star_comments, post_url_input
        )
        try:
            send_report_email(title, html)
        except Exception as e:
            print(f"\nWarning: Could not send email: {e}")
    else:
        print("\nNote: Email not configured. Set EMAIL_SENDER, EMAIL_APP_PASSWORD, EMAIL_RECIPIENT in .env")

    print("\nDone!")


if __name__ == "__main__":
    main()
