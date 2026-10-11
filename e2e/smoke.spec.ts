import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * WS0 R10 end-to-end smoke against `make demo` (docs/workstreams/WS0-readiness.md R10). Two journeys, driven only
 * through the dashboard, as the demo roles from the top-bar switch (demo identity headers, no authentication):
 *
 *   1. Replay → review confirm → investigator → SAE sign → send → sponsor inbox.
 *   2. As CRA: /sites → a site at Look or Watch → select unmatched episodes → draft query → edit → approve.
 *      As coordinator: /site-inbox → respond with a code. As CRA: close. /audit shows the five site_query.* rows.
 */

type Role = "coordinator" | "investigator" | "sponsor" | "cra";

const SCENARIO = process.env.E2E_SCENARIO || "rosa_es_urgent";
const SPEED = process.env.E2E_REPLAY_SPEED || "4";

/** The five audit actions of a site query's life cycle (docs/03 §5.4, §5.8). */
const SITE_QUERY_ACTIONS = [
  "site_query.drafted",
  "site_query.edited",
  "site_query.approved",
  "site_query.answered",
  "site_query.closed",
] as const;

/** Switch the demo identity with the top-bar select (it re-sends X-BV-Role and refetches every query). */
async function asRole(page: Page, role: Role): Promise<void> {
  const select = page.getByLabel("Demo role");
  await select.selectOption(role);
  await expect(select).toHaveValue(role);
}

/** Text of an element, trimmed; fails if it is empty. */
async function textOf(locator: Locator): Promise<string> {
  const text = ((await locator.textContent()) ?? "").trim();
  expect(text, "expected a non-empty text").not.toBe("");
  return text;
}

