# Private Equity Deal Screener + Quick LBO Engine

Live demo: https://dealflow-metrics-1.preview.emergentagent.com

Resume-ready project that showcases modern Private Equity data science workflows: sourcing and screening target companies, computing valuation and quality factors, and underwriting a 5-year LBO with FCF-driven deleveraging to report MOIC and IRR. Built as a production-style, cloud-native full-stack app.


## What this project demonstrates
- Deal sourcing and screening discipline using quantitative factors (margin, growth, multiple)
- Comparable valuation metrics (EV/EBITDA) with sector/geo analytics
- LBO underwriting fundamentals: leverage sizing, interest expense, capex/NWC drag, tax shield, deleveraging, MOIC, IRR
- Modern data ingestion: chunked CSV uploads to scale beyond proxy limits
- Production-style architecture and best practices (UUIDs, env-based routing, typed models)

Keywords to highlight on resume: deal funnel, sourcing, screening, diligence, EV/EBITDA, EBITDA margin, revenue growth, net debt, leverage multiple, entry/exit multiple, FCF, deleveraging, MOIC, IRR, investment committee (IC) readiness.


## Architecture
- Frontend: React (functional, modern UI), environment-based backend URL: `REACT_APP_BACKEND_URL`
- Backend: FastAPI with Motor (async MongoDB), prefixed routes: `/api/*`
- Database: MongoDB (Motor client). UUIDs for IDs, not Mongo ObjectIDs, for clean JSON
- Ingress rules: all backend APIs must be called with `/api` prefix. Frontend calls backend via `REACT_APP_BACKEND_URL`
- Services: supervised processes, hot reload enabled


## Key features
1) Deal Screener
- Import deals via CSV (chunked upload) or seed sample data
- Filter by sector/geo and EV/EBITDA range
- Rank by a proprietary score combining margin, growth, and multiple
- Dashboard cards: Deal count, average EV/EBITDA, median EV/EBITDA

2) Quick LBO model
- Inputs: entry multiple, leverage, growth, margin, capex %, NWC %, tax rate, interest rate, exit multiple, years
- Mechanics: FCF used to amortize debt each year; exit value from exit multiple on year-5 EBITDA
- Outputs: entry EV/debt/equity, exit EV and debt, equity value at exit, MOIC, IRR, yearly schedule (Revenue, EBITDA, Interest, Capex, NWC Δ, FCF, Debt End)

3) CSV ingest
- Chunked upload with init → chunk → complete flow
- Flexible column mapping and validation


## Data model (Deal)
Field summary in API responses (DealOut):
- id (UUID string)
- name, sector, subsector, geography
- revenue (float, in millions)
- ebitda (float, in millions)
- ebitda_margin (0..1)
- ev (float, in millions)
- ev_ebitda (float), computed if absent
- growth_rate (0..1)
- net_debt (float)
- deal_stage (sourced | screened | diligence | IC | closed)
- source (seed | csv_upload | other)
- created_at, updated_at (UTC)
- score (float) — derived


## Scoring formula (Screener)
Intuition: higher margins and growth are good; lower entry multiple is good.

```
score = 100 * (0.4 * margin + 0.4 * growth + 0.2 * (1 / (1 + max(ev_ebitda - 5, 0))))
```

This yields a 0–100-ish ranking for fast triage in the pipeline.


## LBO methodology
- Entry EV = EBITDA × entry EV/EBITDA
- Debt at close = leverage multiple × entry EBITDA
- Equity at close = EV − Debt (guardrail: must be positive)
- For each year: Revenue grows by growth; EBITDA = margin × Revenue
- Cash flows: FCF = EBITDA − Capex − ΔNWC − Interest − Tax, where Tax = max(EBITDA − Interest, 0) × tax_rate
- Use FCF to amortize debt fully (no optionality modeling here)
- Exit EV = EBITDA_yearN × exit multiple; Equity_exit = Exit EV − Debt_end; MOIC = Equity_exit / Equity_entry; IRR = (MOIC^(1/N)) − 1

