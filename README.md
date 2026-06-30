# Idea Builder

[![Support me on Patreon](https://img.shields.io/badge/Patreon-Support%20my%20work-FF424D?style=flat&logo=patreon&logoColor=white)](https://www.patreon.com/AndersBjarby)

A Flask web app that uses an LLM to generate and combine ideas. You give it a concept and it generates related ideas, proposes combinations of how they could work together, rates them, and collects the best ("gold") ideas — with prompt groups, image handling, and PDF export.

## What it does

- **Idea generation** — generate related ideas for a concept and combine them, driven by a configurable LLM (OpenRouter / OpenAI-compatible, default model `openai/gpt-4o-mini`).
- **Prompt groups** — save and switch between named sets of system / combination / generation prompts.
- **Idea rating** — rate generated ideas against a configurable rating prompt; promising ones are kept as "gold ideas".
- **URL ingestion** — fetch and parse web page content (BeautifulSoup) to feed the idea engine.
- **Images & PDF** — image storage via Imgur, plus PDF export of ideas (ReportLab).
- **Admin & auth** — session-based authentication, settings, and password change.
- Data persisted in PostgreSQL via Flask-SQLAlchemy / psycopg2.

## Setup

```bash
pip install -r requirements.txt
python main.py
```

The app serves on the host/port set in `main.py` (`0.0.0.0:80`). Configure your API key and model in the app's settings UI. Originally built to run on Replit (see `.replit`).

## Tech

Python, Flask, Flask-SQLAlchemy, PostgreSQL, OpenAI/OpenRouter API, BeautifulSoup, Pillow, ReportLab, Imgur storage.
