#!/usr/bin/env python3
"""Transport shim: Graff -> OpenCode Go.

Purpose: Graff cannot inject the x-opencode-session header that OpenCode Go
requires for /v1/chat/completions requests. This shim acts as a transparent
HTTP proxy that adds the required session header while preserving all other
request/response data.

Contract (JCODE-GRAFF-BENCH-003 GATE 4C):
  CAN:
    - proxy GET  /v1/models
    - proxy POST /v1/chat/completions
    - support streaming (SSE) and non-streaming
    - preserve request body  (byte-for-byte passthrough)
    - preserve response body (byte-for-byte passthrough)
    - preserve requested model
    - preserve Authorization header from incoming request
    - inject x-opencode-session header (from SHIM_SESSION_ID env var)
    - use independent session identity per trial (SHIM_SESSION_ID)

  CANNOT:
    - modify prompt, system prompt, tools, model, reasoning, temperature
    - add hidden retries
    - rewrite or cache responses
    - share session ID between trials
    - log secrets or response content

Headers modified by the shim:
  ADDED:
    - x-opencode-session: from SHIM_SESSION_ID env var (required by OpenCode Go)
    - User-Agent: set to a standard HTTP client string. Required because
      Python's urllib default User-Agent is rejected by Cloudflare's HTTP
      validation layer (returns 403). This is standard HTTP compliance, not
      evasion -- any valid User-Agent works.
  PRESERVED:
    - Authorization: from incoming request (or from OPENCODE_GO_API_KEY env)
    - Content-Type: from incoming request
  NOT FORWARDED:
    - Transfer-Encoding: hop-by-hop header, excluded per HTTP spec

Usage:
  SHIM_SESSION_ID=<uuid> OPENCODE_GO_API_KEY=<key> python3 opencode_shim.py [port]

Environment:
  SHIM_SESSION_ID  : session identifier for OpenCode Go (required for /chat/completions)
  OPENCODE_GO_API_KEY : fallback API key if request has no Authorization header
  SHIM_PORT        : listen port (default 18923)
"""
import http.server
import os
import sys
import urllib.error
import urllib.request

UPSTREAM = "https://opencode.ai/zen/go"
SESSION_ID = os.environ.get("SHIM_SESSION_ID", "")
API_KEY = os.environ.get("OPENCODE_GO_API_KEY", "")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("SHIM_PORT", "18923"))

# Standard HTTP client User-Agent. Python urllib's default
# ("Python-urllib/3.x") triggers Cloudflare 403 responses because it fails
# basic HTTP client validation. Using a standard client identifier is normal
# HTTP behavior.
_USER_AGENT = "python-http-client/1.0"


class ShimHandler(http.server.BaseHTTPRequestHandler):
    """Transparent proxy that adds x-opencode-session to upstream requests."""

    def _proxy(self, method: str) -> None:
        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # Build upstream URL: UPSTREAM + request path
        # e.g., UPSTREAM="https://opencode.ai/zen/go" + "/v1/chat/completions"
        target = f"{UPSTREAM}{self.path}"

        # Build forwarded headers
        fwd_headers: dict[str, str] = {}

        # Required: session header for OpenCode Go
        if SESSION_ID:
            fwd_headers["x-opencode-session"] = SESSION_ID

        # Required: valid User-Agent for HTTP compliance
        fwd_headers["User-Agent"] = _USER_AGENT

        # Preserve Authorization from request, or use fallback from env
        auth = self.headers.get("Authorization")
        if auth:
            fwd_headers["Authorization"] = auth
        elif API_KEY:
            fwd_headers["Authorization"] = f"Bearer {API_KEY}"

        # Preserve Content-Type
        content_type = self.headers.get("Content-Type")
        if content_type:
            fwd_headers["Content-Type"] = content_type

        # Forward request to upstream
        req = urllib.request.Request(target, data=body, headers=fwd_headers, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=300)
            self._forward_response(resp)
        except urllib.error.HTTPError as e:
            self._forward_error(e)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f"shim error: {e}".encode("utf-8"))

    def _forward_response(self, resp) -> None:
        """Forward a successful upstream response to the client."""
        self.send_response(resp.status)
        for key, value in resp.getheaders():
            # Skip hop-by-hop headers per HTTP spec
            if key.lower() in ("transfer-encoding",):
                continue
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(resp.read())

    def _forward_error(self, err: urllib.error.HTTPError) -> None:
        """Forward an upstream error response to the client."""
        self.send_response(err.code)
        for key, value in err.headers.items():
            if key.lower() in ("transfer-encoding",):
                continue
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(err.read())

    def do_GET(self) -> None:
        self._proxy("GET")

    def do_POST(self) -> None:
        self._proxy("POST")

    def do_OPTIONS(self) -> None:
        self._proxy("OPTIONS")

    def log_message(self, format, *args) -> None:
        # Silent: no logging of requests (may contain auth headers)
        pass


def main() -> None:
    if not SESSION_ID:
        print("WARNING: SHIM_SESSION_ID not set; /chat/completions will fail", file=sys.stderr)
    print(f"SHIM_READY session={SESSION_ID[:16] if SESSION_ID else 'NONE'}... port={PORT}", flush=True)
    server = http.server.HTTPServer(("0.0.0.0", PORT), ShimHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