This simplified engine is calibrated for a fast IC pre-read; sensitives come from adjusting input fields.


## API reference (all routes prefixed with /api)
Health
- GET `/api/` → { message: "Hello World" }

Deals
- POST `/api/deals` → DealOut
- GET `/api/deals` → [DealOut]
  - query params: sector, geography, ev_ebitda_min, ev_ebitda_max, revenue_min, revenue_max
- PUT `/api/deals/{id}` → DealOut (recomputes EV/EBITDA when EV or EBITDA changes)
- DELETE `/api/deals/{id}` → { status: "deleted" }
- POST `/api/deals/screener` (ScreenerFilters JSON) → [DealOut]
- GET `/api/deals/metrics` → { count, avg_multiple, median_multiple, by_sector, by_geo }

LBO
- POST `/api/lbo/quick` (LBORequest JSON) → LBOResponse with MOIC, IRR, yearly schedule

CSV Upload (chunked)
- POST `/api/upload/init` → { upload_id }
- POST `/api/upload/chunk` (multipart: upload_id, index, chunk) → { status: "ok", index }
- POST `/api/upload/complete` (form: upload_id) → { inserted }

Seed
- POST `/api/seed` → { inserted: 3 }


## CSV format (minimal)
Required columns (case-insensitive):
- name, sector, geography, revenue, ebitda
Optional columns: subsector, ev, ev/ebitda, growth_rate (or growth), net_debt

Example:
```
name,sector,geography,revenue,ebitda,ev
TechCorp Alpha,Technology,US,100,25,200
HealthCare Beta,Healthcare,EU,80,16,144
Industrial Gamma,Industrials,US,120,18,162
```


## Environment and routing
- Frontend uses `REACT_APP_BACKEND_URL` from `frontend/.env`, and builds all calls as `${REACT_APP_BACKEND_URL}/api/...`
- Backend uses `MONGO_URL` and `DB_NAME` from `backend/.env`
- Do not hardcode URLs/ports. Backend binds internally at 0.0.0.0:8001 via supervisor
- Ingress: Only `/api/*` routes reach the backend. Frontend routes are served on port 3000

Supervisor controls
```
sudo supervisorctl restart backend
sudo supervisorctl restart frontend
sudo supervisorctl restart all
```


## Local development (generic)
This repository includes ready-to-run FastAPI and React projects.
- Backend dependencies: see `backend/requirements.txt`
- Frontend dependencies: managed by yarn; scripts defined in `frontend/package.json`
- Always prefer `yarn` over `npm` for frontend


## How to talk about this in interviews
- Deal funnel: explain how you triage targets with margin, growth, and multiple into a single rankable score and why this speeds diligence allocation
- Underwriting: discuss deleveraging through FCF, tax shield via interest, and role of capex/NWC in cash conversion
- Calibration: tuning leverage, entry/exit multiple, and growth to reflect sector realities; using scenario inputs as a sensitivity tool
- Data ops: UUIDs for API cleanliness, chunked ingest to bypass proxy limits, and aggregation for sector/geo statistics


## Roadmap ideas
- IC memo generation and NLP risk extraction (use Emergent LLM Key for OpenAI/Anthropic/Gemini via emergent integrations)
- Portfolio monitoring (post-deal KPIs, covenants, alerts)
- Factor calibration and Monte Carlo scenarios for LBO
- User auth and roles (Partner/Associate/Analyst views)


## Repository structure (high-level)
```
/app
  backend/
    server.py
    requirements.txt
    .env
  frontend/
    src/App.js
    src/App.css
    .env
  tests/
  scripts/
  README.md
  test_result.md (testing coordination file)
```


## Credits
- React + FastAPI + Mongo (Motor)
- Thanks to the PE veterans whose heuristics inspired the screening score and quick LBO assumptions


## License
The content is provided as-is for educational and portfolio purposes.