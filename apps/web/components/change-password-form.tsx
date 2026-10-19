"use client";

import { useState, type FormEvent } from "react";
import { authClient } from "@/lib/auth-client";
import { newPasswordProblem } from "@/lib/auth-messages";

const input =
  "w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40";

export function ChangePasswordForm({ minLength }: { minLength: number }) {
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formEl = e.currentTarget;
    const form = new FormData(formEl);
    const current = String(form.get("current") ?? "");
    const next = String(form.get("next") ?? "");
    const problem = newPasswordProblem(next, String(form.get("confirm") ?? ""), current, minLength);
    if (problem) return setStatus({ ok: false, text: problem });
    setPending(true);
    const res = await authClient.changePassword({
      currentPassword: current,
      newPassword: next,
      revokeOtherSessions: true,
    });
    setPending(false);
    if (res.error) {
      setStatus({
        ok: false,
        text:
          res.error.status === 429
            ? "Too many attempts. Wait a minute, then try again."
            : "Your current password is not correct.",
      });
      return;
    }
    formEl.reset();
    setStatus({ ok: true, text: "Password changed. Other devices have been signed out." });
  }

  return (
    <form onSubmit={onSubmit} className="max-w-sm space-y-4">
      {(
        [
          ["current", "Current password", "current-password"],
          ["next", "New password", "new-password"],
          ["confirm", "Confirm new password", "new-password"],
        ] as const
      ).map(([name, label, auto]) => (
        <div key={name} className="space-y-1.5">
          <label htmlFor={name} className="block text-sm font-medium">
            {label}
          </label>
          <input
            id={name}
            name={name}
            type="password"
            autoComplete={auto}
            required
            className={input}
          />
        </div>
      ))}
      <p className="text-xs text-muted">
        At least {minLength} characters. A passphrase works well.
      </p>
      {status && (
        <p
          role={status.ok ? "status" : "alert"}
          className={`rounded-md border px-3 py-2 text-sm text-fg ${status.ok ? "border-best/40 bg-best/10" : "border-danger/40 bg-danger/10"}`}
        >
          {status.text}
        </p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-canvas hover:bg-accent/90 disabled:opacity-60"
      >
        {pending ? "Saving…" : "Change password"}
      </button>
    </form>
  );
}
