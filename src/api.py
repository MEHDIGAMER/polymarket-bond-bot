"""Read-only HTTP API for the dashboard. Stdlib http.server — no deps.

Bound to 0.0.0.0:8001 with API-key auth via Bearer header. Read-only by
design — no order placement, no config edits via HTTP. The dashboard
polls these endpoints every few seconds.
"""
import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import db
from .config import BOT, RISK
from .events import BUS


API_PORT = int(os.environ.get("API_PORT", "8001"))
API_KEY = os.environ.get("API_KEY", "")  # if unset, generate one on first start


def _ensure_api_key() -> str:
    """Read or write a persisted API key so dashboard config doesn't break on restart."""
    global API_KEY
    if API_KEY:
        return API_KEY
    key_path = os.path.join(os.path.dirname(BOT.DATABASE_PATH), "api.key")
    if os.path.exists(key_path):
        with open(key_path) as f:
            API_KEY = f.read().strip()
    else:
        API_KEY = secrets.token_urlsafe(32)
        os.makedirs(os.path.dirname(key_path), exist_ok=True)
        with open(key_path, "w") as f:
            f.write(API_KEY)
        os.chmod(key_path, 0o600)
    return API_KEY


def _row(r) -> dict:
    return {k: r[k] for k in r.keys()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silence default access log
        pass

    def _ok(self, payload, status=200):
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg, status=400):
        self._ok({"error": msg}, status)

    def _auth_ok(self) -> bool:
        hdr = self.headers.get("Authorization", "")
        return hdr == f"Bearer {API_KEY}"

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)

        # /health is unauthenticated for liveness probes
        if u.path == "/health":
            return self._ok({"status": "ok", "mode": BOT.MODE,
                             "ts": datetime.now(timezone.utc).isoformat()})

        # /stream supports either Bearer header OR ?key= (EventSource can't
        # send custom headers in browsers, so we accept both)
        if u.path == "/stream":
            qs_key = (parse_qs(u.query).get("key") or [""])[0]
            if not (self._auth_ok() or qs_key == API_KEY):
                return self._err("unauthorized", 401)
            return self._serve_stream()

        if not self._auth_ok():
            return self._err("unauthorized", 401)

        if u.path == "/stats":
            yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            return self._ok({
                "mode": BOT.MODE,
                "bankroll": BOT.PAPER_BANKROLL,
                "open_positions": len(db.open_positions()),
                "all_time": db.stats(),
                "last_24h": db.stats(since_iso=yesterday),
                "last_7d": db.stats(since_iso=week_ago),
                "ts": datetime.now(timezone.utc).isoformat(),
            })

        if u.path == "/positions":
            qs = parse_qs(u.query)
            status = (qs.get("status") or ["OPEN"])[0]
            limit = int((qs.get("limit") or ["100"])[0])
            with db.connect() as conn:
                if status == "ALL":
                    rows = conn.execute(
                        "SELECT * FROM positions ORDER BY opened_at DESC LIMIT ?",
                        (limit,)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM positions WHERE status = ? "
                        "ORDER BY opened_at DESC LIMIT ?",
                        (status, limit)
                    ).fetchall()
            return self._ok({"positions": [_row(r) for r in rows]})

        if u.path == "/scans":
            limit = int((parse_qs(u.query).get("limit") or ["50"])[0])
            with db.connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return self._ok({"scans": [_row(r) for r in rows]})

        if u.path == "/skips":
            with db.connect() as conn:
                rows = conn.execute("""
                    SELECT skip_reason, COUNT(*) AS n,
                           AVG(market_price) AS avg_price
                    FROM skipped
                    WHERE scanned_at >= datetime('now', '-24 hours')
                    GROUP BY skip_reason
                    ORDER BY n DESC LIMIT 20
                """).fetchall()
            return self._ok({"skips_24h": [_row(r) for r in rows]})

        if u.path == "/equity":
            # Equity curve: cumulative P&L over time, using closed positions.
            with db.connect() as conn:
                rows = conn.execute("""
                    SELECT closed_at, pnl_usd FROM positions
                    WHERE status != 'OPEN' AND closed_at IS NOT NULL
                    ORDER BY closed_at
                """).fetchall()
            cum = 0.0
            curve = []
            for r in rows:
                cum += r["pnl_usd"] or 0.0
                curve.append({"t": r["closed_at"], "cum_pnl": round(cum, 2)})
            return self._ok({"equity_curve": curve, "starting": BOT.PAPER_BANKROLL})

        if u.path == "/config":
            # Read-only view of operational parameters
            return self._ok({
                "mode": BOT.MODE,
                "bankroll": BOT.PAPER_BANKROLL,
                "scan_interval_seconds": BOT.SCAN_INTERVAL_SECONDS,
                "risk": {
                    "price_min": RISK.PRICE_MIN,
                    "price_max": RISK.PRICE_MAX,
                    "hours_min": RISK.HOURS_TO_RESOLUTION_MIN,
                    "hours_max": RISK.HOURS_TO_RESOLUTION_MAX,
                    "volume_min": RISK.VOLUME_24H_MIN,
                    "max_concurrent": RISK.MAX_CONCURRENT_POSITIONS,
                    "position_cap_usd": RISK.POSITION_DOLLAR_CAP,
                    "stop_loss_price": RISK.STOP_LOSS_PRICE,
                    "kelly_fraction": RISK.KELLY_FRACTION,
                },
            })

        return self._err("not found", 404)

    def _serve_stream(self):
        """Server-Sent Events stream — pushes bot events live to dashboard."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Accel-Buffering", "no")  # disable nginx buffering
        self.end_headers()
        try:
            # Send a hello so the client immediately knows it's connected
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            for evt in BUS.subscribe():
                payload = json.dumps(evt, default=str)
                line = f"event: {evt['kind']}\ndata: {payload}\n\n"
                try:
                    self.wfile.write(line.encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
        except Exception:
            return


def serve_in_thread() -> threading.Thread:
    _ensure_api_key()
    httpd = ThreadingHTTPServer(("0.0.0.0", API_PORT), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True, name="api")
    t.start()
    return t
