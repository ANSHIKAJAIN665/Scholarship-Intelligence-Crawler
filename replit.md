# Scholarship Intelligence

An evidence-traced scholarship discovery and monitoring dashboard for Indian students.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — starts the shared `/api` server and its FastAPI scholarship service.
- `pnpm --filter @workspace/scholarship-intelligence run dev` — starts the React dashboard.
- `python3 scripts/run_crawler.py` — runs one live crawl; add `--interval-hours 24` to repeat.
- `python3 -m pytest` — runs the crawler, database, scoring, evidence, and status tests.
- `pnpm run typecheck` — checks the TypeScript workspace.
- `python3 scripts/simulate_changes.py` — runs a clearly labeled change example against an isolated demo database.

## Stack

- pnpm workspaces, Node.js, TypeScript, React, and Vite
- FastAPI and Pydantic, bridged through the shared Express API
- SQLite with SQLAlchemy
- Requests, BeautifulSoup, optional Playwright fallback, and pypdf

## Product

- Discovers scholarship opportunities from configured primary-source websites.
- Stores field-level excerpts, source URLs, extraction timestamps, deterministic verification scores, and historical changes.
- Displays search, filters, scholarship details, crawl statistics, evidence, and score explanations.
- Missing fields stay `Not specified`; the dashboard does not seed fake scholarship records.

## Architecture decisions

- SQLite is the scholarship system of record because the assignment explicitly requires it; unrelated workspace database packages are not used by the crawler.
- The dashboard calls typed generated hooks through `/api`; Express forwards app routes to the local FastAPI service.
- The demo change script uses a separate SQLite file so simulated records never contaminate live totals.
- Confidence is rule-based and thresholded at 95 points; an LLM is not used to invent values or scores.

## Gotchas

- The API workflow must run for the dashboard's scholarship data routes.
- A failed crawl is not evidence that a source disappeared. Only a successful official index check can mark an NSP record `NO_LONGER_VERIFIABLE`.
- The first crawl can take time because sources and guideline PDFs are fetched respectfully and individually.
- `requirements.txt` is the Python dependency list; in this hosted workspace the package manager also maintains the Python environment.
