# Newsletter Report Dashboard

Automated reporting tool for the **Clearer Thinking Newsletter** by **Spark Wave**.

**Live dashboard:** [report-newletter.streamlit.app](https://report-newletter.streamlit.app/)

---

## What does this project do?

Every week a newsletter goes out to thousands of readers. And every week the same question comes up: **how did this edition perform?**

This project automates the answer.

It starts when the operator opens a terminal and types the newsletter title. The script `beehiiv_to_sheets.py` goes to work. First, it downloads the ratings and feedback data from **GuidedTrack** — a survey platform where readers rate each newsletter on a five-point scale (Excellent, Good, Okay, Subpar, Bad) and optionally leave written feedback. The script filters the data for the requested newsletter, counts the votes for each rating level, and collects the comments.

Next, it hits the **Beehiiv API** to pull the open rate, publish date, and audience information.

With everything in hand, it connects to **Google Sheets**, inserts a new row with the metrics, writes the formulas automatically, and distributes comments across the star-rating tabs. It then builds a **formatted HTML email** comparing the results against the historical average and saves it as a **draft in Gmail**, ready for review and sending. Finally, it deletes the downloaded CSV to keep the project clean.

On the other side there's the **dashboard**. Built with Streamlit and Plotly, it reads the same spreadsheet, cleans the data, and displays five interactive charts — open rate, average rating, positive ratings, negative ratings, and total ratings — each with an average line for comparison. Date and author filters let you explore the full history.

What used to be manual copy-and-paste is now **a single terminal command** that feeds the spreadsheet, generates the report, and updates the dashboard all at once.

---

## Data sources

| Data | Source |
|------|--------|
| Open rate, publish date, audience | Beehiiv API |
| Star ratings (Excellent→5★, Good→4★, Okay→3★, Subpar→2★, Bad→1★) | GuidedTrack CSV |
| Reader feedback/comments | GuidedTrack CSV |
| Storage & dashboard data | Google Sheets |

---

## Project structure

```
dashboard-newsletter/
├── beehiiv_to_sheets.py    # Data pipeline (Beehiiv + GuidedTrack → Sheets + Email)
├── app.py                  # Visual dashboard (Streamlit + Plotly)
├── data_loader.py          # Reads and cleans data from the spreadsheet
├── main.py                 # Quick test / debug script
├── pyproject.toml          # Dependencies (managed with Poetry)
├── .env                    # API keys and secrets (NOT in Git)
├── credentials.json        # Google service account (NOT in Git)
└── tests/                  # Automated tests
```

---

## Prerequisites

Make sure you have these installed on your machine:

- **Python 3.13** — [python.org/downloads](https://www.python.org/downloads/)
- **Poetry** — [python-poetry.org/docs/#installation](https://python-poetry.org/docs/#installation)
- **Git** — [git-scm.com/downloads](https://git-scm.com/downloads)

To verify everything is installed:

```bash
python --version    # should show 3.13.x
poetry --version    # should show 2.x.x
git --version       # should show 2.x.x
```

---

## Setup (step by step)

### 1. Clone the repository

```bash
git clone https://github.com/HudsonSilverio/report-newletter.git
cd report-newletter/dashboard-newsletter
```

### 2. Install dependencies

```bash
poetry install
```

This creates a virtual environment and installs all required packages automatically.

### 3. Get the credentials file

You need a `credentials.json` file for Google Sheets access. Ask the project admin (Hudson) for this file and place it inside the `dashboard-newsletter/` folder.

### 4. Create your `.env` file

Inside the `dashboard-newsletter/` folder, create a file named `.env` with the following content. Replace the placeholder values with your actual keys:

```env
# Beehiiv API
BEEHIIV_API_KEY=your_beehiiv_api_key_here
BEEHIIV_PUBLICATION_ID=your_publication_id_here

# Google Sheets
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_SHEET_ID=your_google_sheet_id_here

# GuidedTrack (for ratings & feedback)
GT_EMAIL=your_guidedtrack_email
GT_PASSWORD=your_guidedtrack_password
GT_PROGRAM_ID=38551

# Email (for the automated report)
EMAIL_SENDER=your_email@gmail.com
EMAIL_APP_PASSWORD=your_gmail_app_password
EMAIL_RECIPIENT=recipient_email@gmail.com

# Links included in the report email
DASHBOARD_URL=https://report-newletter.streamlit.app/
SPREADSHEET_URL=https://docs.google.com/spreadsheets/d/your_sheet_id_here
```

> **Important:** Never commit `.env` or `credentials.json` to Git. They contain sensitive keys.

---

## How to run

### View the Dashboard

```bash
poetry run streamlit run app.py
```

Opens in your browser at `http://localhost:8501`. No extra configuration needed — it reads the public spreadsheet automatically.

### Run the Data Pipeline (insert data + generate report)

#### Before running, gather this information:

1. **Newsletter title** — the exact title of the newsletter (e.g. "What stands between you and reality?"). This is used to match entries in the GuidedTrack survey data and to find the post on Beehiiv.
2. **Author(s)** — the name(s) listed as author
3. **Post link** — the blog post URL on [clearerthinking.org](https://www.clearerthinking.org/)

#### Run the script:

```bash
poetry run python beehiiv_to_sheets.py
```

The script will prompt you for each piece of information:

```
Newsletter title: What stands between you and reality?
Author(s): Spencer Greenberg
Post link: https://www.clearerthinking.org/post/what-stands-between-you-and-reality
Observations (press Enter to skip):

Downloading GuidedTrack data (program 38551)...
  CSV downloaded.

Filtering CSV for: "What stands between you and reality?"...
  Found 51 matching rows.

Searching Beehiiv for: "What stands between you and reality?"...

Summary:
  Title:      What stands between you and reality?
  Author:     Spencer Greenberg
  Date:       Aug 27, 2026
  Audience:   All Subscribers
  Opens %:    29.14
  Ratings:    5*:22  4*:11  3*:2  2*:6  1*:10
  Comments:   10 total

Insert this data into Google Sheets? (y/n): y
```

You can also pass the title directly from the command line:

```bash
poetry run python beehiiv_to_sheets.py "What stands between you and reality?"
```

After confirming, the script will:
- Insert the data into Google Sheets (row + formulas)
- Insert reader feedback into the star-rating comment tabs
- Save a formatted report email as a draft in Gmail
- Delete the downloaded GuidedTrack CSV

---

## How it works (step by step)

1. **Downloads** the latest survey data CSV from GuidedTrack (program "CT Newsletter Ratings & Feedback")
2. **Filters** the CSV rows by matching the newsletter title against the article URL slug
3. **Counts** the `final_rating` values: Excellent→5★, Good→4★, Okay→3★, Subpar→2★, Bad→1★
4. **Collects** non-empty `feedback` entries grouped by rating level
5. **Fetches** the open rate, publish date, and audience from the Beehiiv API
6. **Inserts** a new row at position 3 in Google Sheets with all metrics and formulas
7. **Updates** the Means row (row 1) so averages include the new data
8. **Inserts** comments into the corresponding star-rating tabs (5★ through 1★ Comments)
9. **Generates** an HTML email report comparing results to historical averages
10. **Saves** the email as a draft in Gmail
11. **Deletes** the downloaded CSV file

---

## Settings you may need to change

### Email

To receive reports at your own email:

1. Open `.env` and update `EMAIL_SENDER`, `EMAIL_APP_PASSWORD`, and `EMAIL_RECIPIENT`
2. To generate a Gmail App Password:
   - Go to [myaccount.google.com/security](https://myaccount.google.com/security)
   - Enable **2-Step Verification**
   - Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   - Create a new app password and paste it into your `.env`

---

## Common issues

- **`ModuleNotFoundError`** — Run `poetry install` to install dependencies
- **`FileNotFoundError: credentials.json`** — Make sure `credentials.json` is inside `dashboard-newsletter/`
- **Email draft not saving** — Check that `EMAIL_APP_PASSWORD` is correct and 2-Step Verification is enabled
- **No matching rows in CSV** — Make sure the newsletter title matches the article URL slug on clearerthinking.org
- **GuidedTrack returns HTML instead of CSV** — Check `GT_EMAIL` and `GT_PASSWORD` in `.env`
- **`UnicodeEncodeError` on Windows** — Run with `python -X utf8` or set `PYTHONIOENCODING=utf-8`

---

## Credits

Developed by **[Hudson Silverio](https://github.com/HudsonSilverio)** for **Spark Wave — [ClearerThinking.org](https://www.clearerthinking.org/)**
