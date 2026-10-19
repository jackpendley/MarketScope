import { expect, test, type Page } from "@playwright/test";

const gameTables = (page: Page) => page.locator("section[aria-labelledby^='evt-']");

test.describe("odds board", () => {
  test("loads synthetic games grouped by date with an honest banner", async ({ page }) => {
    await page.goto("/nfl");
    await expect(page.getByRole("heading", { name: "NFL Odds Board" })).toBeVisible();
    await expect(page.getByText("Synthetic data: not real odds.")).toBeVisible();
    await expect(page.getByText(/collected periodically \(not live odds\)/)).toBeVisible();
    await expect(gameTables(page)).toHaveCount(3);
  });

  test("marks books that are missing from the feed", async ({ page }) => {
    await page.goto("/nfl");
    const first = gameTables(page).first();
    const caesars = first.getByRole("columnheader", { name: /Caesars/ });
    await expect(caesars).toContainText("not in feed");
  });

  test("filters by team, market, and sportsbook via the URL", async ({ page }) => {
    await page.goto("/nfl");
    await page.getByLabel("Team").fill("Packers");
    await page.getByLabel("Market").selectOption("spreads");
    await page.getByRole("checkbox", { name: "FanDuel" }).uncheck();
    await page.getByRole("button", { name: "Apply" }).click();

    await expect(page).toHaveURL(/q=Packers/);
    await expect(gameTables(page)).toHaveCount(1);
    const table = gameTables(page).first();
    await expect(table.getByRole("heading")).toContainText("Green Bay Packers");
    await expect(table.getByText("Moneyline")).toHaveCount(0);
    await expect(table.getByRole("columnheader", { name: /FanDuel/ })).toHaveCount(0);
    await expect(table.getByRole("columnheader", { name: /DraftKings/ })).toBeVisible();
  });

  test("shows an empty state when no team matches", async ({ page }) => {
    await page.goto("/nfl?q=Nonexistent");
    await expect(page.getByText(/No games match/)).toBeVisible();
  });
});

