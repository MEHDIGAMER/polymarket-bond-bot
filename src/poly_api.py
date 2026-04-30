"""Polymarket Gamma API client. Reads only — no order placement here."""
import json
import time
import urllib.request
import urllib.error
from typing import Any

from .config import BOT


class PolyAPIError(RuntimeError):
    pass


def _get(path: str, params: dict[str, Any] | None = None,
         retries: int = 3) -> Any:
    qs = ""
    if params:
        qs = "?" + "&".join(
            f"{k}={v}" for k, v in params.items() if v is not None
        )
    url = f"{BOT.GAMMA_API_BASE}{path}{qs}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "polymarket-bond-bot/0.1",
        "Accept": "application/json",
    })
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise PolyAPIError(f"GET {url} failed after {retries}: {last_err}")


def list_active_markets(limit: int = 500, offset: int = 0) -> list[dict]:
    """Pull active, non-closed markets ordered by 24h volume."""
    return _get("/markets", {
        "active": "true",
        "closed": "false",
        "order": "volume24hr",
        "ascending": "false",
        "limit": limit,
        "offset": offset,
    }) or []


def get_market(condition_id: str) -> dict | None:
    """Fetch a single market by conditionId — used by resolver."""
    try:
        return _get(f"/markets/{condition_id}")
    except PolyAPIError:
        return None


def is_resolved(market: dict) -> tuple[bool, str | None]:
    """Returns (is_resolved, winning_outcome). Winning_outcome = 'YES' or 'NO'."""
    if not market.get("closed"):
        return False, None
    # Polymarket sets one outcomePrice to '1' and the other to '0' on resolution.
    raw = market.get("outcomePrices")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return True, None
    if isinstance(raw, list) and len(raw) >= 2:
        yes, no = float(raw[0]), float(raw[1])
        if yes >= 0.99:
            return True, "YES"
        if no >= 0.99:
            return True, "NO"
    return True, None
