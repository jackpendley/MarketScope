import Link from "next/link";

export default function GameNotFound() {
  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">Game not found</h1>
      <p className="text-sm text-muted">
        No stored game matches that link. It may be outside the collected data.
      </p>
      <Link href="/nfl" className="text-sm text-accent hover:underline">
        ← Back to the odds board
      </Link>
    </div>
  );
}
