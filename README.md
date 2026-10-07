# xHR — AI Job Application Agent

An AI-powered job application agent that automatically finds, evaluates, and applies to jobs on LinkedIn, Indeed, and Dice — while you focus on interview prep.

![Dashboard](https://img.shields.io/badge/UI-Web%20Dashboard-blue) ![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![License](https://img.shields.io/badge/License-MIT-green)

---

## Features

- **Works in any country** — pick where you're job hunting; each job's country is detected from its location, and work-permit checks follow that country's rules
- **Sponsorship intelligence** — every job gets a verdict (*Sponsors / May sponsor / Won't sponsor / No record*) from the job country's public employer data plus the job post's own wording:
  - 🇺🇸 United States: DOL H-1B filings (filings for the exact role, median pay, prevailing wage)
  - 🇬🇧 United Kingdom: Home Office Register of Licensed Sponsors
  - Every other country: the job post's wording (more country packs coming; see `regions/`)
- **OPT clock** — US F-1 OPT unemployment days (90, or 150 with STEM) right in the sidebar
- **Sponsor Check** — look up any employer in any supported country before you apply
- **Multi-platform** — LinkedIn Easy Apply, Indeed, Dice, and external ATS portals (Workday, Greenhouse, Lever, iCIMS, and more)
- **AI resume tailoring** — rewrites your resume for each job using GPT-4o-mini, generates DOCX and PDF in 3 templates (Classic, Modern, Executive)
- **Fit scoring** — scores each job 1–10 and skips poor matches automatically based on your effort threshold
- **Gmail integration** — reads recruiter emails and drafts professional replies
- **Live web dashboard** — real-time feed, approval modal, application tracker, resumes viewer
- **Ask / Auto / Plan modes** — review each application before submitting, auto-apply, or just plan without submitting
- **Skills gap analysis** — highlights strong matches and missing skills for every tailored resume
- **Human-in-the-loop** — 8-second reading pause before every application; one click (or ← / →) to skip or approve

---

## Demo

```
xHR — AI Job Application Agent
Open http://localhost:8000 in your browser
```

The dashboard lets you type natural language commands:

```
apply java full stack jobs posted last 24 hours on linkedin
apply senior engineer roles on dice this week
check gmail for recruiter emails
```

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/ajaykattevirupu/job-copilot.git
cd job-copilot
pip install -r requirements.txt
playwright install chromium
```

### 2. Add your resume

Drop your resume as `resume.txt` in the project root (plain text works best).
Or upload it from the Settings panel in the dashboard.

### 3. Run

```bash
python run.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### 4. Load sponsor data for your countries (recommended)

**United States**: download the latest **LCA Programs (H-1B, H-1B1, E-3)** `.xlsx` files from the
[DOL performance data page](https://www.dol.gov/agencies/eta/foreign-labor/performance) (the last 2–3 fiscal years is plenty):

```bash
python scripts/build_sponsor_db.py --country US ~/Downloads/LCA_Disclosure_Data_FY2025_Q4.xlsx
```

**United Kingdom**: download the **Register of licensed sponsors: workers** CSV from
[gov.uk](https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers):

```bash
python scripts/build_sponsor_db.py --country GB ~/Downloads/Worker_and_Temporary_Worker.csv
```

Each country is stored in `data/regions/<code>.db`. Without it, verdicts fall back to the job post's wording.

### 5. Configure

Click the ⚙ Settings button and fill in:
- Profile (name, contact) and **Where you're job hunting** (country, whether you can already work there, sponsorship filter; US users also set visa status and OPT days)
- LinkedIn email + password
- Dice email + password (optional)
- OpenAI API key (for resume tailoring + fit scoring)
- Default job title and location

---

## Project Structure

```
xHR/
├── agent/
│   ├── linkedin_agent.py   # LinkedIn Easy Apply + external ATS
│   ├── indeed_agent.py     # Indeed applications
│   ├── dice_agent.py       # Dice.com applications
│   ├── portal_agent.py     # External ATS (Workday, Greenhouse, Lever…)
│   ├── gmail_agent.py      # Gmail recruiter reply automation
│   ├── browser.py          # Stealth Playwright browser utilities
│   ├── docx_generator.py   # DOCX resume templates (Classic/Modern/Executive)
│   ├── pdf_generator.py    # PDF resume generation
│   ├── filter_agent.py     # LinkedIn search filter automation
│   └── recorder.py         # Macro recording/replay
├── webapp/
│   ├── app.py              # FastAPI server + WebSocket
│   ├── agent_bridge.py     # Thread-safe agent ↔ browser communication
│   └── static/
│       ├── index.html      # Dashboard UI
│       ├── app.js          # Frontend logic
│       └── style.css       # Styles
├── scripts/
│   └── build_sponsor_db.py # Public sponsor data → data/regions/<country>.db
├── tests/                  # pytest suite
├── regions/                # Country packs: us.py (H-1B), uk.py (sponsor register), registry
├── sponsorship.py          # Per-job sponsorship verdict (country data + job-post wording)
├── visa.py                 # OPT unemployment clock
├── tailor.py               # OpenAI resume tailoring + fit scoring
├── prompts.py              # All AI prompts
├── tracker.py              # Application history (JSON)
├── user_profile.py         # Profile setup + immigration Q&A
└── run.py                  # Entry point
```

---

## How It Works

1. You type a command like `apply java full stack jobs posted last 24 hours`
2. The agent searches LinkedIn (and/or Indeed, Dice) with your filters
3. For each job, GPT-4o-mini scores the fit (1–10) — low scores are skipped
4. Your resume is tailored to the job description and saved as DOCX + PDF
5. In **Ask mode**, an approval modal shows you the JD + tailored resume before submitting
6. The application is submitted and tracked

---

## Requirements

```
fastapi
uvicorn
playwright
openai
python-docx
pypdf
reportlab
plyer
```

---

## Notes

- Your credentials are stored in **localStorage** in the browser — never sent to any server other than LinkedIn/Indeed/Dice directly
- `profile.json`, `resume.txt`, `browser_profile/`, and `applications.json` are in `.gitignore` — never committed
- The agent uses a persistent browser profile so you stay logged in across runs

---

## License

MIT

---

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```
