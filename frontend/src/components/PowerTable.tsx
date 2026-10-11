import type { ReactNode } from "react";
import { FlaskConical, Gauge, ShieldAlert, SlidersHorizontal, Target } from "lucide-react";
import type { DataOrigin, SiteSignalValidation } from "@/lib/types";
import {
  asArr,
  asNum,
  asRec,
  asStr,
  fmtCi,
  fmtCount,
  fmtParam,
  fmtProp,
  fmtSe,
  pick,
  readRateSe,
  type Rec,
  type RateSe,
} from "@/lib/summary";
import { Card, CardHeader, Table, Td, Th, cn } from "@/components/ui/primitives";
import { DataOriginBadge } from "@/components/DataOriginBadge";

/**
 * "How well it works" blocks of `/sites` (WS3 F16; docs/06 § Site Signal pages, docs/10 §6, docs/11 §12).
 * Every number is read from `GET /api/site-signal/validation` (validation/site_signal/summary.json) and rounded
 * here for display only (docs/11 §15 rule 6). This file holds no result literals: the planted capture losses,
 * targets, replicate counts and statuses all come from the JSON.
 */

/** The three indicators shown in the UI (docs/10 §6). The AE-to-report ratio ablation stays in report.md. */
export const INDICATORS: { id: string; name: string }[] = [
  { id: "discordance", name: "Capture discordance" },
  { id: "rate_kri", name: "Rate KRI" },
  { id: "simaerep_classic", name: "simaerep classic (legacy)" },
];
const INDICATOR_IDS = INDICATORS.map((i) => i.id);

function indicatorName(id: string): string {
  return INDICATORS.find((i) => i.id === id)?.name ?? id;
}

function originOf(v: SiteSignalValidation): DataOrigin {
  return v.data_origin ?? "SIMULATED";
}

// ------------------------------------------------------------------ cells

/** Estimate with its MC SE (docs/11 §15 rule 3), optional CI on a second line. */
function Est({ r, ci = false }: { r: RateSe | null; ci?: boolean }) {
  if (!r || r.rate === null) return <span className="text-ink-subtle">—</span>;
  return (
    <span className="tabular whitespace-nowrap">
      <span className="font-medium text-ink">{fmtProp(r.rate)}</span>{" "}
      <span className="text-ink-subtle">(MC SE {fmtSe(r.mcSe)})</span>
      {ci && r.ci ? (
        <span className="block text-sm text-ink-subtle" title={r.ciMethod ?? undefined}>
          95% CI {fmtCi(r.ci)}
        </span>
      ) : null}
    </span>
  );
}

function BlockCard({
  title,
  icon,
  subtitle,
  origin,
  children,
  id,
}: {
  title: ReactNode;
  icon: ReactNode;
  subtitle?: ReactNode;
  origin: DataOrigin;
  children: ReactNode;
  id?: string;
}) {
  return (
    <Card id={id} className="overflow-hidden">
      <CardHeader title={title} icon={icon} subtitle={subtitle} actions={<DataOriginBadge origin={origin} />} className="flex-wrap" />
      {children}
    </Card>
  );
}

function Missing({ what }: { what: string }) {
  return <p className="px-5 py-4 text-sm text-ink-muted">{what} is not in this validation summary.</p>;
}

// ------------------------------------------------------------------ power rows

interface PowerCell {
  power: number | null;
  mcSe: number | null;
  neverAssigned: boolean;
}

interface PowerLine {
  key: string;
  cell: string;
  indicator: string;
  f: number;
  pComputed: number | null;
  look: PowerCell | null;
  watch: PowerCell | null;
}

function cellLabel(r: Rec): string {
  return `${fmtParam(r.n_sites)} sites, ${fmtParam(r.patients_per_site)} patients per site, μ = ${fmtParam(r.mu)}`;
}

