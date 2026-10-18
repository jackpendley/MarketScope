// SYNTHETIC MarketScope Ratings for demo/e2e databases (MS-033): eight teams, four weekly snapshots,
// played and upcoming games, coaching staff, pre-kickoff model estimates, QB names, closing lines
// and a one-time test record. Every value is generated (model_version "synthetic-demo"), so the UI
// shows its synthetic-data banner. Never real model output.
//
// The upcoming week's BUF-MIA and DAL-PHI games link to the synthetic odds events of the same teams
// (seed those first), so the game pages show the model panel.

import {
  type Database,
  modelPredictions,
  modelRuns,
  nflCoachingStaff,
  nflGames,
  nflPlayerGameSnaps,
  nflTeams,
  ratingSnapshots,
} from "@marketscope/db";
import { sql } from "drizzle-orm";

export const SYNTHETIC_RATINGS_VERSION = "synthetic-demo";

const TEAMS = [
  ["KC", "Kansas City Chiefs", "AFC", "AFC West"],
  ["DEN", "Denver Broncos", "AFC", "AFC West"],
  ["LV", "Las Vegas Raiders", "AFC", "AFC West"],
  ["LAC", "Los Angeles Chargers", "AFC", "AFC West"],
  ["BUF", "Buffalo Bills", "AFC", "AFC East"],
  ["MIA", "Miami Dolphins", "AFC", "AFC East"],
  ["PHI", "Philadelphia Eagles", "NFC", "NFC East"],
  ["DAL", "Dallas Cowboys", "NFC", "NFC East"],
] as const;

// Fixed underlying strengths (points vs average) so the demo table has a stable order.
const STRENGTH = [6.5, 3.0, -4.5, 1.0, 5.0, -2.0, 4.0, -1.5];

/** Week w pairings for the eight teams (indices, home first); week 4 is upcoming. */
const PAIRS = [
  [
    [0, 1],
    [2, 3],
    [4, 5],
    [6, 7],
  ],
  [
    [0, 2],
    [1, 3],
    [4, 6],
    [5, 7],
  ],
  [
    [3, 0],
    [1, 2],
    [7, 4],
    [6, 5],
  ],
  [
    [4, 5],
    [7, 6],
    [0, 1],
    [3, 2],
  ],
] as const;

const qbId = (t: number) => `00-SYN000${t}`;

/** Rough synthetic moneylines for a home spread (not a pricing model). */
const moneylines = (homeSpread: number): [number, number] => {
  const fav = Math.round(-110 - 20 * Math.abs(homeSpread));
  const dog = Math.round(100 + 16 * Math.abs(homeSpread));
  return homeSpread <= 0 ? [fav, dog] : [dog, fav];
};