test.describe("game detail and history", () => {
  test("opens a game, shows coverage, and links to line history", async ({ page }) => {
    await page.goto("/nfl");
    await gameTables(page).first().getByRole("link").first().click();
    await expect(page).toHaveURL(/\/nfl\/games\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("heading", { name: "Feed coverage" })).toBeVisible();
    await expect(page.getByRole("row", { name: /Caesars williamhill_us/ })).toContainText(
      "never returned",
    );

    await page.getByRole("link", { name: /Open market replay/ }).click();
    await expect(page).toHaveURL(/\/history$/);
    await expect(page.getByRole("heading", { name: /Market replay/ })).toBeVisible();
  });

  test("renders stepped charts, a movement timeline, and gaps; legend toggles books", async ({
    page,
  }) => {
    await page.goto("/nfl");
    await gameTables(page).first().getByRole("link").first().click();
    await page.getByRole("link", { name: /Open market replay/ }).click();

    const charts = page.locator("figure");
    await expect(charts).toHaveCount(2); // spread line + price
    await expect(charts.first().locator(".recharts-line").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Movement timeline/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Data gaps" })).toBeVisible();

    const dk = page.getByRole("button", { name: "DraftKings", exact: true });
    const linesBefore = await charts.first().locator(".recharts-line").count();
    await dk.click();
    await expect(dk).toHaveAttribute("aria-pressed", "false");
    await expect(charts.first().locator(".recharts-line")).toHaveCount(linesBefore - 1);
  });

  test("moneyline history shows only the price chart", async ({ page }) => {
    await page.goto("/nfl");
    await gameTables(page).first().getByRole("link").first().click();
    await expect(page).toHaveURL(/\/nfl\/games\/[0-9a-f-]{36}$/);
    await page.goto(`${page.url()}/history?market=h2h`);
    await expect(page.locator("figure")).toHaveCount(1);
  });

  test("unknown games return the not-found page", async ({ page }) => {
    const res = await page.goto("/nfl/games/00000000-0000-4000-8000-000000000000");
    expect(res?.status()).toBe(404);
    await expect(page.getByRole("heading", { name: "Game not found" })).toBeVisible();
  });
});

test("data health endpoint reports the seeded runs", async ({ request }) => {
  const res = await request.get("/api/health/data");
  expect(res.ok()).toBe(true);
  const { data } = await res.json();
  expect(data.status).toBe("ok");
  expect(data.recentRuns.length).toBeGreaterThan(0);
});

test.describe("market replay", () => {
  async function openReplay(page: Page) {
    await page.goto("/replay");
    await expect(page.getByRole("heading", { name: "Market Replay" })).toBeVisible();
    const replayLinks = page.getByRole("link", { name: "Replay →", exact: true });
    await expect(replayLinks).toHaveCount(3);
    await replayLinks.first().click();
    await expect(page.getByRole("heading", { name: /Market replay/ })).toBeVisible();
  }

  test("stepping the cursor back changes the replay time and market state", async ({ page }) => {
    await openReplay(page);
    const time = page.getByTestId("replay-time");
    await expect(page.getByText("latest", { exact: true })).toBeVisible();
    const latest = await time.textContent();

    await page.getByRole("button", { name: "Previous snapshot" }).click();
    await expect(time).not.toHaveText(latest!);
    await expect(page.getByText(/Snapshot \d+ of \d+/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Latest" })).toBeEnabled();

    await page.getByRole("button", { name: "Latest" }).click();
    await expect(time).toHaveText(latest!);
  });

  test("the slider is keyboard operable", async ({ page }) => {
    await openReplay(page);
    const slider = page.getByRole("slider", { name: "Replay time" });
    const before = await page.getByTestId("replay-time").textContent();
    await slider.focus();
    await page.keyboard.press("Home");
    await expect(page.getByTestId("replay-time")).not.toHaveText(before!);
    // At the first snapshot most books have only just been observed: consensus may or may not
    // form, but the panel must always explain itself.
    await expect(page.getByTestId("replay-consensus")).toBeVisible();
  });

  test("clicking a movement moves the cursor to the end of its interval", async ({ page }) => {
    await openReplay(page);
    const entries = page.locator("ol li button");
    await expect(entries.first()).toBeVisible();
    const target = entries.nth(3);
    await target.click();
    await expect(target).toHaveAttribute("aria-current", "true");
  });
});

test.describe("signal lab", () => {
  test("lists evidence-backed signals with definitions and filters by type", async ({ page }) => {
    await page.goto("/signals");
    await expect(page.getByRole("heading", { name: "Signal Lab" })).toBeVisible();
    await expect(page.getByText("Synthetic data: not real odds.")).toBeVisible();
    await expect(page.getByText(/not betting advice/).first()).toBeVisible();
    const rows = page.locator("tbody tr");
    expect(await rows.count()).toBeGreaterThan(5);
    await expect(page.getByRole("heading", { name: /Definitions/ })).toBeVisible();

    await page.getByLabel("Signal type").selectOption("line_move");
    await page.getByRole("button", { name: "Apply" }).click();
    await expect(page).toHaveURL(/type=line_move/);
    const badges = page.locator("[data-signal-type]");
    await expect(badges.first()).toBeVisible();
    for (const t of await badges.evaluateAll((els) =>
      els.map((e) => e.getAttribute("data-signal-type")),
    )) {
      expect(t).toBe("line_move");
    }
  });

  test("a signal's replay link opens the replay at the signal's moment", async ({ page }) => {
    await page.goto("/signals?type=line_move");
    const link = page.getByRole("link", { name: "Replay →" }).first();
    const href = await link.getAttribute("href");
    const at = new URL(href!, "http://x").searchParams.get("at")!;
    await link.click();
    await expect(page.getByRole("heading", { name: /Market replay/ })).toBeVisible();
    // The cursor starts on the snapshot at (or just before) the signal time, not "latest".
    const expected = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    }).format(new Date(at));
    await expect(page.getByTestId("replay-time")).toHaveText(expected);
  });

  test("game pages show recent signals", async ({ page }) => {
    await page.goto("/nfl");
    await page
      .locator("section[aria-labelledby^='evt-']")
      .first()
      .getByRole("link")
      .first()
      .click();
    await expect(page.getByRole("heading", { name: "Recent signals" })).toBeVisible();
    await expect(page.getByRole("link", { name: /All signals for this game/ })).toBeVisible();
  });
});

test.describe("data coverage", () => {
  test("shows live collection health and per-book coverage for every seeded game", async ({
    page,
  }) => {
    await page.goto("/data");
    await expect(page.getByRole("heading", { name: "Data Coverage" })).toBeVisible();
    await expect(page.getByText("Synthetic data: not real odds.")).toBeVisible();
    await expect(page.locator("[data-status='ok']")).toBeVisible();

    const table = page.getByRole("table", { name: /Pregame spread coverage/ });
    await expect(table.locator("tbody tr")).toHaveCount(3);
    await expect(table.getByRole("columnheader", { name: /Pinnacle/ })).toBeVisible();
    // Coverage is text, not color alone: every cell is a percentage or an em dash.
    const cells = await table.locator("tbody td span").allInnerTexts();
    expect(cells.length).toBeGreaterThan(0);
    for (const c of cells) expect(c).toMatch(/^(\d{1,3}%|—)$/);

    await table.getByRole("link", { name: "Replay →" }).first().click();
    await expect(page.getByRole("heading", { name: /Market replay/ })).toBeVisible();
  });
});

test.describe("research", () => {
  test("lists the pre-registered studies with their status", async ({ page }) => {
    await page.goto("/nfl");
    await page
      .getByRole("navigation", { name: "Primary" })
      .getByRole("link", { name: "Research" })
      .click();
    await expect(page.getByRole("heading", { name: "Research", level: 1 })).toBeVisible();
    await expect(page.locator("article[aria-labelledby^='study-']")).toHaveCount(9);
    await expect(page.getByRole("link", { name: "pre-registered" })).toHaveAttribute(
      "href",
      /PREREGISTRATION\.md$/,
    );
    await expect(page.getByRole("article", { name: /R2 Injury news/ })).toContainText(
      "waiting for data",
    );
  });
});

test.describe("ml lab", () => {
  test("lists the experiments with their verdicts", async ({ page }) => {
    await page.goto("/nfl");
    await page
      .getByRole("navigation", { name: "Primary" })
      .getByRole("link", { name: "ML Lab" })
      .click();
    await expect(page.getByRole("heading", { name: "ML Lab", level: 1 })).toBeVisible();
    await expect(page.locator("article[aria-labelledby^='exp-']")).toHaveCount(4);
    await expect(page.getByRole("article", { name: /MS-036b/ })).toContainText("worse");
    await expect(page.getByRole("table", { name: "Largest model coefficients" })).toBeVisible();
  });
});
