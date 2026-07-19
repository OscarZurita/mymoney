# Personal Finance & Investment Tracker

A privacy-focused Django application for tracking expenses, incomes and investments, and exploring financial analysis workflows.

## Current Features

* User authentication (Django built-in) with customizable Year Goal
* Expense, Income and Investment
* Categories and user-specific tagging
* Expense filtering and analysis views
* Dashboard
* Server-rendered templates

## Planned Features

* Investment tracking -> using external API to track user portfolio real-time
* Portfolio analytics
* Reporting and automatic backup

## Tech Stack

* Backend: Django
* Database: PostgreSQL
* Frontend: Django Templates

## Project Structure

```text
mymoney/
|-- manage.py
|-- .env.example
|-- docker-compose.yml
|-- mymoney/
|   |-- settings.py
|   `-- urls.py
|-- money_app/
|   |-- models/
|   |   |-- __init__.py
|   |   |-- Transactions.py
|   |   |-- Models.py
|   |-- views.py
|   |-- forms.py
|   |-- urls.py
|   |-- migrations/
|   `-- templates/
`-- templates/
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

This starts PostgreSQL, waits for it to become healthy, applies database migrations
automatically, and launches the Django development server.

### 4. Create a login account

```bash
docker compose exec web python manage.py createsuperuser
```

### 5. Open the app

Visit [http://localhost:8000](http://localhost:8000) and log in.

### Everyday commands

| Action | Command |
| --- | --- |
| Start | `docker compose up -d` |
| View server logs | `docker compose logs -f web` |
| Stop (database is kept) | `docker compose down` |
| Stop **and wipe** the database | `docker compose down -v` |
| Rebuild after changing `requirements.txt` | `docker compose build web` |

Your project folder is mounted into the `web` container, so editing source code on
your machine reloads the server automatically — no rebuild needed. `requirements.txt`
is the exception: dependencies are installed into the image at build time, not read
from the mount, so you must rebuild whenever it changes.

## Alternative Setup: Running Django on the Host

Prefer to run Django directly on your machine (e.g. for step-through debugging) while
PostgreSQL runs in Docker? Use these steps instead. This needs Python 3.12 locally.

### 1. Install dependencies

```bash
pip install pipenv
pipenv install
```

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
pipenv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
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
pipenv run python manage.py migrate
```

### 5. Start the app

```bash
pipenv run python manage.py runserver
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

## Access From Your Phone (Tailscale)

[Tailscale](https://tailscale.com) puts your devices on a private WireGuard
network (a "tailnet"), so you can open the app from your phone anywhere
without exposing anything to the public internet.

### 1. On the computer that runs the app

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up        # prints a login URL — sign in (free account)
```

If ufw is active, let tailnet devices reach the app:

```bash
sudo ufw allow in on tailscale0 to any port 8000 proto tcp
```

### 2. Tell Django about the new names

`tailscale status` shows your machine's tailnet IP and name. Append them to
`ALLOWED_HOSTS` in `.env` (comma-separated, no spaces), e.g.:

```env
ALLOWED_HOSTS=localhost,127.0.0.1,mydesktop,mydesktop.tail1234.ts.net,100.101.102.103
```

Then restart the web container so Django rereads `.env`:

```bash
docker compose restart web
```

### 3. On the phone

Install the Tailscale app, sign in to the same account, toggle the VPN on,
and open `http://<machine>.<tailnet>.ts.net:8000`.

### Optional: HTTPS and a clean URL

```bash
sudo tailscale serve --bg 8000
```

serves the app at `https://<machine>.<tailnet>.ts.net` (real certificate, no
port in the URL). Add that origin to `.env` so form posts pass CSRF checks,
then restart the web container:

```env
CSRF_TRUSTED_ORIGINS=https://<machine>.<tailnet>.ts.net
```

The computer must stay on (not suspended) for the app to be reachable.

## Security Notes

* Keep `SECRET_KEY` private.
* Do not commit `.env`.
* Use a strong Postgres password in non-local environments.
* Consider host restrictions and SSL for deployed Postgres instances.
