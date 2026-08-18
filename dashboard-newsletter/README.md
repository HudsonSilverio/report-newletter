# Newsletter Report Dashboard

Automated reporting tool for the **Clearer Thinking Newsletter** by **Spark Wave**.

**Live dashboard:** [report-newletter.streamlit.app](https://report-newletter.streamlit.app/)

---

## What does this project do?

Every week a newsletter goes out to thousands of readers. And every week the same question comes up: **how did this edition perform?**

This project automates the answer.

It starts when the operator opens a terminal and types the newsletter title. The script `beehiiv_to_sheets.py` goes to work. First, it hits the **Beehiiv API** and pulls the numbers: open rate and how many people clicked each star rating. Then it reaches the **Wix API** and collects the **comments** readers left on the feedback forms.

With everything in hand, it connects to **Google Sheets**, inserts a new row with the metrics, writes the formulas automatically, and distributes comments across the star-rating tabs. It then builds a **formatted HTML email** comparing the results against the historical average and saves it as a **draft in Gmail**, ready for review and sending.

On the other side there's the **dashboard**. Built with Streamlit and Plotly, it reads the same spreadsheet, cleans the data, and displays five interactive charts — open rate, average rating, positive ratings, negative ratings, and total ratings — each with an average line for comparison. Date and author filters let you explore the full history.

What used to be manual copy-and-paste is now **a single terminal command** that feeds the spreadsheet, generates the report, and updates the dashboard all at once.

---

## Project structure

```
dashboard-newsletter/
├── beehiiv_to_sheets.py    # Data pipeline (Beehiiv + Wix → Sheets + Email)
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

# Wix Forms (for collecting star-rating comments)
WIX_IST_TOKEN=your_wix_token_here
WIX_SITE_ID=your_wix_site_id_here

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

1. **Newsletter title** — Go to [app.beehiiv.com](https://app.beehiiv.com/), navigate to Posts, and copy the title (or part of it)
2. **Author(s)** — the name(s) listed as author on Beehiiv
3. **Post link** — the blog post URL on [clearerthinking.org](https://www.clearerthinking.org/) that corresponds to the newsletter
4. **Wix comments date range** — On [wix.com](https://www.wix.com/), go to Forms & Submissions and note the time window when comments were submitted (e.g. `Jun 25th, 2026 8:00 PM` to `Jul 2nd, 2026 8:00 PM`)

#### Run the script:

```bash
poetry run python beehiiv_to_sheets.py
```

The script will prompt you for each piece of information:

```
Enter the newsletter title (or part of it): AI and Decision Making
Author(s): Spencer Greenberg
Post link: https://www.clearerthinking.org/post/ai-and-decision-making
Observations (press Enter to skip):

Wix comments date range (Brasilia time).
From: Jun 25th, 2026 8:00 PM
To: Jul 2nd, 2026 8:00 PM

Found post:
  Title:    AI and Decision Making
  Author:   Spencer Greenberg
  Opens %:  0.452
  5*: 120  4*: 85  3*: 30  2*: 10  1*: 5

Insert this data into Google Sheets? (y/n): y
```

You can also pass the title directly from the command line:

```bash
poetry run python beehiiv_to_sheets.py "AI and Decision Making"
```

After confirming, the script will:
- Insert the data into Google Sheets
- Insert Wix comments into the star-rating tabs
- Save a formatted report email as a draft in Gmail

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

### Timezone

The script uses Brazil time (`America/Sao_Paulo`) for Wix comment dates. If you need to change it, edit this line in `beehiiv_to_sheets.py`:

```python
INPUT_TZ = ZoneInfo("America/Sao_Paulo")
```

Examples: `America/New_York`, `America/Los_Angeles`, `Europe/London`, `Europe/Berlin`.

---

## Common issues

- **`ModuleNotFoundError`** — Run `poetry install` to install dependencies
- **`FileNotFoundError: credentials.json`** — Make sure `credentials.json` is inside `dashboard-newsletter/`
- **Email draft not saving** — Check that `EMAIL_APP_PASSWORD` is correct and 2-Step Verification is enabled
- **Wrong dates for comments** — Confirm the timezone in `INPUT_TZ` matches your region
- **`UnicodeEncodeError` on Windows** — Set the environment variable `PYTHONIOENCODING=utf-8` before running

---

## Credits

Developed by **[Hudson Silverio](https://github.com/HudsonSilverio)** for **Spark Wave — [ClearerThinking.org](https://www.clearerthinking.org/)**
