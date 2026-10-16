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
