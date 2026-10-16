import { defineConfig } from "drizzle-kit";

// `drizzle-kit generate` diffs src/schema.ts against the committed snapshots in
// ./drizzle and writes a new SQL migration. It needs no database connection.
export default defineConfig({
  dialect: "postgresql",
  schema: "./src/schema.ts",
  out: "./drizzle",
  casing: "snake_case",
  strict: true,
  verbose: true,
});
