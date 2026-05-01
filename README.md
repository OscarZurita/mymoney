# Personal Finance & Investment Tracker

A privacy-focused Django application for tracking expenses and exploring financial analysis workflows.

## Overview

This project is a learning-driven app that focuses on:

* Django backend architecture
* Financial domain modeling
* Secure handling of personal data
* Server-rendered UI for fast iteration
* Analytical features on top of transaction data

## Current Features

* User authentication (Django built-in feature)
* Expense CRUD
* Categories and user-specific tags
* Expense filtering and analysis views
* Server-rendered templates

## Planned Features

* Investment tracking
* Portfolio analytics
* Richer reporting and breakdowns
* API integrations

## Tech Stack

* Backend: Django
* Database: MySQL
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
|   |-- models.py
|   |-- views.py
|   |-- forms.py
|   |-- urls.py
|   |-- migrations/
|   `-- templates/
`-- templates/
```

## Setup

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
DATABASE_BACKEND=mysql
MYSQL_DATABASE=mymoney
MYSQL_USER=mymoney_user
MYSQL_PASSWORD=change-me
MYSQL_ROOT_PASSWORD=rootpass
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
```

You can generate a Django secret key with:

```bash
pipenv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 3. Start MySQL with Docker Desktop on Windows

Make sure Docker Desktop is running, then from PowerShell/terminal in the project directory run:

```
docker compose up -d mysql
```

Check that the container is healthy:

```
docker compose ps
docker compose logs mysql
```

The container exposes MySQL on `127.0.0.1:${MYSQL_PORT}` so Django can keep running directly on the machine.

### 4. Run migrations

```bash
pipenv run python manage.py migrate
```

### 5. Start the app

```bash
pipenv run python manage.py runserver
```

### Notes

* If you later move Django into Docker too, set `MYSQL_HOST=mysql` instead of `127.0.0.1`.
* MySQL container credentials are only applied the first time the volume is created. If you change `MYSQL_DATABASE`, `MYSQL_USER`, or passwords later, recreate the volume:

```
docker compose down -v
docker compose up -d mysql
```

## Optional SQLite Fallback

The project now defaults to MySQL. For temporary local work against SQLite, set:

```env
DATABASE_BACKEND=sqlite
```

This is mainly intended for local migration/export workflows and test convenience.

## Security Notes

* Keep `SECRET_KEY` private.
* Do not commit `.env`.
* Use a strong MySQL password in non-local environments.
* Consider host restrictions and SSL for deployed MySQL instances.

## Learning Goals

This project explores:

* Django architecture and patterns
* Form handling and validation
* Financial data modeling
* Analytics-oriented product design
* AI-assisted software development workflows
