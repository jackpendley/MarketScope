"""Minimal OddsPapi client for the lake: responses stream to disk, so their size never matters.
The key travels in the query string, so URLs are never logged and errors are redacted."""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.oddspapi.io"
COOLDOWN = {"/v4/historical-odds": 5.0, "/v4/fixtures": 2.0, "/v4/markets": 1.0}
NFL_TOURNAMENT = 31


class OddsPapiError(RuntimeError):
    pass


class Client:
    def __init__(self, api_key: str):
        self.key = api_key
        self.last: dict[str, float] = {}

    def _open(self, path: str, params: dict):
        wait = self.last.get(path, 0) + COOLDOWN.get(path, 1.0) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last[path] = time.monotonic()
        url = f"{BASE}{path}?{urllib.parse.urlencode({**params, 'apiKey': self.key})}"
        for attempt in range(3):
            try:
                return urllib.request.urlopen(url, timeout=600)
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:200].replace(self.key, "[REDACTED]")
                if e.code == 429 and "REQUEST_LIMIT_EXCEEDED" not in body and attempt < 2:
                    time.sleep(COOLDOWN.get(path, 1.0) * 2)
                    continue
                raise OddsPapiError(f"GET {path} failed: HTTP {e.code} {body}") from None
            except urllib.error.URLError:
                if attempt == 2:
                    raise OddsPapiError(f"GET {path} failed: network error") from None
        raise OddsPapiError(f"GET {path} failed after retries")

    def historical_to_file(self, fixture_id: str, bookmakers: list[str], dest: Path) -> Path:
        """Free endpoint. Streams the response to `dest` (atomic rename when complete)."""
        tmp = dest.with_suffix(".part")
        with self._open("/v4/historical-odds", {"fixtureId": fixture_id, "bookmakers": ",".join(bookmakers)}) as r, \
                open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, length=1 << 20)
        tmp.replace(dest)
        return dest

    def fixtures(self, frm: str, to: str, status_id: int = 2) -> list[dict]:
        """Billable (1 request)."""
        with self._open("/v4/fixtures", {"tournamentId": NFL_TOURNAMENT, "statusId": status_id,
                                         "from": frm, "to": to}) as r:
            return json.loads(r.read())

    def markets(self) -> list[dict]:
        """Billable (1 request)."""
        with self._open("/v4/markets", {}) as r:
            return json.loads(r.read())
