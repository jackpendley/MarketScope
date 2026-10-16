/**
 * NFL season year for a kickoff time. The season starts in September and ends in
 * February, so January/February games belong to the previous calendar year's season.
 */
export function nflSeasonForKickoff(iso: string): number {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) throw new RangeError(`invalid kickoff time: ${iso}`);
  const year = date.getUTCFullYear();
  return date.getUTCMonth() <= 1 ? year - 1 : year;
}
