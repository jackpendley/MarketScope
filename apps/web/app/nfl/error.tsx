"use client";

// Error boundaries must be client components. Shows a safe message; details stay in server logs.
export default function NflError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div
      role="alert"
      className="space-y-3 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm"
    >
      <p className="font-semibold text-danger">Something went wrong loading odds.</p>
      <button
        type="button"
        onClick={reset}
        className="rounded border border-line px-3 py-1 text-fg hover:text-accent"
      >
        Try again
      </button>
    </div>
  );
}
