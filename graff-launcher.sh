#!/bin/sh
set -eu

# ---- Write router config (non-secret metadata only) ----
mkdir -p .graff
cat > .graff/.config.router << 'ROUTER'
{
  "id": "opencode-go",
  "name": "OpenCode Go (via shim)",
  "base_url": "http://127.0.0.1:18923/v1",
  "env_key": "OPENCODE_GO_API_KEY",
  "default_model": "mimo-v2.5-pro",
  "takes_effort": true
}
ROUTER

# ---- Start transport shim ----
SHIM_DIR="$(cd "$(dirname "$0")" && pwd)"
export SHIM_SESSION_ID="${SHIM_SESSION_ID:-$(cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')}"
export SHIM_PORT="${SHIM_PORT:-18923}"
python3 "$SHIM_DIR/opencode_shim.py" "$SHIM_PORT" >/dev/null 2>&1 &
SHIM_PID=$!

# Wait for shim to be ready
sleep 1

# Cleanup on exit
trap "kill $SHIM_PID 2>/dev/null" EXIT

# ---- Launch Graff ----
exec "$SHIM_DIR/graff" "$@"
