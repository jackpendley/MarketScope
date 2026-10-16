import { setupTestDatabase } from "./testing";

export default async function globalSetup() {
  await setupTestDatabase();
}
