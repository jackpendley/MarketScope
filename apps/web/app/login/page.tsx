import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { LoginForm } from "@/components/login-form";
import { safeNext } from "@/lib/auth-redirect";
import { getAuth } from "@/lib/server/auth";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const next = safeNext((await searchParams).next);
  const requestHeaders = await headers(); // first: marks the page dynamic before any auth code runs
  const session = await getAuth().api.getSession({ headers: requestHeaders });
  if (session) redirect(next);

  return (
    <div className="relative flex min-h-[calc(100vh-10rem)] items-center justify-center py-10">
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/3 -z-10 h-80 w-[36rem] max-w-full -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent/10 blur-3xl"
      />
      <div className="w-full max-w-sm space-y-7">
        <div className="space-y-2 text-center">
          <p className="text-3xl font-semibold tracking-tight">
            Market<span className="text-accent">Scope</span>
          </p>
          <p className="text-sm text-muted">
            NFL market intelligence and KenPom-style team ratings
          </p>
        </div>
        <div className="rounded-xl border border-line bg-surface/95 p-6 shadow-xl shadow-black/40 backdrop-blur">
          <h1 className="mb-5 text-lg font-semibold">Sign in</h1>
          <LoginForm next={next} />
        </div>
        <p className="text-center text-xs text-subtle">
          Odds board · Market replay · Ratings · Projections · Research
        </p>
        <p className="text-center text-xs text-subtle">
          Accounts are by invitation. Forgot your password? Ask the site owner to reset it.
        </p>
      </div>
    </div>
  );
}
