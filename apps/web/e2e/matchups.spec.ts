import { expect, test } from "@playwright/test";

// The e2e database holds SYNTHETIC games, ratings and estimates (model_version "synthetic-demo",
// apps/collector/src/synthetic-ratings.ts): weeks 1-3 final, week 4 upcoming. Week 4's MIA@BUF and
// PHI@DAL link to the synthetic odds events of the same teams.
test.describe("matchups and model scorecard", () => {
  test("the matchups page shows the upcoming week's labeled model estimates", async ({ page }) => {
    await page.goto("/matchups");
    await expect(page.getByRole("heading", { name: "Matchups" })).toBeVisible();
    await expect(
      page.getByText("Synthetic estimates: demo data, not real model output."),
    ).toBeVisible();
    await expect(page.getByText("model estimate", { exact: false }).first()).toBeVisible();
    const cards = page.locator("article");
    await expect(cards).toHaveCount(4);

    const buf = page.getByRole("article", { name: "MIA at BUF" });
    await expect(buf.getByText("Consensus now")).toBeVisible();
    await expect(buf.getByText(/^BUF −\d/)).toBeVisible(); // board consensus, posted sign
    await expect(buf.getByRole("table", { name: /contributions, BUF vs MIA/ })).toBeVisible();
    await expect(buf.getByText("Synthetic QB BUF")).toBeVisible();
    await expect(page.getByText("64% to play")).toBeVisible();
  });

  test("an earlier week shows finals against the estimate and the close", async ({ page }) => {
    await page.goto("/matchups");
    await page.getByLabel("Week").selectOption({ label: "Week 1" });
    await page.getByRole("button", { name: "Show" }).click();
    await expect(page).toHaveURL(/week=1/);
    await expect(page.getByText("Close (nflverse)").first()).toBeVisible();
    await expect(page.getByText(/missed by \d/).first()).toBeVisible();
  });

  test("the game page shows the model panel next to the consensus", async ({ page }) => {
    await page.goto("/matchups");
    await page
      .getByRole("article", { name: "MIA at BUF" })
      .getByRole("link", { name: /Odds and line history/ })
      .click();
    await expect(page.getByRole("heading", { name: "Model estimate" })).toBeVisible();
    await expect(
      page.getByText("Synthetic estimate: demo data, not real model output."),
    ).toBeVisible();
    await expect(page.getByRole("table", { name: /contributions, BUF vs MIA/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /Week 4 matchups/ })).toBeVisible();
  });

  test("the scorecard shows the forward test and the one-time test record", async ({ page }) => {
    await page.goto("/model");
    await expect(page.getByRole("heading", { name: "Model scorecard" })).toBeVisible();
    await expect(
      page.getByText("Synthetic scorecard: demo data, not real model output."),
    ).toBeVisible();
    await expect(page.getByText(/12 games final, 4 awaiting a result/)).toBeVisible();
    const live = page.getByRole("table", { name: "Live forward test vs the close" });
    await expect(live.getByRole("row", { name: /Margin MAE/ })).toContainText("12");
    await expect(
      page.getByRole("table", { name: "Margin error by week" }).locator("tbody tr"),
    ).toHaveCount(3);
    const record = page.getByRole("table", { name: /test record/ });
    await expect(record.locator("tbody tr")).toHaveCount(3);
    await expect(record.locator("tbody tr").first()).toContainText("synthetic-demo");
  });
});

test("the matchups and model APIs return model estimates in the standard envelope", async ({
  request,
}) => {
  const m = await request.get("/api/matchups");
  expect(m.ok()).toBe(true);
  const body = await m.json();
  expect(body.meta).toMatchObject({ count: 4, modelVersion: "synthetic-demo", week: 4 });
  expect(body.data[0].estimate).toMatchObject({ homeQbP: 1 });

  const s = await request.get("/api/model");
  expect(s.ok()).toBe(true);
  const model = await s.json();
  expect(model.data.scorecard.games).toBe(12);
  expect(model.data.pending).toBe(4);
  expect(model.data.runs[0].runKind).toBe("test");
});
