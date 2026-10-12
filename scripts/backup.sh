#!/usr/bin/env bash
# Database backup: dump Postgres into BACKUP_DIR and delete the dumps that have
# aged out. Run nightly by deployment/mymoney-backup.timer, or by hand.
#
# Getting the dumps off this machine is Syncthing's job, not this script's.
# Syncthing runs on its own and watches BACKUP_DIR, so a device that is offline
# when a dump is taken still receives it the next time it connects.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# A setting's value: the environment wins, then .env, then the default given.
setting() {
    local value=${!1:-}
    if [[ -z $value && -f .env ]]; then
        value=$(sed -n "s/^$1=//p" .env | tail -n 1)
        value=${value#[\"\']}
        value=${value%[\"\']}
    fi
    printf '%s' "${value:-$2}"
}

BACKUP_DIR=$(setting BACKUP_DIR "$HOME/mymoney-backups")
BACKUP_DIR=${BACKUP_DIR/#\~/$HOME}
BACKUP_KEEP_DAYS=$(setting BACKUP_KEEP_DAYS 30)

if [[ ! $BACKUP_KEEP_DAYS =~ ^[0-9]+$ ]]; then
    echo "BACKUP_KEEP_DAYS must be a whole number of days, got '$BACKUP_KEEP_DAYS'" >&2
    exit 1
fi

# The dumps hold every user's data: keep them readable by this user only.
umask 077
mkdir -p "$BACKUP_DIR"

dump="$BACKUP_DIR/mymoney-$(date +%Y-%m-%d-%H%M%S).dump"
partial="$dump.partial"
trap 'rm -f "$partial"' EXIT

# Run a command in the database container. The container already has the
# database name and user in its environment and trusts its own local socket,
# so no credentials need to be read or passed from here.
db() { docker compose exec -T postgres "$@"; }

# Fired right after a boot, the timer can get here before Postgres is ready, so
# give it up to a minute. If it never is, pg_dump below reports why.
for _ in {1..30}; do
    db sh -c 'pg_isready -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' 2>/dev/null && break
    sleep 2
done

db sh -c 'pg_dump --format=custom -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$partial"

# Read the dump back in full before trusting it: old dumps are only deleted
# once a new one is known to be restorable.
db pg_restore --file=/dev/null < "$partial"

mv "$partial" "$dump"
# The trailing * also sweeps up a .partial left behind by an interrupted run.
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'mymoney-*.dump*' \
    -mtime +"$BACKUP_KEEP_DAYS" -delete
echo "Backup written to $dump"
