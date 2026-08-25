# CivilStandards MVP

A working, self-contained web application for indexing jurisdictional civil engineering standards and monitoring official sources for changes.

## What is included

- Search by jurisdiction, discipline, category, title, or detail number
- Official-source links for every standards record
- SQLite database with jurisdictions, documents, versions, and change events
- Source fingerprinting and version history
- PDF text extraction for more stable PDF change detection
- HTML normalization to reduce false change alerts from scripts/styles
- Human-review workflow: changed engineering sources are **flagged**, not silently auto-approved
- Responsive frontend with Library, Changes, and About views
- JSON API for future mobile apps, admin tools, or integrations

## Run it

Requires Python 3.10+ and the packages `requests`, `beautifulsoup4`, and `pypdf` for the monitoring script. The web server itself uses only the Python standard library.

```bash
cd civil-standards-mvp
python server.py
```

Then open:

```text
http://127.0.0.1:8000
```

The SQLite database is created and seeded automatically on first run.

## Establish source baselines / check for updates

```bash
python monitor.py
```

On the first run, the monitor stores a content fingerprint for each source. On later runs:

- unchanged source → document stays `Verified`
- changed source → new version is stored + a `Needs review` change event is created
- failed check → document is marked with the check failure type

For production, schedule `python monitor.py` with cron, GitHub Actions, AWS EventBridge/Lambda, a Render cron job, or another scheduler.

## API

- `GET /api/stats`
- `GET /api/jurisdictions`
- `GET /api/filters`
- `GET /api/documents?q=&jurisdiction_id=&discipline=&category=`
- `GET /api/documents/<id>`
- `GET /api/changes`
- `POST /api/documents`
- `POST /api/changes/<id>/review`

Example create-document request:

```json
{
  "jurisdiction_id": 1,
  "title": "Standard Drainage Details",
  "category": "Standard Details",
  "discipline": "Storm Drain",
  "detail_number": "Section III",
  "source_url": "https://official-government-source.gov/example.pdf",
  "file_type": "PDF",
  "revision_label": "2026",
  "notes": "Official agency source."
}
```

## Production roadmap

The MVP deliberately keeps the engineering-control model conservative. A commercial version should add:

1. User authentication and organization accounts
2. Role-based admin/reviewer permissions
3. PostgreSQL + object storage instead of local SQLite
4. Per-jurisdiction monitoring rules and crawler adapters
5. Visual/PDF page comparison for detected changes
6. AI-assisted change summaries **with source citations and mandatory review**
7. Email/Slack change alerts
8. Favorites, saved jurisdictions, and project-specific watchlists
9. CAD/DWG metadata and source links where agencies publish them
10. Billing, firm seats, and usage analytics
11. Audit logs and stronger legal/disclaimer language reviewed by counsel
12. Automated backups and source-retention policy

## Important limitation

This software is a reference/indexing system, not professional engineering advice. Before final design, permit submission, or construction, users should verify requirements with the governing jurisdiction and official source.

## Seed data

The demo is seeded with official-source examples from Anne Arundel County and Harford County, Maryland. Seed records are examples for the MVP and should be expanded through a controlled ingestion/review process before commercial use.

## Apple devices (iPhone, iPad, Mac)

This build is configured as an installable Progressive Web App (PWA) and includes iPhone/iPad safe-area, touch, and Safari-specific improvements.

### Mac — easiest local launch

1. Double-click `start_mac.command` in Finder. If macOS blocks it the first time, Control-click it, choose **Open**, then confirm.
2. Safari opens `http://127.0.0.1:8000` on the Mac.
3. The Terminal window prints a second address such as `http://192.168.1.25:8000`. Open that address in Safari on an iPhone or iPad connected to the **same Wi-Fi network**.
4. Keep the Terminal window open while using the local site. Press Control-C to stop the server.

If macOS Firewall asks whether Python may accept incoming connections, allow it on your private/home network so an iPhone or iPad can reach the local server.

### Add to the iPhone/iPad Home Screen

When the site is hosted over HTTPS, open it in Safari, tap **Share**, choose **Add to Home Screen**, then tap **Add**. It launches in a standalone app-style window with the included CivilStandards icon.

A local `http://192.168...` test URL works for browsing the app from another Apple device, but full PWA/service-worker behavior on iOS is most reliable after the website is deployed over HTTPS.

### Important architecture note

The iPhone/iPad is the client. The Python API, SQLite database, and source monitor run on a Mac or hosted server. iOS does not run this Python backend directly. For a production Apple experience, deploy the backend to an HTTPS host and then install the website to the Home Screen.

## Render deployment

This repository includes `render.yaml` for a Docker-based Render Web Service.

- Health check: `/api/stats`
- Render supplies `PORT` automatically; `server.py` reads it.
- The free Render filesystem is ephemeral. The demo reseeds its SQLite database after a restart.
- For persistent production data, set `DATABASE_PATH=/var/data/standards.db` and attach a paid persistent disk mounted at `/var/data`, or migrate the database layer to Postgres.
