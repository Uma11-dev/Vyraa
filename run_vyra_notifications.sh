#!/bin/bash
set -euo pipefail

PROJECT_DIR="/Users/uma/Vyraa"
LOCK_DIR="/tmp/vyra-notifications.lock"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "$(date): Another notification run is active; skipping." >> "$LOG_DIR/notifications.log"
    exit 0
fi

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

{
    echo "=== VYRA notification run: $(date) ==="
    "$PROJECT_DIR/venv/bin/python" \
        "$PROJECT_DIR/manage.py" \
        process_vyra_notifications
    echo "=== Run completed: $(date) ==="
} >> "$LOG_DIR/notifications.log" 2>&1
#!/bin/bash
set -euo pipefail

PROJECT_DIR="/Users/uma/Vyraa"
LOCK_DIR="/tmp/vyra-notifications.lock"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

# Prevent overlapping executions.
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "$(date): Another notification run is active; skipping." >> "$LOG_DIR/notifications.log"
    exit 0
fi

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

{
    echo "=== VYRA notification run: $(date) ==="
    "$PROJECT_DIR/venv/bin/python" \
        "$PROJECT_DIR/manage.py" \
        process_vyra_notifications
    echo "=== Run completed: $(date) ==="
} >> "$LOG_DIR/notifications.log" 2>&1
#!/bin/bash
set -euo pipefail

PROJECT_DIR="/Users/uma/Vyraa"
LOCK_DIR="/tmp/vyra-notifications.lock"

cd "$PROJECT_DIR"

# Prevent overlapping executions.
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "$(date): Another notification run is active; skipping."
    exit 0
fi

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

"$PROJECT_DIR/venv/bin/python" \
    "$PROJECT_DIR/manage.py" \
    process_vyra_notifications