/** Merge the `look` and `watch` rows of one (cell, indicator, f) into one line; indicators in UI order, then f. */
function readPowerLines(rows: unknown[]): PowerLine[] {
  const lines = new Map<string, PowerLine>();
  for (const raw of rows) {
    const r = asRec(raw);
    if (!r) continue;
    const indicator = asStr(r.indicator);
    const tier = asStr(r.tier);
    const f = asNum(r.f);
    if (!indicator || !tier || f === null || !INDICATOR_IDS.includes(indicator)) continue;
    const cell = cellLabel(r);
    const key = `${cell}|${indicator}|${f}`;
    let line = lines.get(key);
    if (!line) {
      line = { key, cell, indicator, f, pComputed: asNum(r.p_computed), look: null, watch: null };
      lines.set(key, line);
    }
    const c: PowerCell = { power: asNum(r.power), mcSe: asNum(r.mc_se), neverAssigned: r.threshold_never_assigned === true };
    if (tier === "look") line.look = c;
    else if (tier === "watch") line.watch = c;
    if (line.pComputed === null) line.pComputed = asNum(r.p_computed);
  }
  return [...lines.values()].sort(
    (a, b) =>
      a.cell.localeCompare(b.cell) || INDICATOR_IDS.indexOf(a.indicator) - INDICATOR_IDS.indexOf(b.indicator) || a.f - b.f,
  );
}

/**
 * The `sap-v1` design rows of `power[]`: rows marked `design_row`; else rows matching `design`; else every row
 * (the B16b fixture has no design row), with the cell shown so nothing is passed off as the design.
 */
function designPowerRows(v: SiteSignalValidation): { rows: unknown[]; isDesign: boolean } {
  const rows = asArr(v.power);
  const marked = rows.filter((r) => asRec(r)?.design_row === true);
  if (marked.length) return { rows: marked, isDesign: true };
  const d = asRec(v.design);
  if (d) {
    const match = rows.filter((raw) => {
      const r = asRec(raw);
      return !!r && r.n_sites === d.n_sites && r.mu === d.mu && fmtParam(r.patients_per_site) === fmtParam(d.patients_per_site);
    });
    if (match.length) return { rows: match, isDesign: true };
  }
  return { rows, isDesign: false };
}

function PowerCellView({ c }: { c: PowerCell | null }) {
  if (!c || c.power === null) return <span className="text-ink-subtle">—</span>;
  return (
    <span className="tabular whitespace-nowrap">
      <span className="font-medium text-ink">{fmtProp(c.power)}</span>{" "}
      <span className="text-ink-subtle">(MC SE {fmtSe(c.mcSe)})</span>
      {c.neverAssigned ? <span className="block text-sm text-ink-subtle">threshold never assigned</span> : null}
    </span>
  );
}

