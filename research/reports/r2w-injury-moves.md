# R2w: market moves on newly confirmed absences, 2026 weeks 1–6 (MS-035c)

_Generated 2026-10-19 02:20 UTC · commit `9678b20` on `main` · reproduce with `research/src/marketscope_research/run_injury_moves.py`._

Design pre-registered in `research/PREREGISTRATION.md` (addendum B, committed before this code). Event: a starter (≥ 50% of snaps over his recent games) listed Out on the final injury report who played the team's previous game. Outcome: board-consensus margin move from 6 days out to the close. 95% intervals resample games (5,000 draws). Information already priced 6 days out is not visible here. Market data; not betting advice.

## Primary: consensus move per net newly-out starter

77 games with a 6-day and closing consensus; 80 events in them (42 games with at least one), 5 QB events. Gate: 30 events (met).

Slope: +0.40 (+0.14 to +0.73) points of line move toward the opponent per event. Result: **the consensus moves toward the injured team's opponent**.

## Robustness (added after seeing the primary result)

Counting non-QB events only: +0.30 (+0.12 to +0.51) points per event. Not pre-registered; it checks that the primary slope does not rest on the few QB games.

## QB events (exploratory)

QB claim gate (10) not met. Moves toward the opponent of the team missing its QB, game by game: +2.0, -1.0, -0.8, -0.0, +6.8.
