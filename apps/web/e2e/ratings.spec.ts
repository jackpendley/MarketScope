import { expect, test } from "@playwright/test";

// The e2e database holds SYNTHETIC ratings (model_version "synthetic-demo", see
// apps/collector/src/synthetic-ratings.ts): eight teams, weekly snapshots 0-3.
test.describe("ratings", () => {
  test("shows the KenPom table with a synthetic banner and labeled model estimates", async ({
    page,
  }) => {
    await page.goto("/ratings");
    await expect(page.getByRole("heading", { name: "MarketScope Ratings" })).toBeVisible();
    await expect(
      page.getByText("Synthetic ratings: demo data, not real model output."),
    ).toBeVisible();
    await expect(page.getByText("model estimate", { exact: false }).first()).toBeVisible();
    const rows = page.getByRole("table").locator("tbody tr");
    await expect(rows).toHaveCount(8);
    await expect(rows.first()).toContainText("Buffalo Bills"); // synthetic AdjEM #1 after week 3
  });

  test("sorts by a column and filters by conference through the URL", async ({ page }) => {
    await page.goto("/ratings");
    await page.getByRole("columnheader", { name: "AdjPace" }).getByRole("link").click();
    await expect(page).toHaveURL(/sort=adjPace/);
    await expect(page.getByRole("table").locator("tbody tr").first()).toContainText(
      "Dallas Cowboys",
    ); // AdjPace #1
    await page.goto("/ratings?conf=NFC");
    await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(2);
  });

  test("the week selector shows an earlier snapshot", async ({ page }) => {
    await page.goto("/ratings");
    await page.getByLabel("Ratings after").selectOption({ label: "Preseason" });
    await page.getByRole("button", { name: "Show" }).click();
    await expect(page).toHaveURL(/week=0/);
    await expect(page.getByText(/· Preseason ·/)).toBeVisible();
  });

  test("a team page shows ratings, the trend, Five Factors, schedule estimates and staff", async ({
    page,
  }) => {
    await page.goto("/ratings");
    await page.getByRole("link", { name: "Kansas City Chiefs" }).click();
    await expect(page.getByRole("heading", { name: /Kansas City Chiefs/ })).toBeVisible();
    await expect(page.getByRole("img", { name: /AdjEM by week/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Five Factors/ })).toBeVisible();
    const schedule = page.locator("section[aria-labelledby='schedule'] tbody tr");
    await expect(schedule).toHaveCount(4);
    await expect(schedule.last()).toContainText("%"); // the upcoming game's model estimate
    await expect(page.getByText("Synthetic Coach 1")).toBeVisible();
  });

  test("unknown teams return the not-found page", async ({ page }) => {
    const res = await page.goto("/teams/XYZ");
    expect(res?.status()).toBe(404);
  });
});

test("the ratings API returns the latest snapshot in the standard envelope", async ({
  request,
}) => {
  const res = await request.get("/api/ratings");
  expect(res.ok()).toBe(true);
  const body = await res.json();
  expect(body.meta).toMatchObject({ count: 8, modelVersion: "synthetic-demo", week: 3 });
  expect(body.data[0]).toMatchObject({ team: "BUF", adjEmRank: 1 });
});
