"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { FunnelLimit, FunnelPoint, SignalTier, SiteSignalLabels } from "@/lib/types";
import { Table, Td, Th } from "./ui/primitives";

/**
 * Hand-built SVG funnel plot for the committed Site Signal run (docs/06 § Site Signal pages, WS3 F12).
 *
 *   x = E (expected matched episodes), y = O/E (observed / expected).
 *   Look and Watch lower limits come from `funnel.limits` (computed from the sap-v1 thresholds), drawn as
 *   curves in E. One dot per computed site from `funnel.points`. Sites not computed sit as hollow grey
 *   markers in a strip below the axis, each with its reason as a tooltip.
 *
 * Every number and label is passed in from `GET /api/sites`; this file has no result literals. Tier ink
 * follows TierBadge's neutral slate scale and never uses a clinical state color.
 */

export interface NotComputedMarker {
  site_id: string;
  /** Display text: `labels.not_computed` plus `labels.reasons[reason]`. */
  reason: string;
}

const INK = {
  axis: "#94a3b8", // slate-400
  grid: "#e2e8f0", // slate-200
  text: "#475569", // slate-600
  strong: "#1e293b", // slate-800
  look: "#334155", // slate-700
  none: "#94a3b8", // slate-400
  hollow: "#94a3b8", // slate-400
  bandLook: "#f1f5f9", // slate-100
  bandWatch: "#e2e8f0", // slate-200
};

const DOT: Record<SignalTier, { r: number; fill: string; stroke: string; strokeWidth: number }> = {
  watch: { r: 6, fill: INK.strong, stroke: "#ffffff", strokeWidth: 1.5 },
  look: { r: 6, fill: "#ffffff", stroke: INK.look, strokeWidth: 2.25 },
  none: { r: 4.5, fill: INK.none, stroke: "#ffffff", strokeWidth: 1 },
  not_computed: { r: 5, fill: "#ffffff", stroke: INK.hollow, strokeWidth: 1.5 },
};

/** A "nice" tick step (1, 2 or 5 × 10^k) so that `max / step` is about `count`. */
function niceStep(max: number, count: number): number {
  const raw = max / Math.max(1, count);
  const pow = 10 ** Math.floor(Math.log10(raw));
  const unit = raw / pow;
  return (unit <= 1 ? 1 : unit <= 2 ? 2 : unit <= 5 ? 5 : 10) * pow;
}

function ticks(max: number, count: number): { step: number; top: number; values: number[] } {
  const step = niceStep(max, count);
  const top = Math.ceil(max / step) * step;
  const values: number[] = [];
  for (let v = 0; v <= top + step / 2; v += step) values.push(Number(v.toFixed(6)));
  return { step, top, values };
}

function fmt(v: number, digits: number): string {
  return v.toFixed(digits);
}

/** Polyline segments through the non-null points (a null breaks the line). */
function segments(limits: FunnelLimit[], key: "look_lower" | "watch_lower"): { E: number; y: number }[][] {
  const out: { E: number; y: number }[][] = [];
  let cur: { E: number; y: number }[] = [];
  for (const l of limits) {
    const y = l[key];
    if (y === null || y === undefined || !Number.isFinite(y)) {
      if (cur.length) out.push(cur);
      cur = [];
      continue;
    }
    cur.push({ E: l.E, y });
  }
  if (cur.length) out.push(cur);
  return out;
}

function useWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setWidth(Math.max(280, Math.floor(el.getBoundingClientRect().width)));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, width };
}

