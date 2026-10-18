# Personal Finance & Investment Tracker

A privacy-focused Django application for tracking expenses, incomes and investments, and exploring financial analysis workflows.

## Current Features

* User authentication (Django built-in) with customizable Year Goal
* Expense, Income and Investment
* Categories and user-specific tagging
* Shared expenses and debts: track who owes whom; statistics count only your share
* Expense filtering and analysis views
* Dashboard
* Server-rendered templates
* Automatic nightly database backups

## Planned Features

* Investment tracking -> using external API to track user portfolio real-time
* Portfolio analytics
* Reporting

## Tech Stack

* Backend: Django
* Database: PostgreSQL
* Frontend: Django Templates
* Serving: Gunicorn, with WhiteNoise for static files

## Project Structure

```text
mymoney/
|-- manage.py
|-- .env.example
|-- requirements.txt         # runtime dependencies, installed in the image
|-- requirements-dev.txt     # adds the dev tools (Ruff)
|-- pyproject.toml           # Ruff configuration
|-- docker-compose.yml       # always-on: gunicorn, DEBUG=False
|-- docker-compose.dev.yml   # dev override: runserver, DEBUG=True
|-- scripts/
|   `-- backup.sh            # database dump, run nightly
|-- deployment/              # systemd units that schedule the backup
|-- mymoney/                 # project settings and root URLs
|-- money_app/
|   |-- models/              # Category, YearGoal, transactions, tags, debts
|   |-- forms/
|   |-- views/
|   |-- templatetags/        # the |money filter
|   |-- migrations/
|   |-- formatting.py
|   |-- urls.py
|   `-- tests.py
|-- templates/               # all HTML templates
`-- static/                  # stylesheet, light and dark theme
```

## Getting Started

The quickest way to run the whole app — Django **and** PostgreSQL — is with Docker
Compose. The commands below are identical on Linux, Windows, and macOS.

### Prerequisites

* **Docker** with the Compose plugin:
  * Windows / macOS: install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
  * Linux: install Docker Engine and the Compose plugin, and add your user to the
    `docker` group.
* **Git** to clone the repository.

### 1. Clone the repository

```bash
git clone <repository-url>
cd mymoney
```

### 2. Create your environment file

Copy the template to `.env` (which is kept out of version control):

* Linux / macOS: `cp .env.example .env`
* Windows (PowerShell): `Copy-Item .env.example .env`
* Windows (Command Prompt): `copy .env.example .env`

Then open `.env` and set your own values — at minimum a real `SECRET_KEY` and your
chosen database credentials. Leave `POSTGRES_HOST=127.0.0.1`; Docker Compose
overrides it to `postgres` inside the container automatically.

Generate a secret key (works on any OS, no local Python needed):

```bash
docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 3. Build and start the app

```bash
docker compose up -d --build
```

This starts PostgreSQL, waits for it to become healthy, applies database migrations,
collects static files, and launches Gunicorn.

### 4. Create a login account

```bash
docker compose exec web python manage.py createsuperuser
```

### 5. Open the app