function PowerLinesTable({ lines, grossF, caption }: { lines: PowerLine[]; grossF: number | null; caption: string }) {
  const multiCell = new Set(lines.map((l) => l.cell)).size > 1;
  return (
    <Table className="relative">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          {multiCell ? <Th>Cell</Th> : null}
          <Th>Indicator</Th>
          <Th className="text-right">Planted capture loss f</Th>
          <Th>Flagged: Look or Watch</Th>
          <Th>Flagged: Watch</Th>
          <Th className="text-right">Planted site computed</Th>
        </tr>
      </thead>
      <tbody>
        {lines.map((l, i) => {
          const firstOfIndicator = i === 0 || lines[i - 1].indicator !== l.indicator || lines[i - 1].cell !== l.cell;
          return (
            <tr key={l.key} data-indicator={l.indicator} className={cn(firstOfIndicator && i > 0 && "border-t-2 border-line-strong")}>
              {multiCell ? <Td className="min-w-56 text-ink-muted">{l.cell}</Td> : null}
              <Td className="min-w-44 font-medium text-ink">{firstOfIndicator ? indicatorName(l.indicator) : ""}</Td>
              <Td className="tabular text-right whitespace-nowrap">
                {fmtProp(l.f)}
                {grossF !== null && l.f === grossF ? <span className="ml-1 text-ink-subtle">(gross)</span> : null}
              </Td>
              <Td>
                <PowerCellView c={l.look} />
              </Td>
              <Td>
                <PowerCellView c={l.watch} />
              </Td>
              <Td className="tabular text-right">{fmtProp(l.pComputed)}</Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

/** Power at both tiers for the three indicators at the `sap-v1` design, every planted f in the JSON (the 25% and 50% rows included). */
export function PowerTable({ v }: { v: SiteSignalValidation }) {
  const { rows, isDesign } = designPowerRows(v);
  const lines = readPowerLines(rows);
  const grossF = asNum(pick(v.design, "gross_f"));
  const reps = asNum(asRec(rows[0])?.reps);
  const design = asRec(v.design);
  return (
    <BlockCard
      id="power"
      title="Power: one planted site per study"
      icon={<Target className="size-4" aria-hidden />}
      origin={originOf(v)}
      subtitle={
        isDesign && design ? (
          <>
            At the sap-v1 design: {cellLabel(design)}
            {reps !== null ? <>, {fmtCount(reps)} simulated studies per row</> : null}.
          </>
        ) : (
          "No design row is marked in this summary; every grid row is listed with its cell."
        )
      }
    >
      <p className="border-b border-line bg-gray-50/70 px-5 py-3 text-sm leading-6 text-ink-muted">
        Share of simulated studies in which the one planted site with capture loss <i>f</i> was flagged, with the frozen sap-v1
        thresholds. Watch is nested in Look, so &ldquo;Look or Watch&rdquo; counts a flag at either tier. A planted site that is
        not computed counts as missed; &ldquo;Planted site computed&rdquo; is how often it was computed at all, which caps power.
        Moderate gaps are mostly missed at the Watch tier, and this table shows it.
      </p>
      {lines.length ? (
        <PowerLinesTable lines={lines} grossF={grossF} caption="Power at both tiers by indicator and planted capture loss" />
      ) : (
        <Missing what="Power" />
      )}
    </BlockCard>
  );
}

// ------------------------------------------------------------------ null false-flag rates

function nullBlock(v: SiteSignalValidation, id: string): unknown {
  const fromComparators = pick(v.null, "comparators", id);
  if (fromComparators !== undefined) return fromComparators;
  return (asStr(pick(v.null, "indicator")) ?? "discordance") === id ? v.null : undefined;
}

function StatusLine({ label, status }: { label: string; status: string | null }) {
  if (!status) return null;
  return (
    <span className="block whitespace-nowrap">
      <span className="text-ink-subtle">{label}:</span>{" "}
      <span className={cn(status === "failure" ? "font-semibold text-ink" : "text-ink-muted")}>{status}</span>
    </span>
  );
}

/** "<=12" -> "≤ 12", "13-16" -> "13–16" (the K bin labels of summary.json, display only). */
function kBinLabel(bin: string | null): string {
  return bin === null ? "—" : bin.replace("<=", "≤ ").replace(">=", "≥ ").replace("-", "–");
}

/** Capture discordance's null rates by number of computed sites K (docs/11 §12.1, `null.by_k_bin`). */
function NullByKBin({ v }: { v: SiteSignalValidation }) {
  const bins = asArr(pick(v.null, "by_k_bin"));
  if (!bins.length) return null;
  return (
    <>
      <h3 className="border-t border-line px-5 pt-4 pb-1 text-sm font-semibold text-ink">Capture discordance by number of computed sites K</h3>
      <p className="px-5 pb-2 text-sm leading-6 text-ink-muted">
        The Watch target holds on average over the null studies. The Watch threshold is one study-wide cut-off, so a study
        with more computed sites has more chances of a false Watch flag.
      </p>
      <Table>
        <caption className="sr-only">Null false-flag rates of capture discordance by number of computed sites, with Monte Carlo standard errors</caption>
        <thead>
          <tr>
            <Th>Computed sites K</Th>
            <Th>Null studies</Th>
            <Th>Any Watch per study</Th>
            <Th>False Look flags per study</Th>
            <Th>False Look per site</Th>
          </tr>
        </thead>
        <tbody>
          {bins.map((b, i) => {
            const bin = asStr(pick(b, "k_bin"));
            return (
              <tr key={bin ?? i} data-k-bin={bin ?? undefined}>
                <Td className="font-medium whitespace-nowrap text-ink">{kBinLabel(bin)}</Td>
                <Td className="tabular">{fmtCount(asNum(pick(b, "n_studies")))}</Td>
                <Td>
                  <Est r={readRateSe(pick(b, "watch_fwer"))} ci />
                </Td>
                <Td>
                  <Est r={readRateSe(pick(b, "look_per_study"))} />
                </Td>
                <Td>
                  <Est r={readRateSe(pick(b, "look_per_site"))} />
                </Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
    </>
  );
}

/** Null false-flag rates of every indicator with MC SE and the REQ-023 outcome (docs/11 §12.1). */
export function NullRatesTable({ v }: { v: SiteSignalValidation }) {
  const acc = pick(v.null, "acceptance");
  const nominalLook = asNum(pick(acc, "nominal", "look"));
  const nominalWatch = asNum(pick(acc, "nominal", "watch"));
  const r = asNum(pick(v.null, "r"));
  const computedMean = asNum(pick(v.null, "computability", "mean_computed_sites"));
  const computedSe = asNum(pick(v.null, "computability", "mean_computed_sites_mc_se"));
  const rule = asStr(pick(acc, "rule"));
  const sizeRule = asStr(pick(acc, "size_rule"));

  return (
    <BlockCard
      id="null"
      title="False flags under the null"
      icon={<ShieldAlert className="size-4" aria-hidden />}
      origin={originOf(v)}
      subtitle={
        <>
          {r !== null ? <>{fmtCount(r)} fresh simulated studies with no planted site, </> : "Simulated studies with no planted site, "}
          scored with the frozen sap-v1 thresholds.
          {nominalLook !== null && nominalWatch !== null ? (
            <>
              {" "}
              Targets: Look {fmtProp(nominalLook)} per site; any Watch in {fmtProp(nominalWatch)} of studies, on average over
              the design (by number of computed sites below).
            </>
          ) : null}
        </>
      }
    >
      {asRec(v.null) ? (
        <>
          <Table className="relative">
            <caption className="sr-only">Null false-flag rates by indicator, with Monte Carlo standard errors</caption>
            <thead>
              <tr>
                <Th>Indicator</Th>
                <Th>False Look per site</Th>
                <Th>By site size (tertiles of E)</Th>
                <Th>False Look flags per study</Th>
                <Th>Any Watch per study</Th>
                <Th>Check (REQ-023)</Th>
              </tr>
            </thead>
            <tbody>
              {INDICATORS.map(({ id, name }) => {
                const b = nullBlock(v, id);
                if (!asRec(b)) {
                  return (
                    <tr key={id}>
                      <Td className="min-w-44 font-medium text-ink">{name}</Td>
                      <Td colSpan={5} className="text-ink-subtle">
                        Not in this summary
                      </Td>
                    </tr>
                  );
                }
                const tertiles = asArr(pick(b, "look_per_site_by_e_tertile"));
                const status = pick(acc, "by_indicator", id);
                return (
                  <tr key={id} data-indicator={id}>
                    <Td className="min-w-44 font-medium text-ink">{name}</Td>
                    <Td>
                      <Est r={readRateSe(pick(b, "look_per_site"))} ci />
                    </Td>
                    <Td>
                      {tertiles.length ? (
                        tertiles.map((t, i) => {
                          const tr = readRateSe(t);
                          return (
                            <span key={i} className="tabular block whitespace-nowrap">
                              <span className="text-ink-subtle">{fmtCount(asNum(pick(t, "tertile")) ?? i + 1)}:</span>{" "}
                              <span className="font-medium text-ink">{fmtProp(tr?.rate)}</span>{" "}
                              <span className="text-ink-subtle">(MC SE {fmtSe(tr?.mcSe)})</span>
                            </span>
                          );
                        })
                      ) : (
                        <span className="text-ink-subtle">—</span>
                      )}
                    </Td>
                    <Td>
                      <Est r={readRateSe(pick(b, "look_per_study"))} />
                    </Td>
                    <Td>
                      <Est r={readRateSe(pick(b, "watch_fwer"))} ci />
                    </Td>
                    <Td className="text-sm">
                      <StatusLine label="Look" status={asStr(pick(status, "look", "status"))} />
                      <StatusLine label="Watch" status={asStr(pick(status, "watch", "status"))} />
                      <StatusLine label="Size" status={asStr(pick(status, "size_calibration", "status"))} />
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
          <NullByKBin v={v} />
          <div className="space-y-1 bg-gray-50/70 px-5 py-3 text-sm leading-6 text-ink-muted">
            {computedMean !== null ? (
              <p>
                Computed sites per null study (capture discordance): mean {fmtProp(computedMean)} (MC SE {fmtSe(computedSe)}).
              </p>
            ) : null}
            {rule ? <p>Look and Watch check: {rule}</p> : null}
            {sizeRule ? <p>Size check: {sizeRule}</p> : null}
          </div>
        </>
      ) : (
        <Missing what="The null block" />
      )}
    </BlockCard>
  );
}

// ------------------------------------------------------------------ failure case

/** " (1000 null studies, 300 studies per row)" from the counts that exist; "" when none do. */
function countsNote(parts: [number | null, string][]): string {
  const present = parts.filter(([n]) => n !== null).map(([n, what]) => `${fmtCount(n)} ${what}`);
  return present.length ? ` (${present.join(", ")})` : "";
}

/** The failure case (docs/11 §12.5): honest sites differ mainly in diligence, not case mix. Shown next to the favourable rows. */
export function FailureCaseTable({ v }: { v: SiteSignalValidation }) {
  const fc = asRec(v.failure_case);
  const lines = readPowerLines(asArr(pick(fc, "a", "power")));
  const grossF = asNum(pick(v.design, "gross_f"));
  const nulls = asArr(pick(fc, "b", "null"));
  const reps = asNum(pick(fc, "a", "reps"));
  const rNullA = asNum(pick(fc, "a", "r_null"));
  const rNullB = asNum(pick(fc, "b", "r_null"));

  return (
    <BlockCard
      id="failure-case"
      title="Failure case"
      icon={<FlaskConical className="size-4" aria-hidden />}
      origin={originOf(v)}
      subtitle={
        fc ? (
          <>
            Honest sites differ mainly in diligence: between-site capture SD {fmtParam(fc.between_site_sd_logit)} (logit scale),
            case-mix SD {fmtParam(fc.casemix_sd_log)} (log scale). This is the case built to favour a plain rate KRI.
          </>
        ) : undefined
      }
    >
      {fc ? (
        <>
          <h3 className="px-5 pt-4 pb-2 text-sm font-semibold text-ink">
            (a) Thresholds re-calibrated on this null
            <span className="font-normal text-ink-subtle">{countsNote([[rNullA, "null studies"], [reps, "studies per row"]])}</span>
          </h3>
          {lines.length ? (
            <PowerLinesTable lines={lines} grossF={grossF} caption="Failure case power at both tiers, re-calibrated thresholds" />
          ) : (
            <Missing what="Failure-case power" />
          )}
          <h3 className="border-t border-line px-5 pt-4 pb-2 text-sm font-semibold text-ink">
            (b) Frozen sap-v1 thresholds on this null
            <span className="font-normal text-ink-subtle">{countsNote([[rNullB, "null studies"]])}</span>
          </h3>
          {nulls.length ? (
            <Table className="relative">
              <caption className="sr-only">Failure-case false-flag rates with the frozen sap-v1 thresholds</caption>
              <thead>
                <tr>
                  <Th>Indicator</Th>
                  <Th>False Look per site</Th>
                  <Th>False Look flags per study</Th>
                  <Th>Any Watch per study</Th>
                </tr>
              </thead>
              <tbody>
                {nulls
                  .filter((n) => INDICATOR_IDS.includes(asStr(pick(n, "indicator")) ?? ""))
                  .sort(
                    (a, b) =>
                      INDICATOR_IDS.indexOf(asStr(pick(a, "indicator")) ?? "") -
                      INDICATOR_IDS.indexOf(asStr(pick(b, "indicator")) ?? ""),
                  )
                  .map((n) => {
                    const id = asStr(pick(n, "indicator")) ?? "";
                    return (
                      <tr key={id} data-indicator={id}>
                        <Td className="min-w-44 font-medium text-ink">{indicatorName(id)}</Td>
                        <Td>
                          <Est r={readRateSe(pick(n, "look_per_site"))} />
                        </Td>
                        <Td>
                          <Est r={readRateSe(pick(n, "look_per_study"))} />
                        </Td>
                        <Td>
                          <Est r={readRateSe(pick(n, "watch_fwer"))} ci />
                        </Td>
                      </tr>
                    );
                  })}
              </tbody>
            </Table>
          ) : (
            <Missing what="The failure-case null" />
          )}
        </>
      ) : (
        <Missing what="The failure case" />
      )}
    </BlockCard>
  );
}

// ------------------------------------------------------------------ sensitivity

function grossDetection(row: unknown, tier: string): RateSe | null {
  const hit = asArr(pick(row, "full_mix_detection")).find(
    (d) => pick(d, "indicator") === "discordance" && pick(d, "tier") === tier && pick(d, "label") === "gross_under",
  );
  return hit ? readRateSe(hit) : null;
}

/** Sensitivity analyses SE1..SEn (docs/11 §12.6) for capture discordance, each with MC SE. */
export function SensitivityTable({ v }: { v: SiteSignalValidation }) {
  const rows = asArr(v.sensitivity);
  const rNull = asNum(pick(rows[0], "r_null"));
  return (
    <BlockCard
      id="sensitivity"
      title="Sensitivity analyses"
      icon={<SlidersHorizontal className="size-4" aria-hidden />}
      origin={originOf(v)}
      subtitle={
        <>
          Each row changes one assumption and re-runs capture discordance with the frozen sap-v1 thresholds
          {rNull !== null ? <> ({fmtCount(rNull)} null studies per row)</> : null}. Misspecified-null rows show what happens
          when the null the thresholds assume is wrong.
        </>
      }
    >
      {rows.length ? (
        <Table className="relative">
          <caption className="sr-only">Sensitivity analyses for capture discordance</caption>
          <thead>
            <tr>
              <Th>ID</Th>
              <Th>Change</Th>
              <Th>False Look per site</Th>
              <Th>Any Watch per study</Th>
              <Th>Gross-loss site flagged: Look or Watch</Th>
              <Th>Gross-loss site flagged: Watch</Th>
              <Th className="text-right">Committed study: sites whose tier changed</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const id = asStr(pick(row, "id")) ?? String(i + 1);
              return (
                <tr key={id} data-sensitivity={id}>
                  <Td className="font-mono text-sm whitespace-nowrap">{id}</Td>
                  <Td className="min-w-64 text-ink">{asStr(pick(row, "change")) ?? "—"}</Td>
                  <Td>
                    <Est r={readRateSe(pick(row, "null", "look_per_site"))} />
                  </Td>
                  <Td>
                    <Est r={readRateSe(pick(row, "null", "watch_fwer"))} />
                  </Td>
                  <Td>
                    <Est r={grossDetection(row, "look")} />
                  </Td>
                  <Td>
                    <Est r={grossDetection(row, "watch")} />
                  </Td>
                  <Td className="tabular text-right">
                    {fmtCount(asNum(pick(row, "committed_by_indicator", "discordance", "n_sites_tier_changed")))}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      ) : (
        <Missing what="Sensitivity" />
      )}
    </BlockCard>
  );
}

// ------------------------------------------------------------------ committed study (illustration only)

const CONFUSION_TIERS: { id: string; label: string }[] = [
  { id: "watch", label: "Watch" },
  { id: "look", label: "Look or Watch" },
];

/** Caught, missed and false flags in the one committed study: an illustration, not evidence of performance (§12.7). */
export function CommittedConfusionTable({ v }: { v: SiteSignalValidation }) {
  const confusion = pick(v.eval_study, "confusion");
  const note = asStr(pick(v.eval_study, "note"));
  return (
    <BlockCard
      id="committed-study"
      title={
        <>
          Committed study <span className="font-normal text-ink-muted">· illustration only</span>
        </>
      }
      icon={<Gauge className="size-4" aria-hidden />}
      origin={originOf(v)}
      subtitle={
        note ??
        "Illustration only, not evidence of performance. One study is one draw; the rates above are the evidence."
      }
    >
      {asRec(confusion) ? (
        <Table className="relative">
          <caption className="sr-only">Committed study: planted sites caught and missed, and false flags (illustration only)</caption>
          <thead>
            <tr>
              <Th>Indicator</Th>
              <Th>Tier</Th>
              <Th className="text-right">Planted sites caught</Th>
              <Th className="text-right">Planted sites missed</Th>
              <Th className="text-right">False flags</Th>
              <Th className="text-right">Other sites not flagged</Th>
            </tr>
          </thead>
          <tbody>
            {INDICATORS.flatMap(({ id, name }) =>
              CONFUSION_TIERS.map((t, i) => {
                const c = pick(confusion, id, t.id);
                return (
                  <tr key={`${id}-${t.id}`} data-indicator={id} className={cn(i === 0 && id !== INDICATORS[0].id && "border-t-2 border-line-strong")}>
                    <Td className="min-w-44 font-medium text-ink">{i === 0 ? name : ""}</Td>
                    <Td className="whitespace-nowrap">{t.label}</Td>
                    <Td className="tabular text-right">{fmtCount(asNum(pick(c, "tp")))}</Td>
                    <Td className="tabular text-right">{fmtCount(asNum(pick(c, "fn")))}</Td>
                    <Td className="tabular text-right">{fmtCount(asNum(pick(c, "fp")))}</Td>
                    <Td className="tabular text-right">{fmtCount(asNum(pick(c, "tn")))}</Td>
                  </tr>
                );
              }),
            )}
          </tbody>
        </Table>
      ) : (
        <Missing what="The committed study" />
      )}
    </BlockCard>
  );
}
