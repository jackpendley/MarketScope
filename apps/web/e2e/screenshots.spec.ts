import { expect, test, type Page } from "@playwright/test";

// Portfolio screenshots of the SYNTHETIC e2e database (every page shows its synthetic-data banner).
// Not part of the normal suite: SCREENSHOTS=1 pnpm exec playwright test e2e/screenshots.spec.ts
test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to capture docs/screenshots");

const OUT = "../../docs/screenshots";
const MOBILE = new Set(["board", "ratings", "matchups"]); // phone captures: a few pages show the layout
const MAX_HEIGHT = 2200; // desktop captures are full-page up to this height, to keep the repo small

async function shoot(page: Page, file: string, desktop: boolean) {
  if (!desktop) return page.screenshot({ path: file });
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  const width = page.viewportSize()!.width;
  return page.screenshot({
    path: file,
    fullPage: true,
    clip: { x: 0, y: 0, width, height: Math.min(height, MAX_HEIGHT) },
  });
}
const PAGES: [string, string][] = [
  ["board", "/nfl"],
  ["replay", "/replay"],
  ["signals", "/signals"],
  ["ratings", "/ratings"],
  ["team", "/teams/KC"],
  ["matchups", "/matchups"],
  ["projections", "/projections"],
  ["model", "/model"],
  ["research", "/research"],
  ["data", "/data"],
];

for (const [name, path] of PAGES) {
  test(`screenshot ${name}`, async ({ page }, info) => {
    test.skip(info.project.name === "mobile" && !MOBILE.has(name), "desktop only");
    await page.goto(path);
    await expect(page.locator("main h1").first()).toBeVisible();
    await shoot(page, `${OUT}/${name}-${info.project.name}.png`, info.project.name === "desktop");
  });
}

test("screenshot game page", async ({ page }, info) => {
  test.skip(info.project.name === "mobile", "desktop only");
  await page.goto("/nfl");
  await page.locator("section[aria-labelledby^='evt-']").first().getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: "Feed coverage" })).toBeVisible();
  await shoot(page, `${OUT}/game-${info.project.name}.png`, info.project.name === "desktop");
});
