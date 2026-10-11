import { Scale } from "lucide-react";
import type { DataOrigin, SiteSignalEquity, SiteSignalValidation } from "@/lib/types";
import { asNum, asRec, asStr, fmtCi, fmtCount, fmtProp, fmtRatio, fmtSe, pick, readRateSe, type RateSe } from "@/lib/summary";
import { Card, CardHeader, Table, Td, Th } from "@/components/ui/primitives";
import { DataOriginBadge } from "@/components/DataOriginBadge";

/**
 * Equity block of the "How well it works" tab (docs/11 §14). The separate Equity tab (F17) is cut, so the
 * committed study's within-site capture odds ratios live here. Every number comes from `GET /api/site-signal/equity`
 * (monitoring/out/equity.json) or, for the operating characteristics, `GET /api/site-signal/validation`
 * (`full_mix.equity`); rounding is for display only (docs/11 §15 rule 6). No number is typed here.
 */

const COMPARISONS: { key: "language" | "pace"; name: string; exposed: string; reference: string }[] = [
  { key: "language", name: "Language", exposed: "Spanish", reference: "English" },
  { key: "pace", name: "Pace", exposed: "Extra time", reference: "standard pace" },
];

function nEpisodes(block: unknown, group: string): string {
  return fmtCount(asNum(pick(block, "n_episodes", group)));
}

function Est({ r }: { r: RateSe | null }) {
  if (!r || r.rate === null) return <span className="text-ink-subtle">—</span>;
  return (
    <span className="tabular whitespace-nowrap">
      <span className="font-medium text-ink">{fmtProp(r.rate)}</span>{" "}
      <span className="text-ink-subtle">(MC SE {fmtSe(r.mcSe)})</span>
    </span>
  );
}

function ciOf(v: unknown): [number | null, number | null] | null {
  return Array.isArray(v) && v.length === 2 ? [asNum(v[0]), asNum(v[1])] : null;
}

export function EquityBlock({ equity, validation }: { equity: SiteSignalEquity; validation: SiteSignalValidation | undefined }) {
  const origin: DataOrigin = equity.data_origin ?? "SIMULATED";
  const note = asStr(equity.note);
  const powerIsLow = equity.power_is_low === true;
  const oc = pick(validation?.full_mix, "equity");

  return (
    <Card id="equity">
      <CardHeader
        title="Equity: capture within the same site"
        icon={<Scale className="size-4 text-ink-subtle" aria-hidden />}
        subtitle="Are Spanish-speaking (or extra-time) patients' episodes found in the site AE log less often than other patients' episodes at the same site? Mantel-Haenszel odds ratio over sites with enough episodes in each group; below 1 means lower capture for that group."
        actions={<DataOriginBadge origin={origin} />}
        className="flex-wrap"
      />
      {powerIsLow || note ? (
        <div className="space-y-1 border-b border-line bg-slate-50 px-4 py-2.5 text-sm text-ink-muted" role="note">
          {powerIsLow ? <p className="font-semibold text-ink">Power is low at these sample sizes.</p> : null}
          {note ? <p>{note}</p> : null}
        </div>
      ) : null}
      <Table className="relative">
        <caption className="sr-only">Within-site capture odds ratios, committed study</caption>
        <thead>
          <tr>
            <Th>Comparison</Th>
            <Th className="text-right">Odds ratio (MH)</Th>
            <Th>95% CI, patient bootstrap</Th>
            <Th>95% CI, Robins-Breslow-Greenland</Th>
            <Th className="text-right">Breslow-Day p</Th>
            <Th className="text-right">Sites used</Th>
            <Th className="text-right">Episodes</Th>
          </tr>
        </thead>
        <tbody>
          {COMPARISONS.map((c) => {
            const b = asRec(equity[c.key]);
            const notComputed = !b || asNum(b.mh_or) === null;
            const exposedKey = asStr(b?.exposed) ?? "";
            const referenceKey = asStr(b?.reference) ?? "";
            return (
              <tr key={c.key} data-comparison={c.key}>
                <Td className="min-w-48">
                  <span className="font-medium text-ink">
                    {c.exposed} vs {c.reference}
                  </span>
                  <span className="block text-sm text-ink-subtle">
                    {c.name}
                    {b?.negative_control === true ? " · negative control (no pace effect simulated)" : ""}
                  </span>
                </Td>
                {notComputed ? (
                  <Td colSpan={4} className="text-ink-muted">
                    {asStr(b?.label) ?? "not computed: insufficient data"}
                  </Td>
                ) : (
                  <>
                    <Td className="tabular text-right font-medium text-ink">{fmtRatio(asNum(b?.mh_or))}</Td>
                    <Td className="tabular whitespace-nowrap">{fmtCi(ciOf(b?.ci95))}</Td>
                    <Td className="tabular whitespace-nowrap">{fmtCi(ciOf(b?.rbg_ci95))}</Td>
                    <Td className="tabular text-right">{fmtSe(asNum(b?.breslow_day_p))}</Td>
                  </>
                )}
                <Td className="tabular text-right">{fmtCount(asNum(b?.n_sites_used))}</Td>
                <Td className="tabular text-right whitespace-nowrap">
                  {exposedKey && referenceKey ? (
                    <>
                      {nEpisodes(b, exposedKey)} / {nEpisodes(b, referenceKey)}
                    </>
                  ) : (
                    "—"
                  )}
                </Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
      <p className="px-4 pt-3 text-sm text-ink-muted">
        Episodes: evaluable, non-paged episodes of the compared group / the reference group, at the sites used. A gap planted at
        one site is diluted in a pooled odds ratio; the per-site odds ratios are in <code className="font-mono text-sm">equity.json</code>.
      </p>
      {asRec(oc) ? (
        <div className="px-4 py-3">
          <h3 className="text-sm font-semibold text-ink">How the intervals behave in simulation</h3>
          <dl className="mt-1.5 grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[auto_1fr]">
            <dt className="text-ink-subtle">Language interval covers 1, no planted gap</dt>
            <dd>
              <Est r={readRateSe(pick(oc, "language_ci_covers_1_null"))} />
            </dd>
            <dt className="text-ink-subtle">Pace interval excludes 1, no planted gap</dt>
            <dd>
              <Est r={readRateSe(pick(oc, "pace_ci_excludes_1_null"))} />
            </dd>
            <dt className="text-ink-subtle">Pace interval excludes 1, full mix</dt>
            <dd>
              <Est r={readRateSe(pick(oc, "pace_ci_excludes_1_full_mix"))} />
            </dd>
          </dl>
        </div>
      ) : (
        <div className="pb-3" />
      )}
    </Card>
  );
}
