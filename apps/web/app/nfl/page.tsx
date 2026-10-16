import type { Metadata } from "next";

export const metadata: Metadata = { title: "NFL Odds Board" };

export default function NflOddsBoardPage() {
  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold tracking-tight">NFL Odds Board</h1>
      <p className="text-sm text-muted">
        Not built yet. The first fixture-backed matchup arrives with MS-003.
      </p>
    </div>
  );
}
