import pandas as pd

from marketscope_research.close_check import compare, summary

K = pd.Timestamp("2026-10-04T17:00:00Z")


def rows(event, hours_before, points, source="oddspapi", market_books=("draftkings", "fanduel", "williamhill_us")):
    t = K - pd.Timedelta(hours=hours_before)
    return [(event, t, b, p, source) for b, p in zip(market_books, points)]


def test_compare_uses_last_pregame_snapshot_and_orientation():
    cols = ["event_id", "observed_at", "bookmaker_key", "point", "source"]
    spreads = pd.DataFrame(rows("e", 6, [-2.5] * 3) + rows("e", 0.1, [-3] * 3) + rows("e", -1, [-9] * 3), columns=cols)
    totals = pd.DataFrame(rows("e", 0.1, [44.5] * 3), columns=cols)
    games = pd.DataFrame({"event_id": ["e"], "game_id": ["g"], "nflverse_close_home_spread": [-3.0],
                          "nflverse_close_total": [45.0]})
    df = compare(games, spreads, totals, pd.Series({"e": K}))
    r = df.iloc[0]
    assert r["consensus"] == -3.0 and r["spread_diff"] == 0 and bool(r["same_favorite"])  # in-play row ignored
    assert r["total_diff"] == -0.5
    s = summary(df)
    assert s.loc["all", "spread_exact"] == 1.0 and s.loc["oddspapi", "games"] == 1
