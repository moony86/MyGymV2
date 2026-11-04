# MyGym

تطبيق عربي لتسجيل التدريب، إنشاء برامج مبدئية حسب المعدات والخبرة، ومراجعة الحصص والتحليلات، مع حساب مستقل لكل مستخدم.

## Restored release: 2026-11-04

This release reconstructs the October 27 guidance release from retained source-writing history on top of the original `v3` branch. It restores authenticated accounts, ownership checks, idempotent set recording and local drafts, descriptive analytics, plan schedules and alternatives, equipment-aware generation, onboarding, session reviews, and explicitly confirmed progression proposals.

Training recommendations use recorded and self-reported information. The app does not observe technique, diagnose pain, guarantee results, or substitute for an in-person coach. Unknown effort stays unknown. Progression requires comparable evidence and user confirmation.

## Installation

Use Python 3.13. Install into a dedicated virtual environment, with persistent data outside the code checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export DB_PATH=/absolute/private/data/gym_tracker.db
export MYGYM_AUTH_DB=/absolute/private/data/mygym_auth.sqlite3
export ENV=production
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn src.apis.main:app --host 127.0.0.1 --port 8000
```

Serve through HTTPS (a TLS reverse proxy or Uvicorn TLS configuration). Session cookies require a secure connection. Leave `MYGYM_AUTH_ENABLED` enabled; disabling it is for isolated tests only. Restrict permissions on the data directory and files. Do not point a preview or test run at production data.

With a new empty authentication database, a private initial setup key is created at `secrets/mygym-bootstrap.txt` beside the authentication database. Use that key on `/login` to create the initial administrator. Subsequent family accounts are managed on `/accounts`. Existing authentication databases preserve usernames and password hashes.

For a new exercise database, inspect and run the catalog seeding/matching tools in `scripts/` before generating plans. Existing installations should preserve their exercise IDs and knowledge links.

## Validation

```sh
.venv/bin/python -m pytest tests -q --disable-warnings
.venv/bin/python -m pytest security_tests -q --disable-warnings
```

Run these in separate processes: security tests intentionally enable authentication, while functional tests use isolated databases. The root test configuration redirects database access before collection. Never set test flags on the production service.

## Backups and recovery

GitHub stores application source and migrations, **not** workout records, account hashes, cookies, certificates, or environment secrets. Back up both SQLite databases separately using SQLite's backup API; copying only a live `.db` file can miss WAL changes. Keep backups off the server as well. Restrict backup access because authentication backups contain password hashes.

Before deploying, save the current application release, service configuration, and fresh consistent database snapshots. Test a candidate against isolated synthetic data. Switch the service to the tested release while keeping persistent database paths unchanged. Restore code and service configuration if startup fails; do not replace newer user records with an old database backup. Never run an Alembic downgrade as an automatic rollback.

`scripts/reset_account_password.py` provides server-owner password recovery without printing the password. Export the intended authentication database path before using it.

## Media

Two exercise videos are included with individual attribution and CC BY-SA 4.0 license links in `static/exercise-media.json` and `static/media-attribution.html`. The videos are third-party works; their license does not grant a license to unrelated application code. Visual variant matching is not a professional biomechanics certification. Do not add third-party videos without checking reuse rights and exercise/equipment correspondence.

See [release notes](docs/releases/2026-11-04-restoration.md).