export function FunnelPlot({
  points,
  limits,
  notComputed,
  labels,
  legendNote,
  className,
}: {
  points: FunnelPoint[];
  limits: FunnelLimit[];
  notComputed: NotComputedMarker[];
  labels: SiteSignalLabels;
  /** Shown first in the legend, e.g. the number of computed sites from the run. */
  legendNote?: ReactNode;
  className?: string;
}) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const { ref, width } = useWidth<HTMLDivElement>(720);
  const compact = width < 520;

  const sortedLimits = [...limits].sort((a, b) => a.E - b.E);
  const maxE = points.length ? Math.max(...points.map((p) => p.E)) : Math.max(10, ...sortedLimits.map((l) => l.E));
  const maxY = Math.max(1, ...points.map((p) => p.oe_ratio));
  const xt = ticks(maxE * 1.08, compact ? 4 : 6);
  const yt = ticks(maxY * 1.08, 5);

  const m = { top: 14, right: compact ? 12 : 20, left: compact ? 40 : 52 };
  const plotH = Math.round(Math.min(340, Math.max(220, width * 0.46)));
  const plotW = width - m.left - m.right;
  const axisBottom = m.top + plotH;

  // Strip of hollow markers for not-computed sites, wrapped into rows.
  const stripLabelW = compact ? 0 : 108;
  const slot = 46;
  const perRow = Math.max(1, Math.floor((plotW - stripLabelW) / slot));
  const stripRows = notComputed.length ? Math.ceil(notComputed.length / perRow) : 0;
  const stripTop = axisBottom + 50;
  const stripHeader = compact ? 18 : 0;
  const rowH = 40;
  const height = stripRows ? stripTop + stripHeader + stripRows * rowH + 6 : axisBottom + 46;

  const x = (e: number) => m.left + (e / xt.top) * plotW;
  const y = (r: number) => m.top + plotH - (r / yt.top) * plotH;
  const path = (seg: { E: number; y: number }[]) =>
    seg.map((p, i) => `${i ? "L" : "M"}${x(p.E).toFixed(1)},${y(p.y).toFixed(1)}`).join(" ");
  const band = (seg: { E: number; y: number }[]) =>
    seg.length < 2
      ? ""
      : `${path(seg)} L${x(seg[seg.length - 1].E).toFixed(1)},${y(0).toFixed(1)} L${x(seg[0].E).toFixed(1)},${y(0).toFixed(1)} Z`;

  const look = segments(sortedLimits, "look_lower");
  const watch = segments(sortedLimits, "watch_lower");
  const clip = `funnel-clip-${uid}`;
  const titleId = `funnel-title-${uid}`;
  const descId = `funnel-desc-${uid}`;
  const flagged = points.filter((p) => p.tier === "watch" || p.tier === "look");
  // Draw unflagged dots first so flagged sites stay on top.
  const ordered = [...points].sort((a, b) => Number(a.tier !== "none") - Number(b.tier !== "none"));

  return (
    <div className={className}>
      <div ref={ref} className="w-full min-w-0">
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-labelledby={`${titleId} ${descId}`}
          className="block max-w-full font-sans"
        >
          <title id={titleId}>Funnel plot of site capture: expected matched episodes against observed over expected</title>
          <desc id={descId}>
            {`${points.length} computed sites shown as dots; ${notComputed.length} sites not computed, shown as hollow markers below the axis. ` +
              `${labels.look} and ${labels.watch} lower limits are drawn as curves. The same data is in the table below the plot.`}
          </desc>
          <defs>
            <clipPath id={clip}>
              <rect x={m.left} y={m.top} width={plotW} height={plotH} />
            </clipPath>
          </defs>

          {/* grid + axes */}
          {yt.values.map((v) => (
            <g key={`y${v}`}>
              <line x1={m.left} x2={m.left + plotW} y1={y(v)} y2={y(v)} stroke={INK.grid} strokeWidth={1} />
              <text x={m.left - 6} y={y(v)} dy="0.32em" textAnchor="end" fontSize={11} fill={INK.text} className="tabular">
                {fmt(v, yt.step < 0.1 ? 2 : 1)}
              </text>
            </g>
          ))}
          {xt.values.map((v) => (
            <g key={`x${v}`}>
              <line x1={x(v)} x2={x(v)} y1={axisBottom} y2={axisBottom + 4} stroke={INK.axis} />
              <text x={x(v)} y={axisBottom + 16} textAnchor="middle" fontSize={11} fill={INK.text} className="tabular">
                {fmt(v, xt.step < 1 ? 1 : 0)}
              </text>
            </g>
          ))}
          <line x1={m.left} x2={m.left + plotW} y1={axisBottom} y2={axisBottom} stroke={INK.axis} />
          <line x1={m.left} x2={m.left} y1={m.top} y2={axisBottom} stroke={INK.axis} />
          <text x={m.left + plotW / 2} y={axisBottom + 34} textAnchor="middle" fontSize={12} fill={INK.text}>
            E, expected matched episodes
          </text>
          <text
            transform={`translate(${compact ? 11 : 14},${m.top + plotH / 2}) rotate(-90)`}
            textAnchor="middle"
            fontSize={12}
            fill={INK.text}
          >
            O/E, observed over expected
          </text>

          {/* limit bands and curves */}
          <g clipPath={`url(#${clip})`}>
            {look.map((seg, i) => (
              <path key={`lb${i}`} d={band(seg)} fill={INK.bandLook} />
            ))}
            {watch.map((seg, i) => (
              <path key={`wb${i}`} d={band(seg)} fill={INK.bandWatch} />
            ))}
            <line
              x1={m.left}
              x2={m.left + plotW}
              y1={y(1)}
              y2={y(1)}
              stroke={INK.axis}
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            {look.map((seg, i) => (
              <path key={`l${i}`} d={path(seg)} fill="none" stroke={INK.look} strokeWidth={1.75} strokeDasharray="6 4" />
            ))}
            {watch.map((seg, i) => (
              <path key={`w${i}`} d={path(seg)} fill="none" stroke={INK.strong} strokeWidth={2} />
            ))}

            {ordered.map((p) => {
              const d = DOT[p.tier] ?? DOT.none;
              return (
                <circle
                  key={p.site_id}
                  cx={x(p.E)}
                  cy={y(p.oe_ratio)}
                  r={d.r}
                  fill={d.fill}
                  stroke={d.stroke}
                  strokeWidth={d.strokeWidth}
                  data-site={p.site_id}
                  data-tier={p.tier}
                >
                  <title>{`Site ${p.site_id}: E ${fmt(p.E, 1)}, O/E ${fmt(p.oe_ratio, 2)}, ${labels[p.tier] ?? p.tier}`}</title>
                </circle>
              );
            })}
            {flagged.map((p) => (
              <text
                key={`t${p.site_id}`}
                x={x(p.E) + 9}
                y={y(p.oe_ratio)}
                dy="0.32em"
                fontSize={11}
                fontWeight={600}
                fill={INK.strong}
                stroke="#ffffff"
                strokeWidth={3}
                paintOrder="stroke"
                aria-hidden
              >
                {p.site_id}
              </text>
            ))}
          </g>
          <text x={m.left + plotW - 4} y={y(1) - 5} textAnchor="end" fontSize={11} fill={INK.text}>
            O/E = 1
          </text>

          {/* strip: sites not computed */}
          {stripRows ? (
            <g data-strip="not-computed">
              <line x1={m.left} x2={m.left + plotW} y1={stripTop - 8} y2={stripTop - 8} stroke={INK.grid} />
              <text
                x={m.left}
                y={compact ? stripTop + 6 : stripTop + 14}
                fontSize={12}
                fontWeight={500}
                fill={INK.text}
              >
                {`${labels.not_computed} (${notComputed.length})`}
              </text>
              {notComputed.map((s, i) => {
                const row = Math.floor(i / perRow);
                const col = i % perRow;
                const cx = m.left + stripLabelW + col * slot + slot / 2 - (compact ? slot / 2 - 8 : 0);
                const cy = stripTop + stripHeader + row * rowH + 10;
                return (
                  <g key={s.site_id} data-site={s.site_id} data-tier="not_computed">
                    <circle
                      cx={cx}
                      cy={cy}
                      r={DOT.not_computed.r}
                      fill={DOT.not_computed.fill}
                      stroke={DOT.not_computed.stroke}
                      strokeWidth={DOT.not_computed.strokeWidth}
                    >
                      <title>{`Site ${s.site_id}: ${s.reason}`}</title>
                    </circle>
                    <text x={cx} y={cy + 20} textAnchor="middle" fontSize={11} fill={INK.text} aria-hidden>
                      {s.site_id}
                    </text>
                  </g>
                );
              })}
            </g>
          ) : null}
        </svg>
      </div>

      <FunnelLegend labels={labels} note={legendNote} />

      <details className="mt-3 rounded-md border border-line bg-white">
        <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-ink-muted">Funnel data as a table</summary>
        <Table className="relative">
          <caption className="sr-only">Funnel plot data: one row per site</caption>
          <thead>
            <tr>
              <Th>Site</Th>
              <Th className="text-right">E</Th>
              <Th className="text-right">O/E</Th>
              <Th>Tier</Th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.site_id}>
                <Td className="font-medium">{p.site_id}</Td>
                <Td className="tabular text-right">{fmt(p.E, 1)}</Td>
                <Td className="tabular text-right">{fmt(p.oe_ratio, 2)}</Td>
                <Td>{labels[p.tier] ?? p.tier}</Td>
              </tr>
            ))}
            {notComputed.map((s) => (
              <tr key={s.site_id} className="text-ink-muted">
                <Td className="font-medium">{s.site_id}</Td>
                <Td className="text-right">—</Td>
                <Td className="text-right">—</Td>
                <Td className="min-w-56 whitespace-normal">{s.reason}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
        <Table className="relative border-t border-line">
          <caption className="sr-only">Lower limits by E</caption>
          <thead>
            <tr>
              <Th className="text-right">E</Th>
              <Th className="text-right">{labels.look} lower limit (O/E)</Th>
              <Th className="text-right">{labels.watch} lower limit (O/E)</Th>
            </tr>
          </thead>
          <tbody>
            {sortedLimits.map((l) => (
              <tr key={l.E}>
                <Td className="tabular text-right">{fmt(l.E, 1)}</Td>
                <Td className="tabular text-right">{l.look_lower === null ? "—" : fmt(l.look_lower, 2)}</Td>
                <Td className="tabular text-right">{l.watch_lower === null ? "—" : fmt(l.watch_lower, 2)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </details>
    </div>
  );
}

function Swatch({ tier }: { tier: SignalTier }) {
  const d = DOT[tier];
  return (
    <svg width={14} height={14} viewBox="0 0 14 14" aria-hidden className="shrink-0">
      <circle cx={7} cy={7} r={Math.min(d.r, 5.5)} fill={d.fill} stroke={d.stroke === "#ffffff" ? d.fill : d.stroke} strokeWidth={d.strokeWidth} />
    </svg>
  );
}

function LineSwatch({ dashed, color }: { dashed: boolean; color: string }) {
  return (
    <svg width={22} height={10} viewBox="0 0 22 10" aria-hidden className="shrink-0">
      <line x1={1} x2={21} y1={5} y2={5} stroke={color} strokeWidth={2} strokeDasharray={dashed ? "5 3" : undefined} />
    </svg>
  );
}

/** Tier and limit legend; every tier name comes from the API labels. */
export function FunnelLegend({ labels, note }: { labels: SiteSignalLabels; note?: ReactNode }) {
  const item = "inline-flex items-center gap-1.5 whitespace-nowrap";
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 text-sm text-ink-muted" aria-label="Funnel legend">
      {note ? <li className={item}>{note}</li> : null}
      {(["watch", "look", "none", "not_computed"] as const).map((t) => (
        <li key={t} className={item}>
          <Swatch tier={t} />
          {labels[t]}
        </li>
      ))}
      <li className={item}>
        <LineSwatch dashed color={INK.look} />
        {labels.look} lower limit
      </li>
      <li className={item}>
        <LineSwatch dashed={false} color={INK.strong} />
        {labels.watch} lower limit
      </li>
    </ul>
  );
}
