"""MS-043 sharp-market study: planted signals, leakage and the pre-registered edge rules."""

import numpy as np
import pandas as pd
import pytest

from marketscope_research import sharp_market as sm

KICK = pd.Timestamp("2026-10-18T17:00:00Z")


def ts(hhmm: str, day: int = 18) -> pd.Timestamp:
    return pd.Timestamp(f"2026-10-{day:02d}T{hhmm}:00Z")


def rows(event: str, book: str, *moves):
    """moves: (time, point or None for off, price1, price2[, limit])."""
    out = []
    for m in moves:
        t, point, p1, p2 = m[:4]
        out.append({"event_id": event, "bookmaker_key": book, "changed_at": t,
                    "point": point, "price1": p1, "price2": p2, "limit1": m[4] if len(m) > 4 else None})
    return out


def frame(*groups):
    return pd.DataFrame([r for g in groups for r in g])


def test_line_at_never_looks_past_the_decision_time():
    tl = sm.timelines(frame(rows("g", "draftkings", (ts("10:00"), -3, -110, -110),
                                 (ts("10:00") + pd.Timedelta(seconds=61), -3.5, -110, -110))))
    book = tl["g"]["draftkings"]
    assert book.at(ts("10:00") + sm.DECISION_DELAY).point == -3
    assert book.at(ts("09:59")) is None


def test_close_is_last_available_pinnacle_line_unless_off_for_30_minutes():
    on = sm.Book(pd.DataFrame(rows("g", "pinnacle", (ts("10:00"), -3, -110, -110),
                                   (ts("16:45"), None, None, None))))
    assert sm.close_line(on, KICK) == -3  # off for the final 15 minutes only
    off = sm.Book(pd.DataFrame(rows("g", "pinnacle", (ts("10:00"), -3, -110, -110),
                                    (ts("16:20"), None, None, None))))
    assert sm.close_line(off, KICK) is None
    after = sm.Book(pd.DataFrame(rows("g", "pinnacle", (ts("10:00"), -3, -110, -110),
                                      (ts("17:00"), -4, -110, -110))))
    assert sm.close_line(after, KICK) == -3  # a row at kickoff is not pregame


def test_clv_signs():
    assert sm.clv("home", -3, -3.5) == 0.5
    assert sm.clv("away", -3, -2.5) == 0.5
    assert sm.clv("over", 44.5, 45.5) == 1
    assert sm.clv("under", 44.5, 45.5) == -1


def test_key_numbers():
    assert sm.crosses_key(-2.5, -3) and sm.crosses_key(-2.5, -3.5) and sm.crosses_key(-6.5, -7)
    assert not sm.crosses_key(-3, -3.5) and not sm.crosses_key(-4, -4.5)


def planted_lead(lead_minutes: float, games: int = 30):
    """Every game: Pinnacle and DraftKings both move -3 -> -3.5; DraftKings `lead_minutes` later."""
    out = []
    for g in range(games):
        e = f"g{g}"
        out += rows(e, "pinnacle", (ts("08:00"), -3, -110, -110), (ts("10:00"), -3.5, -110, -110))
        out += rows(e, "draftkings", (ts("08:00"), -3, -110, -110),
                    (ts("10:00") + pd.Timedelta(minutes=lead_minutes), -3.5, -110, -110))
    return pd.DataFrame(out)


def test_s1_recovers_a_planted_pinnacle_lead():
    df = planted_lead(5)
    kicks = pd.Series(KICK, index=df["event_id"].unique())
    r = sm.s1(sm.s1_pairs(sm.timelines(df), kicks), resamples=200)
    assert r["pinnacle"]["share"].value == 1.0 and r["pinnacle"]["pairs"] == 30


def test_s1_follower_lead_and_same_second_ties():
    df = planted_lead(-5)
    kicks = pd.Series(KICK, index=df["event_id"].unique())
    assert sm.s1(sm.s1_pairs(sm.timelines(df), kicks), resamples=200)["pinnacle"]["share"].value == 0.0
    tie = planted_lead(0)
    r = sm.s1(sm.s1_pairs(sm.timelines(tie), kicks), resamples=200)
    assert r["pinnacle"]["pairs"] == 0 and r["pinnacle"]["ties"] == 30


def test_s1_matches_one_to_one_and_ignores_moves_beyond_an_hour():
    pin = [(ts("10:00"), -3, -3.5, None), (ts("10:30"), -3, -3.5, None)]
    dk = [(ts("10:10"), -3, -3.5, None)]
    assert len(sm.match_pairs(pin, dk)) == 1
    assert sm.match_pairs(pin, [(ts("11:31"), -3, -3.5, None)]) == []


