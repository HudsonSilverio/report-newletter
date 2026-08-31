"""
Beehiiv + GuidedTrack -> Google Sheets integration script.

Fetches the open rate from the Beehiiv API, downloads ratings and feedback
from GuidedTrack, inserts a new row into the Google Sheets spreadsheet
used by the Streamlit dashboard, and saves an email report as a Gmail draft.

Usage:
    python beehiiv_to_sheets.py "Newsletter Title Here"
    python beehiiv_to_sheets.py   # will prompt for the title
"""

import csv
import html as html_module
import imaplib
import io
import os
import re
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlparse

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

# GuidedTrack configuration
GT_EMAIL = os.getenv("GT_EMAIL", "")
GT_PASSWORD = os.getenv("GT_PASSWORD", "")
GT_PROGRAM_ID = os.getenv("GT_PROGRAM_ID", "38551")
GT_CSV_PATH = os.path.join(os.path.expanduser("~"), "guidedtrack", "ct_newsletter_data.csv")

# Rating mapping: GuidedTrack final_rating text -> star number
RATING_MAP = {
    "Excellent": 5,
    "Good": 4,
    "Okay": 3,
    "Subpar": 2,
    "Bad": 1,
}

STAR_TAB_NAMES = {
    5: "5\u2605 Comments",
    4: "4\u2605 Comments",
    3: "3\u2605 Comments",
    2: "2\u2605 Comments",
    1: "1\u2605 Comments",
}

# Email configuration
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")
SPREADSHEET_URL = os.getenv(
    "SPREADSHEET_URL",
    f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}",
)


