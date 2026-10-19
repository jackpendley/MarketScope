import { expect, test as setup } from "@playwright/test";
import { E2E_USER, STORAGE_STATE } from "./e2e-user";

// Signs in once through the real login page and saves the session for every other test.
setup("sign in as the e2e user", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username or email").fill(E2E_USER.username);
  await page.getByLabel("Password", { exact: true }).fill(E2E_USER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/nfl$/);
  await page.context().storageState({ path: STORAGE_STATE });
});
