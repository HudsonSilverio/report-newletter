# Newsletter Report Dashboard

Automated reporting tool for the **Clearer Thinking Newsletter** by **Spark Wave**.

This project does two things:

1. **Dashboard** — A Streamlit web app that displays interactive charts with historical newsletter metrics (open rates, ratings, comments).
2. **Data Pipeline** — A script that pulls data from Beehiiv + Wix, inserts it into Google Sheets, and sends a formatted report email to the team.

**Live dashboard:** [https://report-newletter.streamlit.app/](https://report-newletter.streamlit.app/)

---

## Prerequisites

Before starting, make sure you have these installed on your machine:

| Tool | What it is | How to install |
|------|-----------|----------------|
| **Python 3.13** | The programming language | [python.org/downloads](https://www.python.org/downloads/) |
| **Poetry** | Manages project dependencies | [python-poetry.org/docs/#installation](https://python-poetry.org/docs/#installation) |
| **Git** | Version control | [git-scm.com/downloads](https://git-scm.com/downloads) |

To check if they are installed, open a terminal and run:

```bash
python --version    # should show 3.13.x
poetry --version    # should show 2.x.x
git --version       # should show 2.x.x
```

---

## Setup (Step by Step)

### 1. Clone the repository

```bash
git clone https://github.com/HudsonSilverio/report-newletter.git
cd report-newletter
```

### 2. Install dependencies

```bash
cd dashboard-newsletter
poetry install
```

This will create a virtual environment and install all required packages automatically.

### 3. Get the credentials file

You need a `credentials.json` file for Google Sheets access. Ask the project admin (Hudson) for this file and place it inside the `dashboard-newsletter/` folder.

### 4. Create your `.env` file

Inside the `dashboard-newsletter/` folder, create a file named `.env` with the following content. Replace the placeholder values with your own keys:

```env
# Beehiiv API
BEEHIIV_API_KEY=your_beehiiv_api_key_here
BEEHIIV_PUBLICATION_ID=your_publication_id_here

# Google Sheets
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_SHEET_ID=your_google_sheet_id_here

# Wix Forms (for collecting star-rating comments)
WIX_IST_TOKEN=your_wix_token_here
WIX_SITE_ID=your_wix_site_id_here

# Email (for automated report sending)
EMAIL_SENDER=your_email@gmail.com
EMAIL_APP_PASSWORD=your_gmail_app_password
EMAIL_RECIPIENT=your_email@gmail.com

# Links included in the report email
DASHBOARD_URL=https://report-newletter.streamlit.app/
SPREADSHEET_URL=https://docs.google.com/spreadsheets/d/your_sheet_id_here
```

> **Important:** Never commit the `.env` file or `credentials.json` to Git. They contain sensitive keys.

---

## Configuration You Must Change

If you are **not** the original developer, you **must** update these settings before running:

### Email

The email is currently configured to send reports to the developer's personal address. To receive reports at your own email:

1. Open `dashboard-newsletter/.env`
2. Change `EMAIL_SENDER` and `EMAIL_RECIPIENT` to your Gmail address
3. Generate a **Gmail App Password** for your account (see instructions below)
4. Update `EMAIL_APP_PASSWORD` with your new app password

**How to generate a Gmail App Password:**

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** if you haven't already
3. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
4. Enter a name (e.g. `newsletter-report`) and click **Create**
5. Copy the 16-character password and paste it into your `.env` file

### Timezone

The Wix comment date range is currently set to **Brazil time** (`America/Sao_Paulo`).

If you are in a different timezone, open `dashboard-newsletter/beehiiv_to_sheets.py` and change this line:

```python
INPUT_TZ = ZoneInfo("America/Sao_Paulo")
```

Replace `"America/Sao_Paulo"` with your timezone. Examples:

| Region | Timezone string |
|--------|----------------|
| US Eastern | `America/New_York` |
| US Pacific | `America/Los_Angeles` |
| UK | `Europe/London` |
| Central Europe | `Europe/Berlin` |
| Brazil | `America/Sao_Paulo` |

> **Tip:** Your timezone should match the one configured in your Beehiiv/Wix dashboard so that date ranges align correctly.

### API Keys

If you are working with a different Beehiiv publication or Wix site, update the corresponding keys in your `.env` file.

---

## How to Run

### Running the Dashboard (view charts)

```bash
cd dashboard-newsletter
poetry run streamlit run app.py
```

This opens the dashboard in your browser at `http://localhost:8501`.

### Running the Data Pipeline (insert data + send email)

Before running the script, you need to gather some information from Beehiiv and Wix. Follow the steps below.

#### Step 1 — Get the post info from Beehiiv

1. Go to [app.beehiiv.com](https://app.beehiiv.com/) and log in
2. Navigate to **Posts** in the sidebar
3. Find the newsletter you want to report on and click on it
4. From the post page, copy:
   - **Title** — the subject line of the newsletter (you only need part of it; the script will search for a match)
   - **Author(s)** — the name(s) listed as author

#### Step 2 — Get the post link from the website

1. Go to [clearerthinking.org](https://www.clearerthinking.org/)
2. Find the blog post that corresponds to the newsletter
3. Open the post and copy the full URL from your browser's address bar (e.g., `https://www.clearerthinking.org/post/ai-and-decision-making`)

> **Note:** This URL is the blog post link, not the Beehiiv email link. The script will automatically fetch the page title from this URL to use in the report email.

#### Step 3 — Get the date range for Wix comments

1. Go to [wix.com](https://www.wix.com/) and log in to the site dashboard
2. Navigate to **Forms & Submissions**
3. Check when the first and last comments were submitted for this newsletter
4. Note down the date range (in Brasilia time) — for example, `Jun 25th, 2026 8:00 PM` to `Jul 2nd, 2026 8:00 PM`

> **Tip:** Use a range that covers the full period the newsletter was live. This is typically from the day it was sent until the next newsletter goes out.

#### Step 4 — Run the script

```bash
cd dashboard-newsletter
poetry run python beehiiv_to_sheets.py
```

The script will prompt you for the information you gathered:

```
Enter the newsletter title (or part of it): AI and Decision Making
Author(s): Spencer Greenberg
Post link: https://www.clearerthinking.org/post/ai-and-decision-making

Wix comments date range (Brasilia time).
From: Jun 25th, 2026 8:00 PM
To: Jul 2nd, 2026 8:00 PM

Found post:
  Title:    AI and Decision Making
  Author:   Spencer Greenberg
  ...

Insert this data into Google Sheets? (y/n): y
```

After confirming, it will:
- Insert the data into Google Sheets
- Insert Wix comments into the comment tabs
- Save a report email draft with the post link title automatically fetched from the linked page (e.g., the actual blog post title, not the newsletter subject line)

You can also pass the title directly:

```bash
poetry run python beehiiv_to_sheets.py "AI and Decision Making"
```

---

## Running with Claude Code (Alternative)

If you have [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed, you can use it to run and interact with the project:

### 1. Install Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

### 2. Open the project

```bash
cd report-newletter
claude
```

### 3. Ask Claude to run the project

Inside the Claude Code session, you can simply type:

```
Run the data pipeline for the newsletter "AI and Decision Making"
```

Or:

```
Start the Streamlit dashboard
```

Claude Code will handle the commands for you and can help troubleshoot any errors.

---

## Project Structure

```
report-newletter/
├── dashboard-newsletter/
│   ├── app.py                  # Streamlit dashboard (main UI)
│   ├── data_loader.py          # Loads data from Google Sheets
│   ├── beehiiv_to_sheets.py    # Data pipeline + email report
│   ├── main.py                 # Quick data loading test
│   ├── pyproject.toml          # Project dependencies
│   ├── .env                    # API keys and config (not in Git)
│   └── credentials.json        # Google service account (not in Git)
└── README.md
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `poetry install` to install dependencies |
| `FileNotFoundError: credentials.json` | Make sure `credentials.json` is in the `dashboard-newsletter/` folder |
| Email not sending | Check your `EMAIL_APP_PASSWORD` is correct and 2-Step Verification is enabled |
| Wrong date range for comments | Check the `INPUT_TZ` timezone setting matches your region |
| `UnicodeEncodeError` on Windows | Set the environment variable `PYTHONIOENCODING=utf-8` before running |
| Post link title not matching the blog post | The title is fetched from the linked page's `<title>` tag; if the page is unreachable, the newsletter subject is used as fallback |

---

## Credits

Developed by **[Hudson Silverio](https://github.com/HudsonSilverio)** for **Spark Wave — [ClearerThinking.org](https://www.clearerthinking.org/)**