export async function seedSyntheticRatings(db: Database, now: Date): Promise<number> {
  const season = now.getUTCMonth() >= 2 ? now.getUTCFullYear() : now.getUTCFullYear() - 1;
  await db
    .insert(nflTeams)
    .values(
      TEAMS.map(([abbr, fullName, conference, division]) => ({
        abbr,
        franchise: abbr,
        fullName,
        nickname: fullName.split(" ").at(-1)!,
        conference,
        division,
      })),
    )
    .onConflictDoNothing();

  const DAY = 86_400_000;
  const games = PAIRS.flatMap((week, w) =>
    week.map(([h, a], i) => {
      const kickoff = new Date(now.getTime() + (w - 3) * 7 * DAY + 2 * DAY + i * 3_600_000);
      const played = w < 3;
      const margin = Math.round(STRENGTH[h]! - STRENGTH[a]! + 2 + ((i * 7 + w * 3) % 9) - 4);
      const closeHomeSpread = -Math.round((STRENGTH[h]! - STRENGTH[a]! + 2) * 2) / 2;
      const [homeMl, awayMl] = moneylines(closeHomeSpread);
      return {
        gameId: `${season}_${String(w + 1).padStart(2, "0")}_${TEAMS[a]![0]}_${TEAMS[h]![0]}`,
        season,
        gameType: "REG",
        week: w + 1,
        kickoffUtc: kickoff.toISOString(),
        homeTeam: TEAMS[h]![0],
        awayTeam: TEAMS[a]![0],
        neutralSite: false,
        divisionGame: TEAMS[h]![3] === TEAMS[a]![3],
        homeScore: played ? 20 + Math.max(margin, 0) : null,
        awayScore: played ? 20 + Math.max(-margin, 0) : null,
        nflverseCloseHomeSpread: played ? closeHomeSpread : null,
        nflverseCloseTotal: played ? 44.5 : null,
        nflverseCloseHomeMoneyline: played ? homeMl : null,
        nflverseCloseAwayMoneyline: played ? awayMl : null,
        h,
        a,
        margin,
      };
    }),
  );
  await db.insert(nflGames).values(games.map(({ h: _h, a: _a, margin: _m, ...g }) => g));
  await db.execute(sql`
    UPDATE nfl_games g SET event_id = e.id
    FROM events e, nfl_teams ht, nfl_teams awt
    WHERE ht.abbr = g.home_team AND awt.abbr = g.away_team AND g.home_score IS NULL
      AND e.home_team = ht.full_name AND e.away_team = awt.full_name
  `);
  await db.insert(nflPlayerGameSnaps).values(
    games
      .filter((g) => g.homeScore !== null)
      .flatMap((g) =>
        [g.h, g.a].map((t) => ({
          gameId: g.gameId,
          season,
          week: g.week,
          pfrPlayerId: `SynQb${t}`,
          gsisId: qbId(t),
          player: `Synthetic QB ${TEAMS[t]![0]}`,
          position: "QB",
          team: TEAMS[t]![0],
          offenseSnaps: 60,
          offensePct: 1,
          defenseSnaps: 0,
          stSnaps: 0,
        })),
      ),
  );

  const snaps = [];
  for (let week = 0; week <= 3; week++) {
    const em = STRENGTH.map((s, t) => s * (0.6 + 0.1 * week) + ((t * 5 + week) % 3) - 1);
    const order = [...em.keys()].sort((x, y) => em[y]! - em[x]!);
    const rank = (t: number) => order.indexOf(t) + 1;
    for (let t = 0; t < TEAMS.length; t++) {
      const played = games.filter((g) => g.week <= week && (g.h === t || g.a === t));
      const wins = played.filter((g) => (g.h === t ? g.margin > 0 : g.margin < 0)).length;
      snaps.push({
        modelVersion: SYNTHETIC_RATINGS_VERSION,
        season,
        week,
        team: TEAMS[t]![0],
        adjEm: em[t]!,
        adjEmSe: 2.6 - 0.1 * week,
        adjEmRank: rank(t),
        adjO: 2.0 + em[t]! / 30,
        adjOSe: 0.15,
        adjORank: rank(t),
        adjD: 2.0 - em[t]! / 30,
        adjDSe: 0.15,
        adjDRank: rank(t),
        adjSt: ((t % 3) - 1) * 0.4,
        adjStSe: 0.4,
        adjStRank: (t % TEAMS.length) + 1,
        adjPace: 10.5 + (t % 4) * 0.2,
        adjPaceSe: 0.3,
        adjPaceRank: TEAMS.length - t,
        priorWeight: 1 - 0.05 * week,
        passOff: em[t]! / 60,
        passDef: -em[t]! / 80,
        rushOff: em[t]! / 120,
        rushDef: -em[t]! / 160,
        succOff: em[t]! / 300,
        succDef: -em[t]! / 300,
        ppdOff: em[t]! / 25,
        ppdDef: -em[t]! / 30,
        games: played.length,
        wins,
        losses: played.length - wins,
        ties: 0,
        pointsFor: played.length * 22,
        pointsAgainst: played.length * 20,
        expectedWins: played.length * 0.5 + em[t]! / 20,
        pythagWins: played.length * 0.52,
        luck: wins - (played.length * 0.5 + em[t]! / 20),
        luckRank: ((t + week) % TEAMS.length) + 1,
        oneScoreLuck: 0.1 * ((t % 3) - 1),
        fumbleLuck: 0.5 * ((t % 4) - 1.5),
        intLuck: 0.3 * ((t % 5) - 2),
        fgLuck: (t % 3) - 1,
        returnTdDiff: (t % 3) - 1,
        sos: played.length ? ((t * 3) % 5) - 2 : null,
        sosRank: played.length ? ((t * 3) % TEAMS.length) + 1 : null,
        oppAdjO: played.length ? 2.1 : null,
        oppAdjD: played.length ? 2.05 : null,
        nondivSos: null,
        remainingSos: ((t * 2) % 5) - 2,
        remainingGames: 4 - played.length,
        offSuccessRate: played.length ? 0.44 + em[t]! / 200 : null,
        defSuccessRate: played.length ? 0.44 - em[t]! / 200 : null,
        offExplosiveness: played.length ? 1.1 : null,
        defExplosiveness: played.length ? 1.0 : null,
        offStartYardline: played.length ? 29 + (t % 3) : null,
        defStartYardline: played.length ? 29 - (t % 3) : null,
        offPointsPerOpp: played.length ? 4.0 + em[t]! / 10 : null,
        defPointsPerOpp: played.length ? 4.0 - em[t]! / 10 : null,
        offTurnovers: played.length ? 1.2 : null,
        defTurnovers: played.length ? 1.1 : null,
      });
    }
  }
  await db.insert(ratingSnapshots).values(snaps);

  await db.insert(nflCoachingStaff).values(
    TEAMS.map(([abbr], t) => ({
      season,
      team: abbr,
      role: "HC",
      coachId: `name:synthetic-coach-${t}`,
      coachName: `Synthetic Coach ${t + 1}`,
      fromWeek: 1,
      toWeek: 18,
      offensePlaycaller: true,
      defensePlaycaller: false,
    })),
  );

  // Estimates for every game: played weeks a day before kickoff, the upcoming week an hour ago.
  await db.insert(modelPredictions).values(
    games.map((g, i) => {
      const m = STRENGTH[g.h]! - STRENGTH[g.a]! + 1.5;
      const kickoff = Date.parse(g.kickoffUtc);
      return {
        modelVersion: SYNTHETIC_RATINGS_VERSION,
        gameId: g.gameId,
        predictedAt: new Date(
          g.week === 4 ? now.getTime() - 3_600_000 : kickoff - 86_400_000,
        ).toISOString(),
        kickoffUtc: g.kickoffUtc,
        homeTeam: g.homeTeam,
        awayTeam: g.awayTeam,
        expectedMargin: m,
        expectedTotal: 45,
        homeScore: (45 + m) / 2,
        awayScore: (45 - m) / 2,
        pHome: 1 / (1 + Math.exp(-m / 6.5)),
        homeQb: qbId(g.h),
        awayQb: qbId(g.a),
        homeQbP: 1,
        awayQbP: i === games.length - 1 ? 0.64 : 1,
        contributions: { ratings: m - 1.1, home: 0.3, qb: 0.5, absences: 0.3 },
      };
    }),
  );

  const metric = (mae: number, brier: number) => ({
    margin_mae: mae,
    margin_mae_lo: mae - 0.9,
    margin_mae_hi: mae + 0.9,
    d_margin_mae: mae - 9.5,
    d_margin_mae_lo: mae - 9.8,
    d_margin_mae_hi: mae - 9.2,
    brier,
    log_loss: brier * 2.9,
    total_mae: null,
  });
  await db.insert(modelRuns).values({
    modelVersion: SYNTHETIC_RATINGS_VERSION,
    runKind: "test",
    seasons: String(season - 1),
    games: 272,
    metrics: {
      [SYNTHETIC_RATINGS_VERSION]: metric(10.0, 0.22),
      "Synthetic Elo": metric(10.4, 0.23),
      "nflverse close": { ...metric(9.5, 0.21), d_margin_mae: 0 },
      paired_vs_benchmarks: {
        "Synthetic Elo": { d_margin_mae: -0.4, d_margin_mae_lo: -0.7, d_margin_mae_hi: -0.1 },
        "nflverse close": { d_margin_mae: 0.5, d_margin_mae_lo: 0.2, d_margin_mae_hi: 0.8 },
      },
    },
    paramsSha256: "synthetic".padEnd(64, "0"),
    codeSha: "0000000",
    notes: "SYNTHETIC demo record, not a real evaluation",
    ranAt: now.toISOString(),
  });
  return snaps.length;
}
