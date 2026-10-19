// Account administration for the invite-only site (MS-038, ADR-049). There is no sign-up page:
// accounts are created and passwords reset here.
//
//   pnpm --filter @marketscope/web users list
//   pnpm --filter @marketscope/web users create --username jack --email jack@example.com
//   pnpm --filter @marketscope/web users reset-password --user jack
//   pnpm --filter @marketscope/web users sign-out --user jack
//
// Uses DATABASE_URL (apps/web/.env.local unless set in the environment). Passwords are typed at a
// hidden prompt, or piped with --password-stdin; never pass them as arguments (shell history).

import { createInterface } from "node:readline/promises";
import { parseArgs } from "node:util";
import { createDb, deleteAccountSessions, findAccount, listAccounts } from "@marketscope/db";
import { createAccount, createAuth, resetPassword } from "../lib/auth-config";
import { PASSWORD_RULE } from "../lib/password-policy";

const { positionals, values } = parseArgs({
  allowPositionals: true,
  options: {
    username: { type: "string" },
    email: { type: "string" },
    name: { type: "string" },
    user: { type: "string" },
    "password-stdin": { type: "boolean", default: false },
    yes: { type: "boolean", default: false },
  },
});

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const c of process.stdin) chunks.push(c as Buffer);
  return Buffer.concat(chunks)
    .toString("utf8")
    .replace(/\r?\n$/, "");
}

async function askHidden(prompt: string): Promise<string> {
  const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: true });
  const out = rl as unknown as { _writeToOutput: (s: string) => void };
  const write = out._writeToOutput.bind(rl);
  out._writeToOutput = (s: string) => {
    if (s.startsWith(prompt)) write(prompt); // echo the prompt, never the typed characters
  };
  const answer = await rl.question(prompt);
  rl.close();
  process.stdout.write("\n");
  return answer;
}

async function newPassword(): Promise<string> {
  if (values["password-stdin"]) return readStdin();
  if (!process.stdin.isTTY)
    throw new Error("Run this in a terminal, or pipe the password with --password-stdin.");
  console.log(PASSWORD_RULE);
  const first = await askHidden("New password: ");
  const second = await askHidden("Repeat it: ");
  if (first !== second) throw new Error("The passwords don't match.");
  return first;
}

async function confirm(host: string): Promise<void> {
  if (values.yes || ["localhost", "127.0.0.1"].includes(host)) return;
  if (!process.stdin.isTTY) throw new Error(`Refusing to change ${host} without --yes.`);
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const answer = await rl.question(
    `This changes accounts in the database at ${host}. Continue? [y/N] `,
  );
  rl.close();
  if (answer.trim().toLowerCase() !== "y") throw new Error("Cancelled.");
}

async function main() {
  const command = positionals[0];
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("Set DATABASE_URL.");
  const host = new URL(url).hostname; // printed without credentials
  const { db, close } = createDb(url, { max: 1 });
  const auth = createAuth(db);
  try {
    const findUser = async (who: string) => {
      const u = await findAccount(db, who);
      if (!u) throw new Error(`No account for ${who}.`);
      return u;
    };
    if (command === "list") {
      const rows = await listAccounts(db);
      console.log(`${rows.length} account(s) at ${host}`);
      for (const r of rows)
        console.log(
          `  ${r.username ?? "–"}\t${r.email}\tcreated ${r.createdAt.toISOString().slice(0, 10)}\t${r.activeSessions} active session(s)`,
        );
    } else if (command === "create") {
      if (!values.username || !values.email)
        throw new Error("create needs --username and --email.");
      if (!/^[a-zA-Z0-9_.]{3,30}$/.test(values.username))
        throw new Error("Usernames are 3–30 letters, digits, underscores or dots.");
      await confirm(host);
      const password = await newPassword();
      await createAccount(auth, {
        username: values.username,
        email: values.email,
        name: values.name,
        password,
      });
      console.log(`Created ${values.username} <${values.email.toLowerCase()}> at ${host}.`);
    } else if (command === "reset-password") {
      if (!values.user) throw new Error("reset-password needs --user (username or email).");
      const u = await findUser(values.user);
      await confirm(host);
      await resetPassword(auth, u.id, await newPassword());
      console.log(`Password reset for ${u.username}; all of their sessions were signed out.`);
    } else if (command === "sign-out") {
      if (!values.user) throw new Error("sign-out needs --user (username or email).");
      const u = await findUser(values.user);
      await confirm(host);
      const gone = await deleteAccountSessions(db, u.id);
      console.log(
        `Signed ${u.username} out of ${gone} session(s) (cached cookies expire within 5 minutes).`,
      );
    } else {
      console.log(
        "Usage: users list | create --username U --email E [--name N] | reset-password --user U | sign-out --user U",
      );
      process.exitCode = 1;
    }
  } finally {
    await close();
  }
}

main().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
