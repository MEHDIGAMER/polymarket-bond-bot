"""Tiny in-memory event bus. Trader/resolver publish; SSE handler subscribes.

No deps — just a thread-safe deque + a Condition. The SSE handler holds a
queue per connected client and the bus fans out to all of them.
"""
from collections import deque
from threading import Lock, Condition
from typing import Iterator
import json
import time


class EventBus:
    def __init__(self):
        self._subs: list[deque] = []
        self._lock = Lock()
        self._cond = Condition(self._lock)
        self._counter = 0

    def publish(self, kind: str, data: dict) -> None:
        evt = {"id": self._next_id(), "kind": kind, "data": data,
               "ts": time.time()}
        with self._cond:
            for q in self._subs:
                q.append(evt)
                # Cap each subscriber's queue so a slow client can't OOM us.
                while len(q) > 1024:
                    q.popleft()
            self._cond.notify_all()

    def subscribe(self) -> Iterator[dict]:
        """Generator yielding events. Caller closes via GeneratorExit."""
        q: deque = deque()
        with self._cond:
            self._subs.append(q)
        try:
            while True:
                with self._cond:
                    while not q:
                        # 30s wait so we can yield heartbeat and let the
                        # client check "is the connection alive".
                        self._cond.wait(timeout=30)
                        if not q:
                            yield {"kind": "heartbeat", "data": {}, "ts": time.time()}
                            continue
                    evt = q.popleft()
                yield evt
        finally:
            with self._cond:
                if q in self._subs:
                    self._subs.remove(q)

    def _next_id(self) -> int:
        self._counter += 1
        return self._counter


# Singleton — imported by trader, resolver, api
BUS = EventBus()


def emit_position_opened(pos: dict) -> None:
    BUS.publish("position_opened", {
        "id": pos.get("id"),
        "side": pos.get("side"),
        "question": pos.get("question") or pos.get("market_question"),
        "entry_price": pos.get("entry_price"),
        "size_usd": pos.get("size_usd"),
        "category": pos.get("category"),
    })


def emit_position_closed(closed: dict) -> None:
    BUS.publish("position_closed", {
        "id": closed.get("id"),
        "question": closed.get("question") or closed.get("market_question"),
        "side": closed.get("side"),
        "entry": closed.get("entry"),
        "exit": closed.get("exit"),
        "pnl": closed.get("pnl"),
        "status": closed.get("status"),
    })


def emit_scan_complete(result: dict) -> None:
    BUS.publish("scan_complete", {
        "markets_seen": result.get("markets_seen"),
        "candidates": result.get("candidates"),
        "opened": len(result.get("opened") or []),
    })
