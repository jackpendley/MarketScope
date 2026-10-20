# Sharp-market study S1–S5: discovery (MS-043)

_Generated 2026-10-20 03:20 UTC · commit `9e4a305` · reproduce with `research/src/marketscope_research/run_sharp_market.py --phase discovery`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum C, committed before this code as `59bce90`). Data: `line_moves` (minute-level main lines, ADR-052). CLV is in points against Pinnacle's line at kickoff. 95% intervals resample games (5,000 draws, seed 2026). Timing describes which book changed its number first, not who bet. Hypothetical results are analysis, not betting advice.

**Sample:** regular-season games kicking off 2026-09-01 to 2026-10-20: 91 final games, 91 with a Pinnacle spread history, 91 with a usable close.

## S1: who moves first? (primary: Pinnacle vs retail)

Matched identical spread changes (same a → b within 60 minutes). Gate: 200 Pinnacle–retail pairs (met).

| Reference book | Pairs with retail | Same-second ties | Share where the reference moved first |
| -------------- | ----------------- | ---------------- | ------------------------------------- |
| Pinnacle       | 216               | 0                | 0.741 (0.680 to 0.798)                |
| Circa          | 166               | 0                | 0.735 (0.664 to 0.812)                |
| Bookmaker.eu   | 135               | 0                | 0.637 (0.525 to 0.744)                |

**Primary result:** **Pinnacle leads retail** (discovery result; needs confirmation on weeks 7–14).

Exploratory, Pinnacle's share by time to kickoff: > 48 h 83.2%, 6–48 h 74.4%, < 6 h 62.8%; by size: 0.5 pt 74.9%, ≥ 1 pt 55.6%.

Exploratory, how retail books follow a Pinnacle change (books that were at Pinnacle's old number):

| Retail book | Pinnacle changes | ≤ 5 min | ≤ 15 min | ≤ 60 min | Never before kickoff | Median when followed |
| ----------- | ---------------- | ------- | -------- | -------- | -------------------- | -------------------- |
| DraftKings  | 362              | 3.6%    | 6.6%     | 11.6%    | 70.4%                | 135 min              |
| FanDuel     | 331              | 1.2%    | 2.4%     | 3.6%     | 83.4%                | 941 min              |
| Caesars     | 395              | 6.3%    | 9.9%     | 14.9%    | 55.4%                | 286 min              |
| Hard Rock   | 389              | 3.6%    | 5.4%     | 10.3%    | 42.7%                | 515 min              |

## S2: stale retail lines (primary: CLV of taking the old number)

Events: a retail book still posting Pinnacle's old number 60 seconds after Pinnacle moved, on the side Pinnacle moved toward, at −125 or better. 1450 events in 89 games. Gate: 100 events in 30 games (met).

Mean CLV: +0.44 (+0.36 to +0.52) points. **Primary result:** **stale retail lines carry positive CLV** (discovery result; needs confirmation on weeks 7–14).

Exploratory:

- Decision 5 minutes after Pinnacle's move: 1425 events, mean CLV +0.42 (+0.34 to +0.49).
- Moves crossing or landing on 3 or 7: 366 events, mean CLV +0.32 (+0.19 to +0.44); others +0.48 (+0.38 to +0.58).
- Totals, same rule: 1254 events, mean CLV +0.55 (+0.43 to +0.68).
- **Hypothetical** cover rate of the S2 bets against actual results: 53.7% of 1424 decided bets (pushes excluded), versus a break-even of 52.9% at the posted prices. One season's results are noisy; CLV is the yardstick.

| Retail book | Events | Mean CLV (points) | Median time the old number stayed up |
| ----------- | ------ | ----------------- | ------------------------------------ |
| DraftKings  | 356    | +0.46             | 124 min                              |
| FanDuel     | 328    | +0.41             | 562 min                              |
| Hard Rock   | 386    | +0.40             | 385 min                              |
| Caesars     | 380    | +0.49             | 271 min                              |

### S2 robustness (added after seeing the primary result; not pre-registered)

By construction the old number starts better than Pinnacle's new one, so S2's CLV splits into that head start plus Pinnacle's own move from its new number to the close (negative when it moves back). Points-based CLV also ignores what the retail book charged for the old number.

- Head start over Pinnacle's new number: +0.54 (+0.51 to +0.58) points; Pinnacle's continuation from its new number to the close: -0.10 (-0.18 to -0.02) points.

| Retail price on the side taken | Events | Mean CLV (points)      | Hypothetical cover rate | Break-even at those prices |
| ------------------------------ | ------ | ---------------------- | ----------------------- | -------------------------- |
| −110 or better                 | 628    | +0.52 (+0.39 to +0.64) | 57.9%                   | 52.0%                      |
| −111 to −125                   | 822    | +0.38 (+0.29 to +0.47) | 50.5%                   | 53.6%                      |

### S2b: standard prices only (Addendum D; registered after discovery, tested on confirmation)

Events at −110 or better: 628. Mean CLV +0.52 (+0.39 to +0.64) points; mean hypothetical (cover − break-even) per decided bet +0.059 (-0.048 to +0.161). Discovery numbers motivated this hypothesis, so they are not evidence for it.

## S3: steam (primary: does Pinnacle keep moving to the close?)

Steam: 3 of the 7 books move the spread the same way within 10 minutes. 139 episodes; 120 with Pinnacle on the board at the decision time and a usable close. Gate: 50 (met).

Continuation from 60 s after the third move to the close: +0.17 (+0.01 to +0.34) points in the steam direction. **Primary result:** **steam continues to the close** (discovery result; needs confirmation on weeks 7–14).

Exploratory:

- CLV at the best line among retail books that had not moved (−125 or better): +0.82 (+0.56 to +1.07) points (120 episodes).
- A reference book among the first three movers in 91.7% of episodes.
- Totals: 195 episodes, continuation +0.24 (+0.12 to +0.37).

## S4 and S5: limits and key numbers (exploratory, descriptive)

Pinnacle spread changes: 877. Reversed by the close (the closing line back at or beyond the old number):

| Pinnacle changes              | Count | Reversed by the close |
| ----------------------------- | ----- | --------------------- |
| Limit above the game's median | 373   | 44.5%                 |
| Limit at or below the median  | 504   | 36.5%                 |
| Crossing or landing on 3 or 7 | 132   | 32.6%                 |
| Other changes                 | 745   | 41.2%                 |

Retail follow-through on key-number moves (S5): within 60 minutes 10.6% versus 10.3% for other moves.

## What this can't see

Who bet or why; Circa's limits (not reported); exchange order books; moves more than 14 days before kickoff. Points-based CLV ignores price beyond the −125 bound. One season of history.