def stale_game(event: str, close: float, retail_price: int = -110):
    return (rows(event, "pinnacle", (ts("08:00"), -3, -110, -110), (ts("10:00"), -3.5, -110, -110),
                 (ts("15:00"), close, -110, -110))
            + rows(event, "fanduel", (ts("08:00"), -3, retail_price, -110),
                   (ts("10:30"), -3.5, -110, -110)))


def test_s2_planted_stale_line_scores_clv_against_the_close():
    df = frame(*[stale_game(f"g{i}", -3.5) for i in range(5)])
    tl = sm.timelines(df)
    kicks = pd.Series(KICK, index=df["event_id"].unique())
    closes = {e: sm.close_line(b.get("pinnacle"), KICK) for e, b in tl.items()}
    ev = sm.s2_events(tl, kicks, closes)
    first = ev[ev["pin_to"] == -3.5]
    assert len(first) == 5 and (first["side"] == "home").all() and (first["clv"] == 0.5).all()
    assert first["stale_min"].iloc[0] == pytest.approx(29)  # until FanDuel moved at 10:30


def test_s2_skips_juiced_or_already_moved_retail_lines():
    tl = sm.timelines(frame(stale_game("g", -3.5, retail_price=-130)))
    closes = {"g": -3.5}
    assert sm.s2_events(tl, pd.Series({"g": KICK}), closes).query("pin_to == -3.5").empty
    moved = frame(rows("g", "pinnacle", (ts("08:00"), -3, -110, -110), (ts("10:00"), -3.5, -110, -110)),
                  rows("g", "fanduel", (ts("08:00"), -3, -110, -110),
                       (ts("10:00") + pd.Timedelta(seconds=30), -3.5, -110, -110)))
    assert sm.s2_events(sm.timelines(moved), pd.Series({"g": KICK}), closes).empty


def test_s3_detects_steam_and_measures_continuation():
    movers = ("pinnacle", "draftkings", "fanduel")
    out = []
    for i, b in enumerate(movers):
        out += rows("g", b, (ts("08:00"), -3, -110, -110), (ts("10:00") + pd.Timedelta(minutes=3 * i), -3.5, -110, -110))
    out += rows("g", "pinnacle", (ts("14:00"), -4.5, -110, -110))
    out += rows("g", "williamhill_us", (ts("08:00"), -3, -110, -110))
    tl = sm.timelines(pd.DataFrame(out))
    ep = sm.steam_episodes(tl, pd.Series({"g": KICK}))
    assert len(ep) == 1 and ep.iloc[0]["toward"] == "home"
    assert ep.iloc[0]["t"] == ts("10:06")
    res = sm.s3_outcomes(ep, tl, {"g": -4.5})
    assert res.iloc[0]["continuation"] == 1.0  # -3.5 at d, closed -4.5
    assert res.iloc[0]["retail_clv"] == 1.5  # Caesars still at -3
    assert res.iloc[0]["reference_in_first_three"]


def test_s3_needs_three_books_within_ten_minutes():
    out = []
    for i, b in enumerate(("pinnacle", "draftkings", "fanduel")):
        out += rows("g", b, (ts("08:00"), -3, -110, -110), (ts("10:00") + pd.Timedelta(minutes=6 * i), -3.5, -110, -110))
    assert sm.steam_episodes(sm.timelines(pd.DataFrame(out)), pd.Series({"g": KICK})).empty


def test_ratio_bootstrap_is_reproducible_and_covers_the_mean():
    df = pd.DataFrame({"event_id": np.repeat([f"g{i}" for i in range(40)], 3),
                       "clv": np.random.default_rng(1).normal(0.2, 1, 120)})
    a, b = sm.ratio_bootstrap(df, "clv", resamples=500), sm.ratio_bootstrap(df, "clv", resamples=500)
    assert a == b and a.low < a.value < a.high


def test_hypothetical_cover_excludes_pushes():
    ev = pd.DataFrame({"event_id": ["a", "b", "c"], "side": ["home", "away", "home"],
                       "line": [-3.0, -3.0, -3.0], "price": [-110, -110, -110]})
    r = sm.hypothetical_cover(ev, pd.Series({"a": 7, "b": 7, "c": 3}))
    assert r["bets"] == 2 and r["cover_rate"] == 0.5 and r["break_even"] == pytest.approx(110 / 210)