Visit the address in `BIND_ADDRESS`/`DJANGO_PORT` — by default
[http://localhost:8000](http://localhost:8000) — and log in.

### Two modes

The app runs in one of two configurations, chosen by which compose files you pass.

**Always-on** (the default) runs Gunicorn with `DEBUG=False`. This is what should be
running when you are just *using* the app:

```bash
docker compose up -d
```

**Development** swaps in `runserver` with `DEBUG=True`, so code changes reload
automatically and errors render a full traceback in the browser:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Both modes bind-mount the source and share the same database and container names, so
the dev command *replaces* the running web container rather than competing with it for
the port. `docker compose up -d` puts the always-on configuration back.

`DEBUG` is worth leaving off outside of development for a reason that is easy to miss:
with it on, Django appends every SQL query it runs to `connection.queries` and never
frees them, so a process that stays up for weeks grows without bound. The debug error
page also renders the local variables of every stack frame to whoever triggered it.

You do not lose tracebacks by running with `DEBUG=False`. The `LOGGING` block in
`settings.py` routes them to stdout, so `docker compose logs -f web` shows the same
traceback the debug page would have.

### Everyday commands

| Action | Command |
| --- | --- |
| Start (always-on) | `docker compose up -d` |
| Start (development) | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` |
| View server logs, including tracebacks | `docker compose logs -f web` |
| Apply code changes in always-on mode | `docker compose restart web` |
| Stop (database is kept) | `docker compose down` |
| Stop **and wipe** the database | `docker compose down -v` |
| Rebuild after changing `requirements.txt` | `docker compose up -d --build` |

Your project folder is mounted into the `web` container, so editing source code on your
machine takes effect without a rebuild — instantly in development mode, and on the next
`docker compose restart web` in always-on mode. `requirements.txt` is the exception:
dependencies are installed into the image at build time, not read from the mount, so you
must rebuild whenever it changes.

## Alternative Setup: Running Django on the Host

Prefer to run Django directly on your machine (e.g. for step-through debugging) while
PostgreSQL runs in Docker? Use these steps instead. This needs Python 3.12 locally.

### 1. Install dependencies

```bash
python -m venv .venv               # with Python 3.12
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

Run the remaining commands in this activated environment.

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```env
SECRET_KEY='replace-with-a-generated-secret-key'
DEBUG=True
DATABASE_BACKEND=postgres
POSTGRES_DATABASE=mymoney
POSTGRES_USER=mymoney_user
POSTGRES_PASSWORD=change-me
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

You can generate a Django secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 3. Start Postgres container using Docker

Make sure Docker Desktop is running, then from PowerShell/terminal in the project directory run:

```
docker compose up -d postgres
```

Check that the container is healthy:

```
docker compose ps
docker compose logs postgres
```

The container exposes Postgres on `127.0.0.1:${POSTGRES_PORT}` so Django can keep running directly on the machine.

### 4. Run migrations

```bash
python manage.py migrate
```

### 5. Start the app

```bash
python manage.py runserver
```

### Notes

* Running Django in Docker is already set up (see [Getting Started](#getting-started)); the `web` service sets `POSTGRES_HOST=postgres` for you, so `.env` can keep `127.0.0.1` for host runs.
* Postgres container credentials are only applied the first time the volume is created. If you change `POSTGRES_DATABASE`, `POSTGRES_USER`, or passwords later, recreate the volume:

```
docker compose down -v
docker compose up -d postgres
```

## Optional SQLite Fallback

The project now defaults to Postgres. For temporary local work against SQLite, set:

```env
DATABASE_BACKEND=sqlite
```

This is mainly intended for local migration/export workflows and test convenience.


## Automatic Backups

`scripts/backup.sh` dumps the database into `BACKUP_DIR` (default `~/mymoney-backups`)
and deletes dumps older than `BACKUP_KEEP_DAYS` (default 30). A systemd timer runs it
every night, and [Syncthing](https://syncthing.net) copies the folder to your other
devices.

**1. Schedule it** on the machine that runs the app:

```bash
mkdir -p ~/.config/systemd/user
cp deployment/mymoney-backup.* ~/.config/systemd/user/
```

Edit the copied `mymoney-backup.service` if the repository is not at `~/mymoney`, or
if you use rootless Docker — the file says what to change. Then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now mymoney-backup.timer
loginctl enable-linger "$USER"                  # run even while you are logged out
systemctl --user start mymoney-backup.service   # take a first backup now
```

`systemctl --user status mymoney-backup.service` shows how the last run went.

**2. Share the folder** in Syncthing: add `BACKUP_DIR` as *Send Only* on this machine
and accept it as *Receive Only* on the others.

**To restore** a dump:

```bash
docker compose exec -T postgres sh -c \
  'pg_restore --clean --if-exists --no-owner --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < ~/mymoney-backups/mymoney-<timestamp>.dump
docker compose restart web   # re-applies any migrations newer than the dump
```

## Contributing

How to run the tests, the code style (Ruff) and the commit conventions are in
[AGENTS.md](AGENTS.md), written for AI coding agents and people alike.

Any documentation meant for people to read, whether written by hand or generated, must stay
as simple, concise and readable as possible.

## Security Notes

* Keep `SECRET_KEY` private.
* Do not commit `.env`.
* Backups are unencrypted database dumps: sync them only to devices you trust.
* Use a strong Postgres password in non-local environments.
* Consider host restrictions and SSL for deployed Postgres instances.
* Keep `DEBUG=False` on anything long-running or reachable from other devices.
* Prefer binding the app to a specific address (`BIND_ADDRESS`) over `0.0.0.0`, so
  that what can reach it is decided by which interface it listens on.
