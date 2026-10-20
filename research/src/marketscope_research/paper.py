"""Paper portfolio job (MS-045b, ADR-056): place and grade hypothetical positions.

This is the one research module that writes, and it writes only `paper_positions`. Studies stay
read-only (data.connect). Every position is hypothetical: nothing is wagered.

    PAPER_DATABASE_URL=... python -m marketscope_research.paper place        # live, before kickoff
    PAPER_DATABASE_URL=... python -m marketscope_research.paper reconstruct  # finished games, from stored snapshots
    PAPER_DATABASE_URL=... python -m marketscope_research.paper grade        # results, close and CLV

Rules are the pre-registered systems (Addenda E and F) from systems.py, applied to a real book's
posted line instead of the nflverse close: Caesars (williamhill_us), else DraftKings.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import psycopg

from . import systems as sy
from .data import _frame
from .run_catalogue import SIDE_FIELDS, attach_context
from .sharp_market import clv

BOOKS = ("williamhill_us", "draftkings")  # preference order
MIN_LEAD = timedelta(minutes=10)  # a quote must be at least this far before kickoff
LIVE_WINDOW = timedelta(hours=6, minutes=10)  # live placement covers games kicking off this soon


def connect_writer(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, connect_timeout=15, prepare_threshold=None)


def load_season_games(conn, season: int) -> pd.DataFrame:
    """Every game of a season (final or not) with situational fields and its odds event."""
    g = _frame(conn, """
        SELECT g.game_id, g.season, g.week, g.kickoff_utc AS kickoff, g.home_team AS home, g.away_team AS away,
               g.neutral_site AS neutral, g.division_game AS division,
               coalesce(g.event_id, (
                 SELECT e.id FROM events e
                 JOIN nfl_teams ht ON ht.odds_api_name = e.home_team AND ht.abbr = g.home_team
                 JOIN nfl_teams at ON at.odds_api_name = e.away_team AND at.abbr = g.away_team
                 WHERE abs(extract(epoch FROM e.commence_time_utc - g.kickoff_utc)) < 6 * 3600 LIMIT 1
               ))::text AS event_id,
               (g.home_score - g.away_score)::float8 AS margin, (g.home_score + g.away_score)::float8 AS points,
               g.nflverse_close_home_spread::float8 AS nflverse_home_line, g.nflverse_close_total::float8 AS nflverse_total,
               extract(hour FROM g.kickoff_utc AT TIME ZONE 'America/New_York')::int AS et_hour
        FROM nfl_games g WHERE g.season = %s""", (season,))
    ctx = _frame(conn, f"SELECT game_id, team, {', '.join(SIDE_FIELDS)} FROM nfl_game_context WHERE season = %s",
                 (season,))
    g = attach_context(g, ctx.rename(columns=SIDE_FIELDS))
    g["kickoff"] = pd.to_datetime(g["kickoff"], utc=True)
    return g


def load_quotes(conn, event_ids: list[str]) -> pd.DataFrame:
    q = _frame(conn, """
        SELECT event_id::text, bookmaker_key, market_type, selection, point::float8 AS point,
               american_price AS price, observed_at
        FROM odds_observations
        WHERE event_id = ANY(%s::uuid[]) AND NOT is_live AND market_type IN ('spreads', 'totals')
          AND bookmaker_key = ANY(%s)""", (event_ids, list(BOOKS)))
    q["observed_at"] = pd.to_datetime(q["observed_at"], utc=True)
    return q


def book_line(quotes: pd.DataFrame, event_id: str, cutoff: pd.Timestamp) -> dict | None:
    """The preferred book's latest snapshot at or before `cutoff` with both a spread and a total."""
    q = quotes[(quotes["event_id"] == event_id) & (quotes["observed_at"] <= cutoff)]
    for book in BOOKS:
        b = q[q["bookmaker_key"] == book]
        if b.empty:
            continue
        at = b["observed_at"].max()
        snap = b[b["observed_at"] == at].set_index(["market_type", "selection"])
        need = [("spreads", "HOME"), ("spreads", "AWAY"), ("totals", "OVER"), ("totals", "UNDER")]
        if not all(k in snap.index for k in need):
            continue
        return {"book": book, "observed_at": at,
                "home_line": float(snap.loc[("spreads", "HOME"), "point"]),
                "home_price": int(snap.loc[("spreads", "HOME"), "price"]),
                "away_price": int(snap.loc[("spreads", "AWAY"), "price"]),
                "total": float(snap.loc[("totals", "OVER"), "point"]),
                "under_price": int(snap.loc[("totals", "UNDER"), "price"])}
    return None


