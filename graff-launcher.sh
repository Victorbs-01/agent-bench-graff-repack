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

# Debug: log to stderr (never stdout — that's the ACP protocol channel)
echo "[graff-launcher] CWD=$(pwd)" >&2
echo "[graff-launcher] router=$(cat .graff/.config.router | tr -d '\n')" >&2
echo "[graff-launcher] KEY_SET=$([ -n "$OPENCODE_GO_API_KEY" ] && echo YES || echo NO)" >&2

# ---- Start transport shim ----
SHIM_DIR="$(cd "$(dirname "$0")" && pwd)"
export SHIM_SESSION_ID="${SHIM_SESSION_ID:-$(cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')}"
export SHIM_PORT="${SHIM_PORT:-18923}"
python3 "$SHIM_DIR/opencode_shim.py" "$SHIM_PORT" >/dev/null 2>&1 &
SHIM_PID=$!

# Wait for shim to be ready
sleep 1

# Debug: verify shim is running
echo "[graff-launcher] SHIM_PID=$SHIM_PID alive=$(kill -0 $SHIM_PID 2>/dev/null && echo YES || echo NO)" >&2

# Cleanup on exit
trap "kill $SHIM_PID 2>/dev/null" EXIT

# ---- Launch Graff ----
exec "$SHIM_DIR/graff" "$@"
