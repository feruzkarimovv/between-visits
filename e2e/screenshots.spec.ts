import path from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * WS3 F19: README and deck screenshots, plus the 390 px width check on /sites and /sites/[id].
 * Config: screenshots.config.ts (1280 x 800). Synthetic data only: the seeded demo patients, a scripted replay and
 * the committed SIMULATED Site Signal study.
 *
 * Files (docs/screenshots/): today, call, nurse-ack, review, sae, sponsor, report-card, sites-funnel,
 * how-well-it-works, site-drilldown, site-inbox.
 */

type Role = "coordinator" | "investigator" | "sponsor" | "cra";

const SCENARIO = process.env.E2E_SCENARIO || "rosa_es_urgent";
const SPEED = process.env.E2E_REPLAY_SPEED || "4";
const SHOTS_DIR = process.env.SHOTS_DIR || path.resolve(__dirname, "..", "docs", "screenshots");

test.describe.configure({ mode: "serial" });

async function asRole(page: Page, role: Role): Promise<void> {
  const select = page.getByLabel("Demo role");
  await select.selectOption(role);
  await expect(select).toHaveValue(role);
}

/** Viewport screenshot without toasts or a hover state; `target` is scrolled to the top of the viewport first. */
async function shot(page: Page, name: string, target?: Locator, offset = 72): Promise<void> {
  await page.mouse.move(0, 799);
  if (target) {
    await target.evaluate((el, off) => {
      const top = el.getBoundingClientRect().top + window.scrollY - off; // below the sticky header
      window.scrollTo(0, Math.max(0, top));
    }, offset);
  } else {
    await page.evaluate(() => window.scrollTo(0, 0));
  }
  await page.addStyleTag({ content: "[data-sonner-toaster]{display:none !important}" });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(SHOTS_DIR, `${name}.png`), animations: "disabled", caret: "hide" });
}

