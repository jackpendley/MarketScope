import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { E2E_USER } from "./e2e-user";

test.describe("signed out", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("pages redirect to the login page and come back after signing in", async ({ page }) => {
    await page.goto("/teams/KC?season=2026");
    await expect(page).toHaveURL(/\/login\?next=%2Fteams%2FKC%3Fseason%3D2026$/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary" })).toHaveCount(0);
    await page.getByLabel("Username or email").fill(E2E_USER.email);
    await page.getByLabel("Password", { exact: true }).fill(E2E_USER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/teams\/KC\?season=2026$/);
    await expect(page.getByRole("link", { name: E2E_USER.username })).toBeVisible();
  });

  test("a wrong password shows one generic message", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Username or email").fill(E2E_USER.username);
    await page.getByLabel("Password", { exact: true }).fill("not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.locator("#login-error")).toHaveText(
      "That username or email and password don't match.",
    );
    await expect(page).toHaveURL(/\/login$/);
  });

  test("the API answers 401 without a session, and sign-up is disabled", async ({ request }) => {
    const res = await request.get("/api/games");
    expect(res.status()).toBe(401);
    expect(await res.json()).toEqual({
      error: { code: "UNAUTHENTICATED", message: "Sign in required." },
    });
    expect((await request.get("/api/health/live")).status()).toBe(200);
    const signUp = await request.post("/api/auth/sign-up/email", {
      data: { email: "intruder@example.com", password: "a-long-enough-password", name: "x" },
      headers: { origin: "http://localhost:3200" },
    });
    expect(signUp.status()).toBeGreaterThanOrEqual(400);
    // The proxy refuses auth mutations from another origin (login CSRF), even the username sign-in.
    const crossSite = await request.post("/api/auth/sign-in/username", {
      data: { username: E2E_USER.username, password: E2E_USER.password },
      headers: { origin: "https://evil.example" },
    });
    expect(crossSite.status()).toBe(403);
  });

  test("the login page is accessible", async ({ page }) => {
    await page.goto("/login");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });

  test("an off-site next parameter is ignored", async ({ page }) => {
    await page.goto("/login?next=https://evil.example");
    await page.getByLabel("Username or email").fill(E2E_USER.username);
    await page.getByLabel("Password", { exact: true }).fill(E2E_USER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/nfl$/);
  });
});

test("signed in: the account page shows the user, and signing out ends the session", async ({
  browser,
}) => {
  // A fresh sign-in, so signing out doesn't invalidate the shared session other tests use.
  const context = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const page = await context.newPage();
  await page.goto("/login");
  await page.getByLabel("Username or email").fill(E2E_USER.username);
  await page.getByLabel("Password", { exact: true }).fill(E2E_USER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: E2E_USER.username }).click();
  await expect(page.getByRole("heading", { name: "Account" })).toBeVisible();
  await expect(page.getByText(E2E_USER.email)).toBeVisible();
  await page.getByRole("banner").getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/ratings");
  await expect(page).toHaveURL(/\/login\?next=%2Fratings$/);
  await context.close();
});