def selections(games: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Every strategy's positions for games already carrying a book line (home_line, total)."""
    upcoming = games.assign(margin=np.nan, points=np.nan)
    out = []
    for v in sy.VARIANTS:
        legs = sy.wong_legs(upcoming, v)
        out.append(pd.DataFrame({"strategy": f"wong-{v}", "game_id": legs["game_id"], "market": "teaser_leg",
                                 "side": legs["team"], "line": legs["line"], "teased_line": legs["teased"]}))
    rules = pd.concat([sy.rule_positions(upcoming), sy.f10_select(history, upcoming)], ignore_index=True)
    out.append(pd.DataFrame({"strategy": rules["system"], "game_id": rules["game_id"], "market": rules["market"],
                             "side": rules["side"], "line": rules["line"], "teased_line": np.nan}))
    return pd.concat(out, ignore_index=True)


def place(conn, season: int, mode: str, now: datetime) -> int:
    from .run_catalogue import load_games

    games = load_season_games(conn, season)
    if mode == "live":
        todo = games[(games["kickoff"] > now + MIN_LEAD) & (games["kickoff"] <= now + LIVE_WINDOW)
                     & games["margin"].isna()]
    else:
        todo = games[games["margin"].notna() & (games["kickoff"] < now)]
    todo = todo[todo["event_id"].notna()]
    if todo.empty:
        return 0
    quotes = load_quotes(conn, list(todo["event_id"]))
    lines = []
    for g in todo.itertuples():
        cutoff = min(pd.Timestamp(now), g.kickoff - MIN_LEAD)
        b = book_line(quotes, g.event_id, cutoff)
        if b:
            lines.append({"game_id": g.game_id, **b})
    if not lines:
        return 0
    lines = pd.DataFrame(lines)
    priced = todo.drop(columns=["margin", "points"]).merge(lines, on="game_id")
    history = load_games(conn, (2016, season - 1))
    sel = selections(priced, history).merge(priced[["game_id", "season", "week", "kickoff", "home", "book",
                                                    "observed_at", "home_price", "away_price", "under_price"]],
                                            on="game_id")
    sel["price"] = np.where(sel["market"] == "teaser_leg", np.nan,
                            np.where(sel["market"] == "total", sel["under_price"],
                                     np.where(sel["side"] == sel["home"], sel["home_price"], sel["away_price"])))
    placed_at = now if mode == "live" else datetime.now(timezone.utc)
    rows = [(r.strategy, mode, r.game_id, int(r.season), int(r.week), r.kickoff.to_pydatetime(), r.market, r.side,
             float(r.line), None if pd.isna(r.teased_line) else float(r.teased_line),
             None if pd.isna(r.price) else int(r.price), r.book, r.observed_at.to_pydatetime(), placed_at)
            for r in sel.itertuples()]
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO paper_positions (strategy, mode, game_id, season, week, kickoff_utc, market, side, line,
                                         teased_line, price, bookmaker_key, quote_observed_at, placed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (strategy, game_id, mode) DO NOTHING""", rows)
        inserted = cur.rowcount
    conn.commit()
    return inserted


def grade_one(market: str, side: str, line: float, teased: float | None, home: str, margin: float,
              points: float) -> str:
    if market == "total":
        v = (line - points) if side == "under" else (points - line)
    else:
        team_margin = margin if side == home else -margin
        v = team_margin + (teased if market == "teaser_leg" else line)
    return "win" if v > 0 else "push" if v == 0 else "loss"


def pinnacle_closes(conn, event_ids: list[str]) -> pd.DataFrame:
    """Pinnacle's latest available main line before kickoff, per event and market (line_moves)."""
    return _frame(conn, """
        SELECT DISTINCT ON (m.event_id, m.market_type) m.event_id::text, m.market_type, m.point::float8 AS point
        FROM line_moves m JOIN events e ON e.id = m.event_id
        WHERE m.event_id = ANY(%s::uuid[]) AND m.bookmaker_key = 'pinnacle' AND m.price1 IS NOT NULL
          AND m.market_type IN ('spreads', 'totals') AND m.changed_at < e.commence_time_utc
        ORDER BY m.event_id, m.market_type, m.changed_at DESC""", (event_ids,))


def grade(conn, season: int) -> int:
    games = load_season_games(conn, season)
    open_ = _frame(conn, """SELECT id, game_id, market, side, line::float8 AS line, teased_line::float8 AS teased
                           FROM paper_positions WHERE season = %s AND result IS NULL""", (season,))
    m = open_.merge(games[games["margin"].notna()], on="game_id")
    if m.empty:
        return 0
    closes = pinnacle_closes(conn, [e for e in m["event_id"].dropna().unique()])
    close_map = {(r.event_id, r.market_type): r.point for r in closes.itertuples()}
    updates = []
    for r in m.itertuples():
        result = grade_one(r.market, r.side, r.line, None if pd.isna(r.teased) else r.teased, r.home, r.margin,
                           r.points)
        key = "totals" if r.market == "total" else "spreads"
        home_close, source = close_map.get((r.event_id, key)), "pinnacle"
        if home_close is None:
            home_close = r.nflverse_total if key == "totals" else r.nflverse_home_line
            source = "nflverse"
        close_line = clv_value = None
        if home_close is not None and not pd.isna(home_close):
            if key == "totals":
                close_line = float(home_close)
                clv_value = clv(r.side, r.line, close_line)
            else:
                close_line = float(home_close if r.side == r.home else -home_close)
                clv_value = float(r.line - close_line)  # more points for the side = positive
        updates.append((result, close_line, source if close_line is not None else None, clv_value, int(r.id)))
    with conn.cursor() as cur:
        cur.executemany("""UPDATE paper_positions SET result = %s, close_line = %s, close_source = %s, clv = %s,
                           graded_at = now() WHERE id = %s""", updates)
    conn.commit()
    return len(updates)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["place", "reconstruct", "grade"])
    ap.add_argument("--season", type=int, default=2026)
    args = ap.parse_args()
    dsn = os.environ.get("PAPER_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set PAPER_DATABASE_URL (writes paper_positions only).")
    now = datetime.now(timezone.utc)
    with connect_writer(dsn) as conn:
        if args.command == "grade":
            print(f"graded {grade(conn, args.season)} positions")
        else:
            mode = "live" if args.command == "place" else "reconstructed"
            print(f"placed {place(conn, args.season, mode, now)} {mode} positions")


if __name__ == "__main__":
    main()
