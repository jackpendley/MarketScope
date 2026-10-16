import { runMigrations } from "../migrate";

const url = process.env.DATABASE_URL;
if (!url) {
  console.error("DATABASE_URL is not set (see packages/db/.env.example)");
  process.exit(1);
}

await runMigrations(url);
console.log(`Migrations applied to ${new URL(url).pathname.slice(1)}`);
