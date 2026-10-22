"""MS-052 research lake: streaming parse, storage, the main-line port."""

import io
import json

import pandas as pd
import pytest

from marketscope_research.lake import check, mainline, store
from marketscope_research.lake.parse import split_path, stream_entries

KICK = "2026-10-11T17:00:00.000Z"


def entry(t, p, a=True, limit=None):
    return {"createdAt": t, "price": p, "active": a, "limit": limit, "exchangeMeta": None}


def response():
    return {"fixtureId": "f", "bookmakers": {
        "bookmaker.eu": {"markets": {
            "100": {"outcomes": {
                "100": {"players": {"0": [entry("2026-10-10T08:00:00.000Z", 1.91, limit=500),
                                          entry("2026-10-10T09:00:00.000Z", 1.91, limit=500),   # unchanged: dropped
                                          entry("2026-10-10T10:00:00.000Z", 1.91, limit=900),   # limit change kept
                                          entry("2026-10-11T17:30:00.000Z", 1.5)]}},            # in-play: dropped
                "101": {"players": {"0": [entry("2026-10-10T08:00:00.000Z", 1.91)]}}}},
            "999": {"outcomes": {"999": {"players": {"0": [entry("2026-10-10T08:00:00.000Z", 2.0)]}}}}}},  # not main
        "draftkings": {"markets": {"100": {"outcomes": {
            "100": {"players": {"0": [entry("2026-10-10T08:00:00.000Z", 1.91, limit=10),
                                      entry("2026-10-10T09:00:00.000Z", 1.91, limit=20)]}}}}}},  # retail: limit ignored
    }}


def parsed():
    return list(stream_entries(io.BytesIO(json.dumps(response()).encode()), {100}, KICK))


def test_split_path_handles_dotted_book_slugs():
    assert split_path("bookmakers.novig.us.markets.141.outcomes.142.players.0.item") == ("novig.us", "141", "142")


def test_stream_entries_filters_and_dedupes():
    got = [(e.book, e.outcome_id, e.created_at[11:16], e.limit) for e in parsed()]
    assert got == [("bookmaker.eu", 100, "08:00", 500.0), ("bookmaker.eu", 100, "10:00", 900.0),
                   ("bookmaker.eu", 101, "08:00", None), ("draftkings", 100, "08:00", 10.0)]


def test_store_round_trip_and_views(tmp_path):
    catalog = [{"marketId": 100, "sportId": 14, "marketType": "spreads", "handicap": -3, "period": "result",
                "playerProp": False, "outcomes": [{"outcomeId": 100, "outcomeName": "1"},
                                                  {"outcomeId": 101, "outcomeName": "2"}]},
               {"marketId": 500, "sportId": 14, "marketType": "spreads", "handicap": -1, "period": "p1",
                "playerProp": False, "outcomes": [{"outcomeId": 500, "outcomeName": "1"}]}]
    markets = store.main_market_rows(catalog)
    assert set(markets["market_id"]) == {100}
    store.write_markets(markets, tmp_path)
    assert store.write_fixture("f1", parsed(), tmp_path) == 4
    store.record_fixture({"fixture_id": "f1", "event_id": "e1", "kickoff": KICK, "home": "H", "away": "A",
                          "rows": 4, "books": "x"}, tmp_path)
    store.record_fixture({"fixture_id": "f1", "event_id": "e1", "kickoff": KICK, "home": "H", "away": "A",
                          "rows": 4, "books": "x"}, tmp_path)  # upsert, not duplicate
    con = store.connect(tmp_path)
    assert con.execute("SELECT count(*) FROM manifest").fetchone()[0] == 1
    lad = con.execute("SELECT fixture_id, book, market_type, outcome_name, handicap FROM ladder ORDER BY book").df()
    assert lad["fixture_id"].unique().tolist() == ["f1"]
    times = con.execute("SELECT created_at FROM entries ORDER BY created_at").df()["created_at"]
    assert times.notna().all() and str(times.iloc[0])[:16] == "2026-10-10 08:00"
    assert set(lad["outcome_name"]) == {"1", "2"} and lad["handicap"].eq(-3).all()


def test_js_rounding_matches_typescript():
    assert mainline.to_american(1.909) == -110 and mainline.to_american(2.5) == 150
    assert mainline.js_round(-2.5) == -2 and mainline.js_round(2.5) == 3


def ladder(*rows):
    df = pd.DataFrame(rows, columns=["market_id", "market_type", "handicap", "outcome_name", "created_at", "price",
                                     "active", "limit"])
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True, format="ISO8601")
    return df


K = pd.Timestamp(KICK)


