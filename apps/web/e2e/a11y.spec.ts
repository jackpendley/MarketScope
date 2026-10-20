import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Automated accessibility check (axe-core, WCAG 2.1 A and AA rules) on every page, against the
// synthetic e2e database. Automated rules catch roughly a third of issues; keyboard and screen
// reader checks are manual (docs/ACCESSIBILITY.md).
const STATIC_PAGES = [
  "/nfl",
  "/replay",
  "/signals",
  "/data",
  "/ratings",
  "/teams/KC",
  "/matchups",
  "/model",
  "/projections",
  "/research",
  "/systems",
  "/ml-lab",
];

async function expectNoViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const summary = results.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.nodes.length} node(s), e.g. ${v.nodes[0]?.target.join(" ")}`,
  );
  expect(summary).toEqual([]);
}

for (const path of STATIC_PAGES) {
  test(`no automated accessibility violations on ${path}`, async ({ page }) => {
    await page.goto(path);
    await expectNoViolations(page);
  });
}

test("no automated accessibility violations on a game page and its line history", async ({
  page,
}) => {
  await page.goto("/nfl");
  await page.locator("section[aria-labelledby^='evt-']").first().getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: "Feed coverage" })).toBeVisible();
  await expectNoViolations(page);
  await page.getByRole("link", { name: /Open market replay/ }).click();
  await expect(page.locator("figure").first()).toBeVisible();
  await expectNoViolations(page);
});

test("keyboard users can skip straight to the main content", async ({ page }) => {
  await page.goto("/ratings");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await skip.press("Enter");
  await expect(page.locator("main#main")).toBeFocused();
});
