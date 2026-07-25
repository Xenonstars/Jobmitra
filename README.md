# 🤖 Job Application Automation System

**AI-powered job search and automated application system.** Discovers jobs across the internet, matches them to your resume using a local LLM (DeepSeek-R1 via Ollama), generates tailored applications, and submits them — all running locally with no cloud API costs.

## Features

✅ **Multi-source Job Discovery** — Indeed & LinkedIn crawling with automatic deduplication  
✅ **Intelligent Job Matching** — DeepSeek-R1 resume-job scoring (0–100 scale) with reasoning and gap analysis  
✅ **Tailored Materials** — Dynamic resume tailoring and professional cover letter generation per job  
✅ **Automated Application** — Playwright-powered form filling for LinkedIn, Naukri, and generic career pages  
✅ **Full Tracking** — Application history, status updates, and success metrics via Streamlit dashboard  
✅ **100% Local** — No cloud API keys required. Uses Ollama with your local models (DeepSeek-R1, Qwen3, or Llama 3.2)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | FastAPI + Uvicorn |
| **Frontend** | Streamlit |
| **Database** | SQLite (dev) / PostgreSQL (prod) |
| **Browser Automation** | Playwright |
| **LLM** | DeepSeek-R1 8B (via Ollama) |
| **Logging** | Structlog |

## Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) installed with a model pulled:
  ```bash
  ollama pull deepseek-r1:8b
  ```
- (Optional) Docker & Docker Compose for production deployment

### Local Development

**1. Install dependencies:**
```bash
pip install -r requirements.txt
playwright install chromium
```

**2. Copy environment config:**
```bash
cp env.example .env
```
Edit `.env` if needed (defaults work for local development).

**3. Start the backend:**
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

**4. Start the frontend (in a new terminal):**
```bash
streamlit run streamlit_app.py
```

**5. Open the dashboard:**
- **Streamlit UI:** http://localhost:8501
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

### Docker Deployment

```bash
docker-compose up -d
```

## API Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/resume/upload` | POST | Upload and parse a resume (PDF/DOCX) |
| `/api/resume/tailor` | POST | Generate a tailored resume for a job |
| `/api/resume/cover-letter` | POST | Generate a cover letter for a job |
| `/api/jobs/search` | POST | Search jobs across Indeed/LinkedIn |
| `/api/jobs/match` | POST | Score jobs against your resume via LLM |
| `/api/applications/apply` | POST | Submit an application (Playwright automation) |
| `/api/applications/` | GET | List all applications |
| `/auth/login` | POST | Login / create user |

## Project Structure

```
├── app.py                        # FastAPI entry point
├── config.py                     # App settings (LLM, DB, browser)
├── llm_service.py                # DeepSeek-R1: scoring, tailoring, cover letters
├── job_discovery_service.py      # Indeed + LinkedIn Playwright crawlers
├── streamlit_app.py              # Dashboard UI
├── db/
│   ├── models.py                 # User, Resume, Job, Application
│   └── session.py                # Async database session
├── services/
│   └── application_service.py    # Playwright auto-apply engine
├── routes/
│   ├── jobs.py                   # Job search & matching endpoints
│   ├── resume.py                 # Resume upload & tailoring endpoints
│   ├── applications.py           # Application submission & tracking
│   └── auth.py                   # User authentication
├── utils/logger.py               # Structured logging
├── docker/                       # Dockerfiles
└── scripts/init_db.sql           # PostgreSQL schema
```

## Switching Models

This project runs entirely on local LLMs via Ollama. To switch models:

```bash
# See available models
ollama list

# In .env or config.py, change:
LLM_MODEL=deepseek-r1:8b   # or qwen3:8b, llama3.2, etc.
```

## License

[MIT](LICENSE)


