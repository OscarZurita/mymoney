# AGENTS.md

Instructions for AI coding agents working in this repository. Human contributors can follow them too.
If an `AGENTS_LOCAL.md` file exists next to this one, read it as well. It holds git-ignored notes specific to one machine.

## Project Overview

mymoney is a self-hosted, privacy-focused personal finance tracker built with Django. Users record
expenses, incomes and investments with categories and their own tags, set a yearly spending goal, and
review a dashboard and analysis charts. It is meant to run on a machine its owner controls and to be
reached only from their own devices over a private network such as Tailscale, never from the public internet.

## Tech Stack

- Python 3.12 (Docker image `python:3.12-slim`)
- Django ~=6.0 with server-rendered templates. There is no JS framework: pages use small inline scripts, and charts are SVG built in Python.
- PostgreSQL 16 through psycopg 3 (`psycopg[binary]`). SQLite is a fallback for tests and quick local work.
- django-environ (settings from `.env`), Gunicorn, WhiteNoise
- Docker Compose for both development and the always-on deployment
- Ruff ~=0.17.1 for linting and formatting (dev only)

Dependencies are declared twice. Runtime dependencies are in `requirements.txt` (what the image installs)
and in Pipfile `[packages]`. Dev tools are in `requirements-dev.txt` and Pipfile `[dev-packages]`. Keep
each pair in sync. There is no lock file.

## Setup Commands

Docker (the main workflow):

```bash
cp .env.example .env            # then set SECRET_KEY and the Postgres credentials
docker compose up -d --build    # always-on: Gunicorn, DEBUG=False
docker compose exec web python manage.py createsuperuser   # then add categories at /admin/
docker compose -f docker-compose.yml -f docker-compose.dev.yml up   # dev: runserver, autoreload, DEBUG=True
docker compose logs -f web      # server logs and tracebacks
```

Every time the container starts, the entrypoint runs `migrate`, and also `collectstatic` except under the dev override.
The source is bind-mounted, so code changes need no rebuild, but only the dev server reloads them on its own:

- After changing code or `.env`, or pulling an update, run `docker compose restart web`. This also applies new migrations.
- After changing `requirements.txt`, a compose file, or `BIND_ADDRESS`, `DJANGO_PORT` or `CONTAINER_USER`,
  run `docker compose up -d --build`. It rebuilds the image and recreates the container.
- The dev override replaces the always-on container. When you stop it, the app is down until you run `docker compose up -d`.

Host Python (needed for Ruff, and handy for debugging). Postgres keeps running in Docker:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
docker compose up -d postgres
.venv/bin/python manage.py migrate
DEBUG=True .venv/bin/python manage.py runserver   # the variable beats .env; needs port 8000, so stop the web container first
```

## Code Style

- Ruff is configured in `pyproject.toml`, and the whole codebase passes it. Before committing, run both commands. Both must pass:
  ```bash
  .venv/bin/ruff check .
  .venv/bin/ruff format .
  ```
- Naming follows PEP 8: `snake_case` for functions, variables and modules, `PascalCase` for classes, `UPPER_CASE` for constants.
  Concrete classes are named `<Type><Role>` (`ExpenseForm`, `IncomeListView`, `InvestmentTag`).
  URL names are `snake_case` in the `money_app` namespace (`money_app:edit_income`).
- Inside `money_app`, use relative imports and import from the package, not the submodule:
  `from ..models import Expense`.
- Money is always `Decimal`. Display it with `format_money()` in Python or `{{ value|money }}` in templates (`{% load money_filters %}`).
- Comments explain *why*, not what.
- Templates live in the top-level `templates/` directory. Pages extend `base.html`. Page CSS goes in
  `{% block extra_style %}` and page JS in `{% block extra_script %}`. Shared styles and the light/dark
  theme variables live in `static/table.css`. Use those CSS variables so that both themes work.

## Testing Instructions

- Tests are in `money_app/tests.py` and use Django's `TestCase`. Put each test in the `<Subject>Tests` class it belongs to
  (`ExpenseFormTests`, `AuthenticatedExpenseViewTests`). Name test methods after the expected behavior:
  `test_user_cannot_delete_another_users_expense`.
- Fast run on SQLite (no Postgres needed):
  ```bash
  DATABASE_BACKEND=sqlite .venv/bin/python manage.py test
  # or, without host Python:
  docker compose run --rm --no-deps --entrypoint python -e DATABASE_BACKEND=sqlite web manage.py test
  ```
- If you change models, migrations or queries, also run the tests against Postgres. This starts the
  postgres container; stop it afterwards with `docker compose stop postgres` if it wasn't running before:
  ```bash
  docker compose run --rm --entrypoint python web manage.py test
  ```
- Without `DATABASE_BACKEND=sqlite`, tests use the backend set in `.env`. That is usually Postgres, which must then be running.
- To run a single test, give its dotted path: `manage.py test money_app.tests.ExpenseFormTests.test_form_requires_amount`.
- There is no numeric coverage target. Every behavior change and every bug fix needs a test. Code that
  reads or writes user data also needs a test showing that one user can't see or change another user's data.
- Both of these must pass too: `manage.py check`, and `manage.py makemigrations --check --dry-run`, which should print "No changes detected".

## Architecture Notes

This is a standard Django MVT project with a single app:

```text
mymoney/              project: env-driven settings, root URLs, WSGI/ASGI
money_app/
  models/             models.py (Category, YearGoal), transactions.py, tags.py; re-exported by __init__.py
  forms/              forms.py (signup, year goal), transactions.py (TransactionFormBase + concrete forms)
  views/              views.py (dashboard, analysis, goals, signup)
                      transactions.py (transaction CRUD class-based views)
                      _utils.py (query-string parsing, SVG chart geometry)
  templatetags/       money_filters (`|money`)
  formatting.py       money rounding and formatting
  migrations/
  tests.py
