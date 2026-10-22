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


def one_outcome(*entries):
    """A response with a single main-market outcome at Pinnacle."""
    body = {"bookmakers": {"pinnacle": {"markets": {"100": {"outcomes": {"100": {"players": {"0": list(entries)}}}}}}}}
    return list(stream_entries(io.BytesIO(json.dumps(body).encode()), {100}, KICK))


def test_kickoff_is_compared_as_an_instant_not_as_text():
    # "2026-10-11T16:30:00-01:00" sorts before the kickoff text but is 17:30Z: in-play, excluded
    got = one_outcome(entry("2026-10-11T16:00:00.000Z", 1.90), entry("2026-10-11T16:30:00-01:00", 1.80))
    assert [e.price for e in got] == [1.90]


def test_offset_entries_before_kickoff_are_kept_and_at_kickoff_dropped():
    got = one_outcome(entry("2026-10-11T17:30:00+01:00", 1.90),    # 16:30Z: before kickoff, kept
                      entry("2026-10-11T17:00:00.000Z", 1.80),     # exactly kickoff: dropped
                      entry("2026-10-11T17:00:00+00:00", 1.70))    # same instant, other spelling: dropped
    assert [(e.created_at, e.price) for e in got] == [("2026-10-11T17:30:00+01:00", 1.90)]


def test_kickoff_with_an_offset_is_the_same_instant():
    body = {"bookmakers": {"pinnacle": {"markets": {"100": {"outcomes": {"100": {"players": {"0": [
        entry("2026-10-11T16:59:59.999Z", 1.9), entry("2026-10-11T17:00:00.000Z", 1.8)]}}}}}}}}
    got = list(stream_entries(io.BytesIO(json.dumps(body).encode()), {100}, "2026-10-11T18:00:00+01:00"))
    assert [e.price for e in got] == [1.9]


def test_timestamps_without_a_zone_are_rejected():
    with pytest.raises(ValueError, match="without a time zone"):
        one_outcome(entry("2026-10-11T16:30:00", 1.9))
    with pytest.raises(ValueError, match="without a time zone"):
        list(stream_entries(io.BytesIO(b'{"bookmakers": {}}'), {100}, "2026-10-11T17:00:00"))
    with pytest.raises(ValueError, match="unparseable"):
        one_outcome(entry("yesterday", 1.9))


def test_an_outcome_going_back_in_time_fails_the_fixture():
    with pytest.raises(ValueError, match="out of time order"):
        one_outcome(entry("2026-10-10T09:00:00.000Z", 1.9), entry("2026-10-10T08:00:00.000Z", 1.8))


def test_suspensions_and_reopenings_survive_deduplication():
    got = one_outcome(entry("2026-10-10T08:00:00.000Z", 1.9), entry("2026-10-10T09:00:00.000Z", 1.9, a=False),
                      entry("2026-10-10T09:30:00.000Z", 1.9, a=False), entry("2026-10-10T10:00:00.000Z", 1.9))
    assert [(e.created_at[11:16], e.active) for e in got] == [("08:00", True), ("09:00", False), ("10:00", True)]


def test_ties_keep_provider_order_after_storage(tmp_path):
    got = one_outcome(entry("2026-10-10T08:00:00.000Z", 1.9), entry("2026-10-10T08:00:00.000Z", 2.1),
                      entry("2026-10-10T08:00:00.000Z", 2.0))
    assert [e.seq for e in got] == [1, 2, 3]
    store.write_fixture("t", got, tmp_path)
    t = pd.read_parquet(tmp_path / "entries" / "fixture=t.parquet")
    assert t["price"].tolist() == [1.9, 2.1, 2.0]  # the last of the tie is the price in effect


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


def test_ghost_rule_matches_the_collector_cases():
    """Mirrors transform.test.ts withoutGhosts (MS-058, ADR-065)."""
    t = pd.Timestamp("2026-10-18T16:00Z")

    def hs(*rows):
        lad = ladder(*[r for k, (h, p1, p2, at, *act) in enumerate(rows) for r in (
            (300 + k, "spreads", h, "1", at, p1, act[0] if act else True, None),
            (300 + k, "spreads", h, "2", at, p2, act[0] if act else True, None))])
        return sorted(c.handicap for c in mainline.without_ghosts(mainline.candidates(lad, "spreads"), t))

    # Caesars' -10 ghost beside its real -7.
    assert hs((-10, 1.87, 1.87, "2026-09-01T02:24:00Z"), (-7, 1.909, 1.926, "2026-10-18T13:30:00Z")) == [-7]
    # A real main line unchanged for days beside repriced alternates is kept; a far alternate is not near even.
    assert hs((1.5, 1.82, 2.0, "2026-10-13T10:59:00Z"), (-1.5, 2.02, 1.77, "2026-10-17T22:17:00Z"),
              (-6.5, 3.4, 1.3, "2026-10-17T14:45:00Z")) == [-1.5, 1.5]
    # Far tails, junk margins and suspended markets: no main line.
    assert hs((14.5, 13.4, 1.01, "2026-10-15T17:07:00Z"), (25, 1.077, 1.286, "2026-10-18T15:00:00Z"),
              (3.5, 1.893, 1.926, "2026-10-18T04:14:00Z", False)) == []
    # Direction is ignored; adjacent half points at equal prices are kept.
    assert hs((-3.5, 1.95, 1.87, "2026-09-02T09:02:00Z"), (-5.5, 1.74, 2.06, "2026-09-02T10:10:00Z")) == [-5.5, -3.5]
    assert hs((-6.5, 1.909, 1.909, "2026-10-17T10:00:00Z"), (-7, 1.909, 1.909, "2026-10-18T10:00:00Z")) == [-7, -6.5]


def test_ghost_rule_in_the_timeline():
    cands = mainline.candidates(ghost_ladder(), "spreads")
    kick = pd.Timestamp("2026-10-18T17:00Z")
    registered = mainline.timeline(cands, "spreads", kick, False)
    fixed = mainline.timeline(cands, "spreads", kick, False, ghost_rule=True)
    assert registered[-1]["point"] == -10
    assert fixed[-1]["point"] == -7
