# Personal Finance & Investment Tracker

A privacy-focused Django application for tracking expenses, incomes and investments, and exploring financial analysis workflows.

## Current Features

* User authentication (Django built-in) with customizable Year Goal
* Expense, Income and Investment
* Categories and user-specific tagging
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
|   |-- models/              # Category, YearGoal, transactions, tags
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
| Rebuild after changing `requirements.txt` | `docker compose build web` |

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

## Access From Your Phone (Tailscale)

[Tailscale](https://tailscale.com) puts your devices on a private WireGuard
network (a "tailnet"), so you can open the app from your phone anywhere
without exposing anything to the public internet.

### 1. On the computer that runs the app

If Tailscale is not already running:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up        # prints a login URL — sign in (free account)
```

`tailscale status` shows this machine's tailnet IP and name.

### 2. Publish the app on the tailnet address

Set `BIND_ADDRESS` in `.env` to the Tailscale IP, and add the tailnet names to
`ALLOWED_HOSTS` (comma-separated, no spaces):

```env
BIND_ADDRESS=100.101.102.103
ALLOWED_HOSTS=mydesktop.tail1234.ts.net,mydesktop,100.101.102.103,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://mydesktop.tail1234.ts.net:8000
```

Publishing on the Tailscale address rather than `0.0.0.0` is what keeps the app
off the local network and off the public internet: the port is only ever bound
on the tailnet interface. Then recreate the container so both the new port
binding and the new `.env` take effect:

```bash
docker compose up -d
```

If ufw is active, let tailnet devices reach the app:

```bash
sudo ufw allow in on tailscale0 to any port 8000 proto tcp
```

Skip that rule if the machine already runs a reverse proxy — see below, where
the app is never published on the tailnet interface in the first place.

### 3. On the phone

Install the Tailscale app, sign in to the same account, toggle the VPN on,
and open `http://<machine>.<tailnet>.ts.net:8000`.

The computer must stay on (not suspended) for the app to be reachable.

### If the machine already runs a reverse proxy

On a shared machine something is often already listening on ports 80 and 443 —
for example, Nginx Proxy Manager. Publishing the app on its own tailnet port alongside
it works, but going *through* the proxy is usually the better fit: the port
disappears from the URL, no new port is opened on any externally reachable
interface, and adding HTTPS later becomes a certificate change in one place
rather than a change to this app.

The proxy runs in a container, so it cannot reach `127.0.0.1` on the host — that
is its own loopback. It reaches the host at the gateway address of the bridge
network its container sits on, which `ip -br addr` shows as the `172.x.0.1` on a
`br-*` interface. Publish the app there:

```env
BIND_ADDRESS=<bridge-gateway-ip>
ALLOWED_HOSTS=<machine>.<tailnet>.ts.net,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://<machine>.<tailnet>.ts.net
```

That address is reachable from the host and from containers on that bridge, and
from nowhere else — not the LAN, not the tailnet, not the internet. Only the
proxy's own ports 80/443 face outward.

Then whoever administers the proxy adds a host pointing at it. In Nginx Proxy
Manager that is **Hosts → Proxy Hosts → Add Proxy Host**:

| Field | Value |
| --- | --- |
| Domain Names | `<machine>.<tailnet>.ts.net` |
| Scheme | `http` |
| Forward Hostname / IP | `<bridge-gateway-ip>` |
| Forward Port | `8000` |
| Block Common Exploits | on |
| Websockets Support | off (this app does not use them) |

A default-deny firewall blocks container-to-host traffic, so the proxy may also
need to be allowed through to that address:

```bash
sudo ufw allow from <bridge-subnet> to <bridge-gateway-ip> port 8000 proto tcp
```

Worth testing before asking for it — on some hosts the bridge is already
permitted. With the app up, from any container on that network:

```bash
docker run --rm --network <proxy-network> curlimages/curl \
  -sS --max-time 5 -o /dev/null -w '%{http_code}\n' http://<bridge-gateway-ip>:8000/
```

A status code means the rule is unnecessary; a timeout means it is needed.

One caveat: bridge subnets are assigned when the network is created, so if the
proxy's stack is ever torn down and recreated it may come back on a different
`172.x`. Re-check `ip -br addr` and update `BIND_ADDRESS` if the app suddenly
becomes unreachable through the proxy.

### On serving this over plain HTTP

Tailscale carries every byte between your devices inside an encrypted WireGuard
tunnel, so HTTP *over the tailnet* is not sent in the clear — the transport
encryption TLS would add is already there.

This is why `BEHIND_TLS_PROXY` defaults to `False`, leaving
`SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` off, and why
`manage.py check --deploy` reports warnings about them. Turning them on without
terminating TLS would break the app outright: the browser would never send the
session or CSRF cookie back over an `http://` origin, so you could not log in.

Once something in front does terminate HTTPS, set `BEHIND_TLS_PROXY=True` and
change `CSRF_TRUSTED_ORIGINS` to the `https://` origin. Django then trusts the
proxy's `X-Forwarded-Proto` header to tell it the browser-facing scheme and
marks its cookies secure. Enable it *only* behind such a proxy: if the app can
also be reached directly, a client can send that header itself.

Two ways to get there. If the machine runs a reverse proxy (above), issue the
certificate there — in Nginx Proxy Manager, the **SSL** tab of the proxy host.
Otherwise `tailscale serve --bg 8000` does it, given port 443 free on the tailnet
address, HTTPS certificates enabled for the tailnet in the Tailscale admin
console, and either root or an `OperatorUser` set on `tailscaled`.

## Deploying on a Shared Machine Without sudo (Rootless Docker)

Talking to the normal Docker daemon requires membership of the `docker` group,
which is equivalent to root on the host — on a machine you share, an admin may
reasonably decline to grant it. Rootless Docker is the alternative: your own
Docker daemon, running as your user, with its own containers, images and volumes,
invisible to and isolated from anyone else's.

An administrator has to run only this, once:

```bash
sudo apt-get install -y uidmap      # provides newuidmap/newgidmap
```

Plus one firewall rule, whose shape depends on how the app is reached — see
[Access From Your Phone](#access-from-your-phone-tailscale). Published directly
on the tailnet it is `ufw allow in on tailscale0 to any port 8000 proto tcp`;
behind a reverse proxy it is the narrower container-to-host rule, and may not be
needed at all.

Everything else you can do yourself:

```bash
loginctl enable-linger "$USER"      # keep the daemon alive after you log out
dockerd-rootless-setuptool.sh install
systemctl --user enable --now docker
export DOCKER_HOST=unix:///run/user/$(id -u)/docker.sock
```

Add that `DOCKER_HOST` line to `~/.bashrc` so it applies to new shells. Then
`docker compose up -d` works exactly as documented above.

Two things behave differently under rootless Docker:

* **Published ports go through the firewall normally.** Rootful Docker inserts its
  own iptables rules and its published ports bypass ufw entirely; rootless Docker
  binds an ordinary socket, so a default-deny ufw policy *will* block it. This is
  why the app needs a `ufw allow` rule when a rootful service on the same machine —
  a reverse proxy, say — appears to need none.
* **Container UID 0 maps to your host user.** The remaining container UIDs map into
  the subordinate range in `/etc/subuid`, which your host user cannot write as. So
  set `CONTAINER_USER=0:0` in `.env` to keep files the container writes into the
  bind mount owned by you. Under rootless Docker that is not a privilege grant —
  container root has no rights on the host.

Ports below 1024 are not bindable by default under rootless Docker; port 8000 is
unaffected.

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

## Security Notes

* Keep `SECRET_KEY` private.
* Do not commit `.env`.
* Backups are unencrypted database dumps: sync them only to devices you trust.
* Use a strong Postgres password in non-local environments.
* Consider host restrictions and SSL for deployed Postgres instances.
* Keep `DEBUG=False` on anything long-running or reachable from other devices.
* Prefer binding the app to a specific address (`BIND_ADDRESS`) over `0.0.0.0`, so
  that what can reach it is decided by which interface it listens on.