test("clinical journey: today, live check-in, nurse ack, review, serious event, sponsor, report card", async ({ page }) => {
  await page.goto("/");
  await asRole(page, "coordinator");
  const replay = page.getByRole("button", { name: "Replay scenario" });
  await expect(replay).toBeVisible({ timeout: 60_000 });
  await page.locator("#scenario").selectOption(SCENARIO);
  await page.getByRole("radiogroup", { name: "Speed" }).getByText(`${SPEED}x`, { exact: true }).click();
  await expect(page.getByRole("radio", { name: `${SPEED}x` })).toBeChecked();
  await replay.click();

  // Live check-in: wait for the call to end and the post-call AE drafts to land.
  await page.waitForURL(/\/checkins\/ci_[^/?#]+$/);
  const checkinId = new URL(page.url()).pathname.split("/").pop() ?? "";
  const aeDraft = page.getByRole("listitem").filter({ has: page.getByText("AE", { exact: true }) }).first();
  await expect(async () => {
    try {
      await expect(aeDraft).toBeVisible({ timeout: 30_000 });
    } catch (e) {
      await page.reload();
      throw e;
    }
  }).toPass({ timeout: 240_000 });
  // The scripted call includes the on-call nurse's acknowledgment of the urgent page.
  await expect(page.getByRole("region", { name: "urgent escalation" }).getByText(/Acknowledged in/)).toBeVisible();
  await shot(page, "call");

  await page.goto("/escalations");
  await expect(page.getByText(/Acknowledged/).first()).toBeVisible();
  await shot(page, "nurse-ack");

  // Review queue for this check-in, before anything is confirmed (Spanish quote and labeled AI translation).
  await page.goto(`/checkins/${checkinId}`);
  await page.getByRole("link", { name: /^Review (\d+ drafts?|drafts)$/ }).click();
  await page.waitForURL((url) => url.pathname === "/review" && url.searchParams.get("checkin_id") === checkinId);
  const confirmButtons = page.getByRole("button", { name: "Confirm", exact: true });
  await expect(confirmButtons.first()).toBeVisible();
  await expect(page.getByText("AI translation, verify").first()).toBeVisible();
  await shot(page, "review");

  const drafts = await confirmButtons.count();
  for (let left = drafts; left > 0; left--) {
    await confirmButtons.first().click();
    await expect(confirmButtons).toHaveCount(left - 1);
  }
  await expect(page.getByText("Nothing waiting for review.")).toBeVisible();

  // Investigator assessment, then the serious-event report: sign and send.
  await asRole(page, "investigator");
  const assessment = page
    .locator("form")
    .filter({ has: page.getByRole("heading", { name: "Investigator assessment" }) })
    .first();
  await expect(assessment).toBeVisible();
  await assessment.getByRole("checkbox", { name: "Requires or prolongs hospitalization" }).check();
  await assessment.getByLabel("Relatedness to study drug").selectOption("possibly_related");
  await assessment.getByRole("button", { name: /^Sign as / }).click();
  const openReport = page.getByRole("link", { name: "Open serious-event report" }).first();
  await expect(openReport).toBeVisible();
  await openReport.click();
  await page.waitForURL(/\/sae\/sae_[^/?#]+$/);
  const saeId = new URL(page.url()).pathname.split("/").pop() ?? "";
  await page.getByRole("button", { name: /^Sign as Dr\./ }).click();
  await expect(page.getByRole("button", { name: "Signed" })).toBeVisible();
  const send = page.getByRole("button", { name: "Send to sponsor" });
  await expect(send).toBeEnabled();
  await send.click();
  await expect(page.getByRole("button", { name: "Sent to sponsor" })).toBeVisible();
  await shot(page, "sae");

  // Sponsor inbox, newest first, the report expanded.
  await page.getByRole("link", { name: "View in sponsor inbox" }).click();
  await page.waitForURL(/\/sponsor$/);
  await asRole(page, "sponsor");
  const inbox = page.locator("ul").filter({ has: page.locator("button[aria-expanded]") }).first();
  const top = inbox.locator("li").first();
  await expect(top).toBeVisible();
  await top.locator("button[aria-expanded]").click();
  await expect(top.getByText(saeId, { exact: true })).toBeVisible();
  await shot(page, "sponsor");

  // Report card (simulated-patient evaluation).
  await asRole(page, "coordinator");
  await page.goto("/report-card");
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  await page.waitForLoadState("networkidle");
  await shot(page, "report-card");

  // Today, after the call.
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Replay scenario" })).toBeVisible({ timeout: 60_000 });
  await page.waitForLoadState("networkidle");
  await shot(page, "today");
});

test("site signal: funnel, how well it works, drill-down with quotes, answered site query", async ({ page }) => {
  await page.goto("/sites");
  await asRole(page, "cra");
  const flagged = page.locator('tr[data-tier="watch"], tr[data-tier="look"]').first();
  await expect(flagged).toBeVisible({ timeout: 60_000 });
  await page.waitForLoadState("networkidle");
  await shot(page, "sites-funnel");

  await page.getByRole("tab", { name: "How well it works" }).click();
  await expect(page.getByRole("tabpanel")).toContainText("SIMULATED");
  await page.waitForLoadState("networkidle");
  await shot(page, "how-well-it-works");
  await page.getByRole("tab", { name: "Signal" }).click();

  const siteId = (await flagged.getAttribute("data-site")) ?? "";
  expect(siteId).toBeTruthy();
  await flagged.getByRole("link", { name: siteId }).click();
  await page.waitForURL(new RegExp(`/sites/${siteId}$`));
  await expect(page.getByRole("heading", { name: `Site ${siteId}` })).toBeVisible();
  const cite = page.getByRole("checkbox", { name: /^Cite .* in a site query$/ });
  await expect(cite.first()).toBeVisible();
  await page.waitForLoadState("networkidle");
  // The unmatched episodes with each patient's verbatim words (only these can be cited in a query).
  await page
    .getByRole("group", { name: "Filter episodes by status" })
    .getByRole("button", { name: /^Unmatched \d+$/ })
    .click();
  await shot(page, "site-drilldown", page.getByRole("heading", { name: "Episodes", exact: true }), 100);

  // CRA drafts and approves a templated query; the coordinator answers it with a coded response.
  const n = Math.min(2, await cite.count());
  for (let i = 0; i < n; i++) await cite.nth(i).check();
  await page.getByRole("button", { name: `Draft query (${n})` }).click();
  await expect(page.getByLabel("Query text (English)")).toBeVisible();
  const queryId = ((await page.locator("code", { hasText: /^sq_/ }).first().textContent()) ?? "").trim();
  expect(queryId).toMatch(/^sq_/);
  await page.getByRole("button", { name: "Approve and send" }).click();
  await expect(page.getByRole("button", { name: "Approve and send" })).toBeHidden();

  await page.goto("/site-inbox");
  await asRole(page, "coordinator");
  const card = page.locator("article").filter({ has: page.locator("code", { hasText: queryId }) });
  await expect(card).toBeVisible();
  await card.getByRole("radio").first().check();
  await card.getByRole("button", { name: "Send response" }).click();
  await expect(card.getByRole("button", { name: "Send response" })).toBeHidden();

  // The CRA's view of the answered query, before closing it.
  await asRole(page, "cra");
  await expect(card.getByRole("button", { name: "Close query" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await shot(page, "site-inbox", card);
});

test("390 px: no horizontal page scroll on /sites and /sites/[id]", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/sites");
  await asRole(page, "cra");
  const flagged = page.locator('tr[data-tier="watch"], tr[data-tier="look"]').first();
  await expect(flagged).toBeVisible({ timeout: 60_000 });
  await page.waitForLoadState("networkidle");
  const widths: Record<string, number> = {};
  const scrollWidth = () => page.evaluate(() => document.documentElement.scrollWidth);
  widths["/sites (Signal)"] = await scrollWidth();
  await page.getByRole("tab", { name: "How well it works" }).click();
  await expect(page.getByRole("tabpanel")).toContainText("SIMULATED");
  await page.waitForLoadState("networkidle");
  widths["/sites (How well it works)"] = await scrollWidth();
  await page.getByRole("tab", { name: "Signal" }).click();
  const siteId = (await flagged.getAttribute("data-site")) ?? "";
  await flagged.getByRole("link", { name: siteId }).click();
  await page.waitForURL(new RegExp(`/sites/${siteId}$`));
  await expect(page.getByRole("checkbox", { name: /^Cite .* in a site query$/ }).first()).toBeVisible();
  await page.waitForLoadState("networkidle");
  widths[`/sites/${siteId}`] = await scrollWidth();
  for (const [p, w] of Object.entries(widths)) console.log(`390px check: ${p} scrollWidth=${w}`);
  for (const w of Object.values(widths)) expect(w).toBeLessThanOrEqual(390);
});