# -------------------------------------------------------
# GuidedTrack CSV
# -------------------------------------------------------
def download_guidedtrack_csv():
    """
    Download the data CSV from GuidedTrack for the configured program.
    Returns the local file path.
    """
    url = f"https://www.guidedtrack.com/programs/{GT_PROGRAM_ID}/exports?export_format=csv"
    resp = requests.get(url, auth=(GT_EMAIL, GT_PASSWORD), timeout=60)
    resp.raise_for_status()

    # Verify we got CSV, not an HTML login page
    if resp.text.strip().startswith("<!DOCTYPE") or resp.text.strip().startswith("<html"):
        raise RuntimeError("GuidedTrack returned HTML instead of CSV. Check GT_EMAIL/GT_PASSWORD in .env")

    os.makedirs(os.path.dirname(GT_CSV_PATH), exist_ok=True)
    with open(GT_CSV_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(resp.text)

    return GT_CSV_PATH


def _title_to_slug(title):
    """Convert a newsletter title to a URL-style slug for matching."""
    slug = title.lower().strip()
    # Replace apostrophes with nothing (don't -> dont, like URL slugs)
    slug = re.sub(r"['']", "", slug)
    # Remove all non-word chars except spaces and hyphens
    slug = re.sub(r"[^\w\s-]", "", slug)
    # Collapse whitespace to single hyphens
    slug = re.sub(r"\s+", "-", slug)
    return slug


def parse_guidedtrack_csv(csv_path, newsletter_title):
    """
    Read the GuidedTrack CSV and filter rows matching the newsletter title.
    Matches by converting the title to a slug and checking if it appears
    in the article URL path.

    Returns a list of dicts (one per matching row).
    """
    slug = _title_to_slug(newsletter_title)

    matching_rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            article_url = row.get("article", "")
            if not article_url:
                continue
            # Extract the path portion of the URL and check for slug match
            try:
                path = urlparse(article_url).path.lower()
            except Exception:
                path = article_url.lower()
            if slug in path:
                matching_rows.append(row)

    return matching_rows


def extract_ratings_from_csv(rows):
    """
    Count final_rating values from filtered CSV rows.
    Returns dict {5: count, 4: count, 3: count, 2: count, 1: count}.
    """
    stars = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    for row in rows:
        rating_text = (row.get("final_rating") or "").strip()
        star = RATING_MAP.get(rating_text)
        if star is not None:
            stars[star] += 1
    return stars


def extract_comments_from_csv(rows):
    """
    Extract non-empty feedback grouped by star rating.
    Returns dict {5: [comments], 4: [comments], ...}.
    """
    comments = {5: [], 4: [], 3: [], 2: [], 1: []}
    for row in rows:
        rating_text = (row.get("final_rating") or "").strip()
        star = RATING_MAP.get(rating_text)
        if star is None:
            continue

        # Check both feedback columns
        feedback = (row.get("feedback") or "").strip()
        if not feedback:
            feedback = (row.get("(Optional) What feedback would you like to give about this article? (7f2fv5r)") or "").strip()

        if feedback:
            # Clean up: replace line breaks with space
            feedback = feedback.replace("\r\n", " ").replace("\n", " ")
            comments[star].append(feedback)

    return comments


def cleanup_guidedtrack_csv(csv_path):
    """Delete the downloaded GuidedTrack CSV file."""
    try:
        if os.path.exists(csv_path):
            os.remove(csv_path)
            print(f"\nCleaned up: {csv_path}")
    except OSError as e:
        print(f"\nWarning: Could not delete CSV: {e}")


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
    When multiple posts match, returns the one with the highest recipients
    to avoid picking test campaigns or duplicates.
    """
    page = 1
    candidates = []
    query_lower = title_query.lower()

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

        for post in posts:
            subject = (post.get("subject_line") or "").lower()
            title = (post.get("title") or "").lower()
            if query_lower in subject or query_lower in title:
                candidates.append(post)

        total_pages = data.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1

    if not candidates:
        return None

    best = max(
        candidates,
        key=lambda p: (p.get("stats") or {}).get("email", {}).get("recipients", 0),
    )

    if len(candidates) > 1:
        print(f"\n  {len(candidates)} posts matched. Selected the one with most recipients:")
        for c in candidates:
            recip = (c.get("stats") or {}).get("email", {}).get("recipients", 0)
            marker = " <-- selected" if c is best else ""
            print(f"    {recip:>8} recipients - {c.get('title', '')}{marker}")

    return best


def extract_open_rate(post):
    """Extract open rate percentage from post stats."""
    stats = post.get("stats", {})
    email = stats.get("email", {})
    return email.get("open_rate", 0)


def extract_date(post):
    """Extract publish date formatted as 'Mon DD, YYYY'."""
    publish_ts = post.get("publish_date") or post.get("displayed_date") or post.get("created")
    if publish_ts:
        dt = datetime.fromtimestamp(publish_ts, tz=timezone.utc)
        return dt.strftime("%b %d, %Y")
    return ""


def extract_audience(post):
    """
    Check the post's send_targets to determine the audience.
    If sent to 'CT Audience - Engaged Subs' segment or to the whole publication,
    returns 'All Subscribers'. Otherwise prints a warning and returns the segment name.
    """
    send_targets = post.get("send_targets", [])

    for target in send_targets:
        receiver_type = target.get("receiver_type", "")

        if receiver_type == "Publication":
            return "All Subscribers"

        if receiver_type == "Segment":
            segment_id = target.get("receiver_id", "")
            # Look up the segment name
            try:
                segments_data = beehiiv_get(f"/publications/{PUBLICATION_ID}/segments")
                segments = segments_data.get("data", [])
                for seg in segments:
                    if seg.get("id") == segment_id:
                        seg_name = seg.get("name", "")
                        if "engaged subs" in seg_name.lower() or "ct audience" in seg_name.lower():
                            return "All Subscribers"
                        print(f"\n  WARNING: Newsletter sent to segment '{seg_name}', not 'CT Audience - Engaged Subs'.")
                        return seg_name
            except Exception as e:
                print(f"\n  WARNING: Could not verify audience segment: {e}")
                return "Unknown"

    # Fallback: if audience field is "free" (whole publication)
    if post.get("audience") == "free":
        return "All Subscribers"

    print(f"\n  WARNING: Could not determine audience. send_targets: {send_targets}")
    return "Unknown"


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


def insert_row_to_sheet(title, author, date_str, audience, open_rate, stars):
    """
    Insert a new data row at position 3 (below header) in the Google Sheet.
    Also inserts formulas and updates the Means row AVERAGE ranges.
    """
    client = get_sheets_client()
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1

    row = [
        title,                          # A - Title
        author,                         # B - Author(s)
        date_str,                       # C - Date
        audience,                       # D - Audience
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

    sheet.insert_row(row, index=3)

    formulas = {
        "F3": "=ROUND(5*(I3/N3)+4*(J3/N3)+3*(K3/N3)+2*(L3/N3)+1*(M3/N3),1)",
        "G3": "=SUM(I3:J3)/N3",
        "H3": "=M3/N3",
        "N3": "=SUM(I3:M3)",
    }
    for cell, formula in formulas.items():
        sheet.update_acell(cell, formula)

    sheet.format("G3", {"numberFormat": {"type": "PERCENT", "pattern": "0%"}})
    sheet.format("H3", {"numberFormat": {"type": "PERCENT", "pattern": "0%"}})

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
    """
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
    E.g. 'AVERAGE(E4:E40)' -> 'AVERAGE(E3:E40)'
    """
    def replace_range(match):
        col1 = match.group(1)
        col2 = match.group(3)
        row2 = match.group(4)
        return f"{col1}{start_row}:{col2}{row2}"

    return re.sub(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", replace_range, formula)


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
            print(f"  Tab '{star_rating}* Comments' not found, skipping.")
            continue

        col_data = [title, str(len(comments))] + comments
        ws.insert_cols([col_data], col=2)

        print(f"  {star_rating}* Comments: {len(comments)} comments inserted")


# -------------------------------------------------------
# Email Report
# -------------------------------------------------------
def compute_newsletter_metrics(open_rate, stars):
    """Compute derived metrics from raw data."""
    total = sum(stars.values())
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


def fetch_post_title(url):
    """Fetch the <title> of a web page from its URL."""
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
        if match:
            raw = match.group(1).strip()
            raw = re.split(r"\s*[|\u2013\u2014]\s*", raw)[0].strip()
            return html_module.unescape(raw)
    except Exception as e:
        print(f"  Warning: Could not fetch title from URL: {e}")
    return None


def build_report_html(title, author, date_str, audience, metrics, means, star_comments, post_url, observations=""):
    """Build the HTML email body matching the newsletter report template."""

    diff_opens = metrics["open_pct"] - means["avg_open_rate"]
    diff_rating = metrics["avg_rating"] - means["avg_rating"]
    diff_positive = metrics["pct_positive"] - means["avg_pct_positive"]
    diff_negative = metrics["pct_negative"] - means["avg_pct_negative"]

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
      <td style="text-align:center;padding:10px;">\u2014</td>
      <td style="text-align:center;padding:10px;">\u2014</td>
    </tr>
    """

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
                comments_html += f"  <li style=\"margin-bottom:4px;\">{html_module.escape(c)}</li>\n"
            comments_html += "</ul>\n"
        else:
            comments_html += '<p style="color:#999;margin:4px 0 0 24px;">( None )</p>\n'

    if post_url:
        page_title = fetch_post_title(post_url) or title
        post_link = f'<a href="{post_url}" style="color:#1a73e8;text-decoration:none;">{page_title}</a>'
    else:
        post_link = title

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
        <strong>Audience:</strong> {audience}
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

  {"" if not observations else f'''<!-- Observations -->
  <div style="background:#fff8e1;border-left:4px solid #ffc107;padding:12px 16px;margin:24px 0;border-radius:4px;">
    <p style="margin:0 0 4px;font-size:15px;"><strong>Observations:</strong></p>
    <p style="margin:0;font-size:14px;">{html_module.escape(observations)}</p>
  </div>'''}

  <!-- Comments Section -->
  <p style="font-size:15px;"><strong>Below are the qualitative feedback we've received for this one:</strong></p>
  {comments_html}

  <br>
  <p style="font-size:15px;">Best,<br>Hudson</p>

</div>
</body>
</html>"""
    return html


def save_report_as_draft(title, html_body):
    """Save the HTML report email as a draft in Gmail for review before sending."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Newsletter Reporting: {title}"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECIPIENT
    msg.attach(MIMEText(html_body, "html"))

    with imaplib.IMAP4_SSL("imap.gmail.com", 993) as imap:
        imap.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
        imap.append(
            "[Gmail]/Drafts",
            "",
            imaplib.Time2Internaldate(datetime.now(tz=timezone.utc)),
            msg.as_bytes(),
        )

    print(f"\nReport email saved as draft in {EMAIL_SENDER}")


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
    if not GT_EMAIL or not GT_PASSWORD:
        missing.append("GT_EMAIL / GT_PASSWORD")

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
        title_query = input("Newsletter title: ").strip()

    if not title_query:
        print("No title provided. Exiting.")
        sys.exit(1)

    # User inputs
    author = input("Author(s): ").strip()
    post_url_input = input("Post link: ").strip()
    observations = input("Observations (press Enter to skip): ").strip()

    # Step 1: Download GuidedTrack CSV
    print(f"\nDownloading GuidedTrack data (program {GT_PROGRAM_ID})...")
    try:
        csv_path = download_guidedtrack_csv()
        print(f"  CSV downloaded: {csv_path}")
    except Exception as e:
        print(f"Error downloading GuidedTrack CSV: {e}")
        sys.exit(1)

    # Step 2: Parse CSV and filter by newsletter title
    print(f"\nFiltering CSV for: \"{title_query}\"...")
    matching_rows = parse_guidedtrack_csv(csv_path, title_query)
    if not matching_rows:
        print(f"  No rows found matching '{title_query}' in the GuidedTrack CSV.")
        print(f"  Slug searched: '{_title_to_slug(title_query)}'")
        cleanup_guidedtrack_csv(csv_path)
        sys.exit(1)
    print(f"  Found {len(matching_rows)} matching rows.")

    # Step 3: Extract ratings and comments from CSV
    stars = extract_ratings_from_csv(matching_rows)
    star_comments = extract_comments_from_csv(matching_rows)

    # Step 4: Search Beehiiv for open rate, date, and audience
    print(f"\nSearching Beehiiv for: \"{title_query}\"...")
    post = find_post_by_title(title_query)

    if not post:
        print("Post not found on Beehiiv. Try a different search term.")
        cleanup_guidedtrack_csv(csv_path)
        sys.exit(1)

    title = post.get("subject_line") or post.get("title", "")
    date_str = extract_date(post)
    open_rate = extract_open_rate(post)
    audience = extract_audience(post)

    # Show summary
    print(f"\nSummary:")
    print(f"  Title:      {title}")
    print(f"  Author:     {author or '(none)'}")
    print(f"  Date:       {date_str}")
    print(f"  Audience:   {audience}")
    print(f"  Opens %:    {open_rate}")
    print(f"  Ratings:    5*:{stars[5]}  4*:{stars[4]}  3*:{stars[3]}  2*:{stars[2]}  1*:{stars[1]}")
    total_comments = sum(len(c) for c in star_comments.values())
    print(f"  Comments:   {total_comments} total")
    for s in [5, 4, 3, 2, 1]:
        count = len(star_comments.get(s, []))
        if count:
            print(f"    {s}*: {count} comments")

    # Confirm before inserting
    confirm = input("\nInsert this data into Google Sheets? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        cleanup_guidedtrack_csv(csv_path)
        sys.exit(0)

    # Insert data into Google Sheets
    insert_row_to_sheet(title, author, date_str, audience, open_rate, stars)

    # Shared client for subsequent sheet operations
    client = get_sheets_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

    # Insert comments into Comments tabs
    if any(star_comments.values()):
        print("\nInserting comments into Google Sheets...")
        insert_comments_to_sheets(spreadsheet, title, star_comments)

    # Generate and save email report
    if EMAIL_SENDER and EMAIL_APP_PASSWORD and EMAIL_RECIPIENT:
        print("\nPreparing report email...")
        metrics = compute_newsletter_metrics(open_rate, stars)
        means = read_means_from_sheet(spreadsheet.sheet1)
        html = build_report_html(
            title, author, date_str, audience, metrics, means, star_comments, post_url_input, observations
        )
        try:
            save_report_as_draft(title, html)
        except Exception as e:
            print(f"\nWarning: Could not save email draft: {e}")
    else:
        print("\nNote: Email not configured. Set EMAIL_SENDER, EMAIL_APP_PASSWORD, EMAIL_RECIPIENT in .env")

    # Cleanup: delete the downloaded CSV
    cleanup_guidedtrack_csv(csv_path)

    print("\nDone!")


if __name__ == "__main__":
    main()
