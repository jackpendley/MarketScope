import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { ChangePasswordForm } from "@/components/change-password-form";
import { SignOutButton } from "@/components/sign-out-button";
import { SESSION_DAYS } from "@/lib/auth-config";
import { getAuth } from "@/lib/server/auth";

export const metadata: Metadata = { title: "Account" };

export default async function AccountPage() {
  const requestHeaders = await headers(); // first: marks the page dynamic before any auth code runs
  const session = await getAuth().api.getSession({ headers: requestHeaders });
  if (!session) redirect("/login?next=/account");
  const user = session.user as typeof session.user & {
    username?: string;
    displayUsername?: string;
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold tracking-tight">Account</h1>
      <section aria-labelledby="profile" className="space-y-2">
        <h2 id="profile" className="text-sm font-medium uppercase tracking-wide text-muted">
          Signed in as
        </h2>
        <dl className="grid max-w-md grid-cols-[8rem_1fr] gap-y-1 text-sm">
          <dt className="text-muted">Username</dt>
          <dd>{user.displayUsername ?? user.username ?? "–"}</dd>
          <dt className="text-muted">Email</dt>
          <dd>{user.email}</dd>
        </dl>
        <p className="text-xs text-subtle">
          You stay signed in for {SESSION_DAYS} days unless you sign out. <SignOutButton />
        </p>
      </section>
      <section aria-labelledby="password" className="space-y-3">
        <h2 id="password" className="text-sm font-medium uppercase tracking-wide text-muted">
          Change password
        </h2>
        <ChangePasswordForm />
      </section>
    </div>
  );
}
