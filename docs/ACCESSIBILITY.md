# Accessibility

The target is WCAG 2.1 level AA. Status as of MS-037 (2026-10-19).

## Automated (every PR)

`apps/web/e2e/a11y.spec.ts` runs axe-core with the WCAG 2.1 A and AA rules on every page, against
the synthetic e2e database. Any violation fails CI.

The pages covered are the odds board, a game page, its line history, replay, signals, data,
ratings, a team page, matchups, model scorecard, projections and research.

The first run found two problems, both now fixed:

- **Colour contrast:** the "subtle" text colour (`#5d6b7d`) was 2.8–3.5:1 on the dark
  backgrounds. It is now `#808d9f`, which is at least 4.5:1 on the canvas, the surfaces and the
  accent/10 highlight rows. Secondary text on tinted rank cells now uses the foreground at 85%
  (`rankText` in `lib/ratings-view.ts`).
- **Links in running text** were told apart by colour alone (WCAG 1.4.1). Links inside paragraphs
  and list items are now underlined.

## Manual checks

- **Keyboard:**
  - A "Skip to main content" link is the first tab stop and moves focus to `<main>` (e2e test).
  - Every control is a native link, button, input or select, so it can be reached by keyboard and
    shows the browser's focus ring.
- **Structure:**
  - One `h1` per page.
  - Sections are labelled by their `h2` (`aria-labelledby`).
  - Tables have an `aria-label` and `scope` on their header cells.
  - `<html lang="en">`.
- **Charts:** charts are SVG figures with captions.
  - The rating-trend and season-outlook charts give each point's value in a `<title>` (for example
    "12 wins: 19%").
  - The line-history charts have only a caption.
  - The underlying numbers are also shown in tables or text on the same page.
- **Responsive:** every page fits a 390 px phone screen without horizontal page scrolling. Wide
  tables scroll inside their card (e2e `mobile.spec.ts`).
- **Colour is never the only signal:**
  - The best price is green and named in the legend.
  - Missing books are labelled "not in feed".
  - Ranks show the number as well as the shading.

## Not yet done

- **No full screen-reader pass.** No VoiceOver or NVDA walkthrough has been done. The charts have
  no summary sentence each, and the line-history points have no per-point text.
- **Reduced motion:** there are no animations, so nothing to reduce.
- **No light theme:** the site is dark-only, and contrast was checked for the dark theme.
