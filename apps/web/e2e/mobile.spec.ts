import { expect, test, type Page } from "@playwright/test";

async function expectNoHorizontalScroll(page: Page) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
}

test("board, detail, and history fit a phone screen without horizontal scrolling", async ({
  page,
}) => {
  await page.goto("/nfl");
  await expect(page.getByRole("heading", { name: "NFL Odds Board" })).toBeVisible();
  await expectNoHorizontalScroll(page);

  await page.locator("section[aria-labelledby^='evt-']").first().getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: "Feed coverage" })).toBeVisible();
  await expectNoHorizontalScroll(page);

  await page.getByRole("link", { name: /Open market replay/ }).click();
  await expect(page.locator("figure").first()).toBeVisible();
  await expectNoHorizontalScroll(page);
});

test("ratings and team pages fit a phone screen (tables scroll inside their card)", async ({
  page,
}) => {
  await page.goto("/ratings");
  await expect(page.getByRole("heading", { name: "MarketScope Ratings" })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.goto("/teams/KC");
  await expect(page.getByRole("heading", { name: /Kansas City Chiefs/ })).toBeVisible();
  await expectNoHorizontalScroll(page);
});

test("matchups, the model scorecard and the game panel fit a phone screen", async ({ page }) => {
  await page.goto("/matchups");
  await expect(page.getByRole("heading", { name: "Matchups" })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.goto("/model");
  await expect(page.getByRole("heading", { name: "Model scorecard" })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.goto("/projections");
  await expect(page.getByRole("heading", { name: "Season projections" })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.goto("/research");
  await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.goto("/systems");
  await expect(page.getByRole("heading", { name: "Systems", level: 1 })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.goto("/portfolio");
  await expect(page.getByRole("heading", { name: "Paper Portfolio", level: 1 })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.goto("/ml-lab");
  await expect(page.getByRole("heading", { name: "ML Lab", level: 1 })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.goto("/nfl");
  await page.locator("section[aria-labelledby^='evt-']").first().getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: "Model estimate" })).toBeVisible();
  await expectNoHorizontalScroll(page);
});