def test_main_line_switch_settles_after_a_burst():
    # Mirrors line-moves.test.ts: -3 is main; the book moves to -3.5 with alternate lines rewritten
    # 200 ms apart, which must be one change recorded when the burst ends.
    lad = ladder(
        (100, "spreads", -3, "1", "2026-10-09T10:00:00Z", 1.91, True, None),
        (100, "spreads", -3, "2", "2026-10-09T10:00:00Z", 1.91, True, None),
        (100, "spreads", -3, "1", "2026-10-10T12:00:00.000Z", 1.67, True, None),
        (100, "spreads", -3, "2", "2026-10-10T12:00:00.000Z", 2.25, True, None),
        (110, "spreads", -3.5, "1", "2026-10-09T10:00:00Z", 2.2, True, None),
        (110, "spreads", -3.5, "2", "2026-10-09T10:00:00Z", 1.7, True, None),
        (110, "spreads", -3.5, "1", "2026-10-10T12:00:00.200Z", 1.909, True, None),
        (110, "spreads", -3.5, "2", "2026-10-10T12:00:00.200Z", 1.909, True, None),
    )
    d = mainline.derive(lad, K)
    assert d[["point", "price1", "price2"]].values.tolist() == [[-3.0, -110, -110], [-3.5, -110, -110]]
    assert d["changed_at"].iloc[1] == pd.Timestamp("2026-10-10T12:00:00.200Z")


def test_suspensions_and_blips():
    rows = []
    for name, p in (("Over", 1.952), ("Under", 1.87)):
        rows += [(200, "totals", 44.5, name, "2026-10-09T10:00:00Z", p, True, None),
                 (200, "totals", 44.5, name, "2026-10-10T08:00:00Z", p, False, None),
                 (200, "totals", 44.5, name, "2026-10-10T08:00:20Z", p, True, None),
                 (200, "totals", 44.5, name, "2026-10-11T09:00:00Z", p, False, None),
                 (200, "totals", 44.5, name, "2026-10-11T09:10:00Z", p, True, None)]
    d = mainline.derive(ladder(*rows), K)
    assert [None if pd.isna(x) else x for x in d["price1"]] == [-105, None, -105]


def test_grid_compare_ignores_settle_timing():
    a = pd.DataFrame({"changed_at": pd.to_datetime(["2026-10-09T10:00:00Z", "2026-10-10T12:00:00.2Z"], utc=True, format="ISO8601"),
                      "point": [-3.0, -3.5], "price1": [-110, -110], "price2": [-110, -110]})
    b = a.assign(changed_at=pd.to_datetime(["2026-10-09T10:00:00Z", "2026-10-10T12:00:01Z"], utc=True, format="ISO8601"))
    m, c = check.compare(a, b, K)
    assert c > 0 and m == c
    worse = b.assign(price1=[-110, -120])
    m2, c2 = check.compare(a, worse, K)
    assert m2 < c2


def ghost_ladder():
    # Caesars-style ghost: -10 last updated weeks ago at -115/-115, still active; the real -7 is fresher.
    return ladder(
        (100, "spreads", -10, "1", "2026-09-01T02:00:00Z", 1.87, True, None),
        (100, "spreads", -10, "2", "2026-09-01T02:00:00Z", 1.87, True, None),
        (110, "spreads", -7, "1", "2026-10-18T13:00:00Z", 1.909, True, None),
        (110, "spreads", -7, "2", "2026-10-18T13:00:00Z", 1.926, True, None),
        (120, "spreads", -7.5, "1", "2026-10-18T13:00:00Z", 2.0, True, None),
        (120, "spreads", -7.5, "2", "2026-10-18T13:00:00Z", 1.83, True, None),
    )


def test_coherence_rule_drops_a_ghost_main_line():
    cands = mainline.candidates(ghost_ladder(), "spreads")
    t = pd.Timestamp("2026-10-18T16:00Z")
    assert mainline.pick_main(cands, t)[1].handicap == -10  # the registered rule picks the ghost
    kept = mainline.coherent(cands, t, "spreads")
    assert sorted(c.handicap for c in kept) == [-7.5, -7]
    assert mainline.pick_main(kept, t)[1].handicap == -7


def test_coherence_rule_keeps_a_monotone_ladder_and_ties():
    lad = ladder(
        (200, "totals", 44, "Over", "2026-10-10T10:00:00Z", 1.909, True, None),
        (200, "totals", 44, "Under", "2026-10-10T10:00:00Z", 1.909, True, None),
        (210, "totals", 47, "Over", "2026-10-01T10:00:00Z", 2.4, True, None),   # older, coherent: P(over) lower
        (210, "totals", 47, "Under", "2026-10-01T10:00:00Z", 1.57, True, None),
        (220, "totals", 44.5, "Over", "2026-10-02T10:00:00Z", 1.909, True, None),  # tie with 44: allowed
        (220, "totals", 44.5, "Under", "2026-10-02T10:00:00Z", 1.909, True, None),
        (230, "totals", 41, "Over", "2026-09-01T10:00:00Z", 2.2, True, None),   # stale, P(over 41) < P(over 44)
        (230, "totals", 41, "Under", "2026-09-01T10:00:00Z", 1.7, True, None),
    )
    cands = mainline.candidates(lad, "totals")
    kept = mainline.coherent(cands, pd.Timestamp("2026-10-18T16:00Z"), "totals")
    assert sorted(c.handicap for c in kept) == [44, 44.5, 47]