templates/            base.html, money_app/, registration/ (login, signup)
static/table.css      shared styles and the light/dark theme
scripts/backup.sh     nightly pg_dump; deployment/ holds its systemd timer templates
```

- **Transactions.** An abstract `Transaction` model has three concrete subclasses: `Expense`, `Income` and
  `Investment`. Each has its own tag model. Forms and views use the same pattern. `TransactionFormBase`
  and `TransactionListView`/`CreateView`/`UpdateView`/`DeleteView` hold the logic. Thin subclasses only
  set class attributes (`model`, `form_class`, `tag_model`, `category_type`, URL names). All types
  share the `transactions.html` and `add_transaction.html` templates. To add a transaction-like
  feature, subclass the bases; don't copy them.
- **Categories and tags.** `Category` is global: every user shares it, and it is managed in the admin. Each
  category has a type (`expense`, `income` or `investment`). A transaction's `clean()` rejects a category
  of the wrong type. Tags belong to a single user and are de-duplicated case-insensitively through `normalized_name`.
- **Tell, don't ask.** Behavior lives on the model that owns the data, as in `Category.matches_transaction_type`.
- **Settings.** All configuration comes from the environment or `.env`. `docker-compose.yml` overrides
  `POSTGRES_HOST` to `postgres` inside the compose network.

## Commits and Pull Requests

- Agents commit locally only, on the branch the maintainer has checked out. **Never create branches, push,
  open pull requests, or commit to `main`**; the maintainer does those. If the current branch is `main`,
  stop and ask the maintainer to create one.
- The maintainer branches off `main` as `<type>/<short-kebab-description>`, e.g. `feat/csv-export` or `fix/goal-rounding`.
- Commit messages use [Conventional Commits](https://www.conventionalcommits.org/):
  `<type>(<optional scope>): <imperative summary>`. Types: `feat`, `fix`, `refactor`, `test`,
  `docs`, `style`, `build`, `chore`. Example scopes: `expenses`, `dashboard`, `analysis`, `goals`,
  `backups`, `docker`. Keep the summary lowercase, under 72 characters, with no trailing period. Use the body for the *why*.
- Make one logical change per commit. A migration goes in the same commit as the model change that needs it.
- When the work is done, finish with a PR description in this format, ready for the maintainer to open the PR:

````markdown
## Summary
What changed and why.

## Changes
- ...

## Testing
- [ ] `manage.py test` passes on SQLite (and on Postgres if models, migrations or queries changed)
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] `makemigrations --check --dry-run` reports no changes
- [ ] Checked in the browser: <pages touched>

## Notes
New migrations, new settings in `.env.example`, deployment or backup impact.
````

## Security Considerations

- Secrets live only in `.env`, which is git-ignored. `.env.example` holds placeholders. Never commit `.env`,
  real hostnames or IPs, database dumps (`backups/`), or `AGENTS_LOCAL.md`. To add a setting, read it with
  `env(...)` in `settings.py` and add it to `.env.example` with a safe default.
- **Scope every query to the current user**, with `Model.objects.filter(user=request.user)` or
  `get_object_or_404(Model, pk=pk, user=request.user)`. Set `user` on the server, never from submitted
  form data. Forms accept a `user=` argument for this and never expose a `user` field.
- Every view except signup and login requires authentication. Function views use `@login_required`;
  class-based views list `LoginRequiredMixin` first among their bases.
- Anything that changes data is a POST with `{% csrf_token %}`. GET never modifies data (the delete views redirect on GET).
- Rely on template auto-escaping. Never use `|safe` or `mark_safe` on user content.
- Keep `DEBUG=False` outside the dev override. Bind to a specific address (`BIND_ADDRESS`), never `0.0.0.0`.
  Set `BEHIND_TLS_PROXY=True` only behind a proxy that terminates HTTPS. Postgres is published on loopback only; keep it that way.
- Backups are unencrypted dumps of every user's data. `scripts/backup.sh` writes them with `umask 077`; keep that.
- Templates load no third-party scripts, fonts, CDNs, analytics or trackers. Ask before adding any
  dependency, and when you do add one, declare it in both `requirements.txt` and the `Pipfile`.

## Things to Avoid

- Using `float` for money.
- Editing or deleting a committed migration. Change the model and run `makemigrations` to get a new one.
- Using `print()` for debugging. Use `logging`; its output appears in `docker compose logs`.
- Duplicating code for each transaction type instead of extending the base classes.
- Switching static storage to the *Manifest* WhiteNoise backend. It breaks `runserver`; `settings.py` explains why.
- Running `docker compose down -v`. It deletes the database volume.