test("serious event: replay, review, investigator, sign and send, sponsor inbox", async ({ page }) => {
  // Today, as the coordinator: replay the scripted call.
  await page.goto("/");
  await asRole(page, "coordinator");
  const replay = page.getByRole("button", { name: "Replay scenario" });
  await expect(replay, "the Replay control shows only when /api/health says demo_mode").toBeVisible({ timeout: 60_000 });
  await page.locator("#scenario").selectOption(SCENARIO);
  // The speed radios are visually hidden inside their labels: click the label, then check the radio.
  await page.getByRole("radiogroup", { name: "Speed" }).getByText(`${SPEED}x`, { exact: true }).click();
  await expect(page.getByRole("radio", { name: `${SPEED}x` })).toBeChecked();
  await replay.click();

  // Live check-in page. A medication draft can land during the call; the side-effect (AE) drafts come from the
  // post-call pipeline once the replay ends, so wait for an AE row in "Drafts created".
  await page.waitForURL(/\/checkins\/ci_[^/?#]+$/);
  const checkinId = new URL(page.url()).pathname.split("/").pop() ?? "";
  const aeDraft = page.getByRole("listitem").filter({ has: page.getByText("AE", { exact: true }) }).first();
  await expect(async () => {
    try {
      await expect(aeDraft).toBeVisible({ timeout: 30_000 });
    } catch (e) {
      // The page stops polling 30 s after the call ends; a reload picks up drafts that land later.
      await page.reload();
      throw e;
    }
  }).toPass({ timeout: 240_000 });
  await page.getByRole("link", { name: /^Review (\d+ drafts?|drafts)$/ }).click();

  // Review queue for this check-in: the coordinator confirms every draft.
  await page.waitForURL((url) => url.pathname === "/review" && url.searchParams.get("checkin_id") === checkinId);
  const confirmButtons = page.getByRole("button", { name: "Confirm", exact: true });
  await expect(confirmButtons.first()).toBeVisible();
  const drafts = await confirmButtons.count();
  for (let left = drafts; left > 0; left--) {
    await confirmButtons.first().click();
    await expect(confirmButtons).toHaveCount(left - 1);
  }
  await expect(page.getByText("Nothing waiting for review.")).toBeVisible();

  // Investigator: confirmed side effects wait for the seriousness and relatedness assessment.
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

  // Serious-event report: the investigator signs, then sends it to the sponsor.
  await page.waitForURL(/\/sae\/sae_[^/?#]+$/);
  const saeId = new URL(page.url()).pathname.split("/").pop() ?? "";
  await page.getByRole("button", { name: /^Sign as Dr\./ }).click();
  await expect(page.getByRole("button", { name: "Signed" })).toBeVisible();
  const send = page.getByRole("button", { name: "Send to sponsor" });
  await expect(send).toBeEnabled();
  await send.click();
  await expect(page.getByRole("button", { name: "Sent to sponsor" })).toBeVisible();
  await page.getByRole("link", { name: "View in sponsor inbox" }).click();

  // Sponsor inbox, newest first: this report is the top row.
  await page.waitForURL(/\/sponsor$/);
  await asRole(page, "sponsor");
  const inbox = page.locator("ul").filter({ has: page.locator("button[aria-expanded]") }).first();
  const top = inbox.locator("li").first();
  await expect(top).toBeVisible();
  await top.locator("button[aria-expanded]").click();
  await expect(top.getByText(saeId, { exact: true })).toBeVisible();
  await expect(top.getByText("Yes (4 of 4)")).toBeVisible();
});

test("site signal: CRA query from a Look or Watch site, coordinator answers, CRA closes, five audit rows", async ({ page }) => {
  // CRA: the ranked sites, then the first site at Watch or Look.
  await page.goto("/sites");
  await asRole(page, "cra");
  const flagged = page.locator('tr[data-tier="watch"], tr[data-tier="look"]').first();
  await expect(flagged, "the committed study has at least one site at Look or Watch").toBeVisible({ timeout: 60_000 });
  const siteId = await flagged.getAttribute("data-site");
  expect(siteId).toBeTruthy();
  await flagged.getByRole("link", { name: siteId ?? "" }).click();
  await page.waitForURL(new RegExp(`/sites/${siteId}$`));
  await expect(page.getByRole("heading", { name: `Site ${siteId}` })).toBeVisible();

  // Select unmatched episodes (only those can be cited) and draft the templated query.
  const cite = page.getByRole("checkbox", { name: /^Cite .* in a site query$/ });
  await expect(cite.first()).toBeVisible();
  const n = Math.min(2, await cite.count());
  for (let i = 0; i < n; i++) await cite.nth(i).check();
  await page.getByRole("button", { name: `Draft query (${n})` }).click();

  // Draft editor: edit the text (site_query.edited), then approve and send (site_query.approved).
  const body = page.getByLabel("Query text (English)");
  await expect(body).toBeVisible();
  const queryId = await textOf(page.locator("code", { hasText: /^sq_/ }).first());
  expect(queryId).toMatch(/^sq_/);
  await body.fill(`${await body.inputValue()}\n\nPlease answer in the site inbox.`);
  await page.getByLabel("Edit note (optional, kept in the audit row)").fill("Smoke test edit");
  await page.getByRole("button", { name: "Save edit" }).click();
  await expect(page.getByText("edited", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Approve and send" }).click();
  await expect(page.getByRole("button", { name: "Approve and send" })).toBeHidden();

  // Coordinator: the query is in the mock site inbox; answer it with a coded response.
  await page.goto("/site-inbox");
  await asRole(page, "coordinator");
  const card = page.locator("article").filter({ has: page.locator("code", { hasText: queryId }) });
  await expect(card).toBeVisible();
  await card.getByRole("radio").first().check();
  await card.getByRole("button", { name: "Send response" }).click();
  await expect(card.getByRole("button", { name: "Send response" })).toBeHidden();

  // CRA: close the answered query.
  await asRole(page, "cra");
  await card.getByRole("button", { name: "Close query" }).click();
  await card.getByRole("button", { name: "Confirm close" }).click();
  await expect(card.getByRole("button", { name: "Close query" })).toBeHidden();
  await expect(card.getByText("Closed", { exact: true }).first()).toBeVisible();

  // Audit trail for this query: exactly the five site_query.* rows.
  await page.goto(`/audit?entity_id=${encodeURIComponent(queryId)}`);
  const rows = page.locator("tbody tr").filter({ has: page.locator("code", { hasText: /^site_query\./ }) });
  await expect(rows).toHaveCount(SITE_QUERY_ACTIONS.length);
  const actions = (await rows.locator("code").allTextContents()).map((s) => s.trim()).sort();
  expect(actions).toEqual([...SITE_QUERY_ACTIONS].sort());
});
