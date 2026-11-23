"""Append-only, hash-chained event ledger.

Every decision, fill, risk action, data problem and code version is written as
one JSON line. Each line includes the SHA-256 of the previous line, so any
after-the-fact edit breaks the chain and `verify()` detects it. The ledger is
committed to git after each run, which gives a second, timestamped audit trail.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def events(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open() as f:
            return [json.loads(line) for line in f if line.strip()]

    def _last(self) -> tuple[int, str]:
        ev = self.events()
        return (ev[-1]["seq"], ev[-1]["hash"]) if ev else (0, GENESIS)

    def append(self, type_: str, data: dict) -> dict:
        seq, prev = self._last()
        body = {"seq": seq + 1, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "type": type_, "data": data, "prev_hash": prev}
        body["hash"] = hashlib.sha256(_canon(body).encode()).hexdigest()
        with self.path.open("a") as f:
            f.write(_canon(body) + "\n")
        return body

    def verify(self) -> tuple[bool, str]:
        prev = GENESIS
        for i, ev in enumerate(self.events(), start=1):
            h = ev.get("hash")
            body = {k: v for k, v in ev.items() if k != "hash"}
            if ev.get("seq") != i:
                return False, f"sequence break at line {i}"
            if body.get("prev_hash") != prev:
                return False, f"chain break at seq {i}"
            if hashlib.sha256(_canon(body).encode()).hexdigest() != h:
                return False, f"content altered at seq {i}"
            prev = h
        return True, "ok"
