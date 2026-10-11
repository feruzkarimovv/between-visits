import { useId } from "react";
import type { TimelinePoint } from "@/lib/types";
import { formatDay } from "@/lib/format";

/**
 * Small-multiple chart of provisional grade (0-4) over time for one term.
 * The shaded band is grade 3 and above; dose dates are vertical dashed markers.
 * Ungraded points are hollow at the baseline.
 */
export function Sparkline({
  term,
  points,
  doseDates,
  width = 280,
  height = 84,
}: {
  term: string;
  points: TimelinePoint[];
  doseDates: string[];
  width?: number;
  height?: number;
}) {
  const gradientId = `spark-${useId().replace(/:/g, "")}`;
  const padX = 8;
  const padTop = 8;
  const padBottom = 8;
  const days = [...points.map((p) => p.date), ...doseDates].map((d) => Date.parse(`${d.slice(0, 10)}T12:00:00Z`)).filter((n) => !Number.isNaN(n));
  if (!points.length || !days.length) return null;
  const min = Math.min(...days);
  const max = Math.max(...days, min + 86_400_000);
  const x = (d: string) => padX + ((Date.parse(`${d.slice(0, 10)}T12:00:00Z`) - min) / (max - min)) * (width - padX * 2);
  const y = (g: number) => padTop + (1 - g / 4) * (height - padTop - padBottom);
  const graded = points.filter((p) => typeof p.provisional_grade === "number");
  const coords = graded.map((p) => [x(p.date), y(p.provisional_grade ?? 0)] as const);
  const path = coords.map(([cx, cy], i) => `${i ? "L" : "M"}${cx.toFixed(1)},${cy.toFixed(1)}`).join(" ");
  const area = coords.length > 1 ? `${path} L${coords[coords.length - 1][0].toFixed(1)},${y(0).toFixed(1)} L${coords[0][0].toFixed(1)},${y(0).toFixed(1)} Z` : null;
  const length = coords.reduce((acc, [cx, cy], i) => (i ? acc + Math.hypot(cx - coords[i - 1][0], cy - coords[i - 1][1]) : 0), 0);
  const maxGrade = Math.max(0, ...graded.map((p) => p.provisional_grade ?? 0));
  const high = maxGrade >= 3;
  const summary = points.map((p) => `${formatDay(p.date)}: ${p.provisional_grade === null ? "not graded" : `grade ${p.provisional_grade}`}`).join("; ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      role="img"
      aria-label={`${term} provisional grade over time. ${summary}`}
      className="overflow-visible"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={high ? "#d97706" : "#127d70"} stopOpacity="0.22" />
          <stop offset="1" stopColor={high ? "#d97706" : "#127d70"} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* grade >= 3 band */}
      <rect x={padX} y={y(4)} width={width - padX * 2} height={y(3) - y(4)} fill="#fef3c7" opacity="0.7" rx="2" />
      <line x1={padX} x2={width - padX} y1={y(3)} y2={y(3)} stroke="#f59e0b" strokeWidth={1} strokeDasharray="3 3" opacity="0.7" />
      {[1, 2].map((g) => (
        <line key={g} x1={padX} x2={width - padX} y1={y(g)} y2={y(g)} stroke="#eef1f0" strokeWidth={1} />
      ))}
      <line x1={padX} x2={width - padX} y1={y(0)} y2={y(0)} stroke="#cfd6d3" strokeWidth={1} />
      {doseDates.map((d) => (
        <g key={d}>
          <title>{`Dose ${formatDay(d)}`}</title>
          <line x1={x(d)} x2={x(d)} y1={padTop - 4} y2={height - padBottom} stroke="#0d655b" strokeWidth={1.25} strokeDasharray="2 3" />
          <circle cx={x(d)} cy={padTop - 4} r={2.5} fill="#0d655b" />
        </g>
      ))}
      {area ? <path d={area} fill={`url(#${gradientId})`} /> : null}
      {path ? (
        <path
          d={path}
          fill="none"
          stroke={high ? "#b45309" : "#26302e"}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          className="bv-draw"
          style={{ ["--bv-len" as string]: Math.ceil(length) + 2 }}
        />
      ) : null}
      {points.map((p) => {
        const g = p.provisional_grade;
        const cx = x(p.date);
        if (g === null)
          return (
            <circle key={p.checkin_id} cx={cx} cy={y(0)} r={3.25} fill="white" stroke="#9ba7a3" strokeWidth={1.4}>
              <title>{`${formatDay(p.date)}: not graded${p.answer ? ` (${p.answer})` : ""}`}</title>
            </circle>
          );
        return (
          <circle key={p.checkin_id} cx={cx} cy={y(g)} r={g >= 3 ? 4.5 : 3.75} fill={g >= 3 ? "#d97706" : "#26302e"} stroke="white" strokeWidth={1.5}>
            <title>{`${formatDay(p.date)}: grade ${g} (provisional)${p.answer ? `, answer ${p.answer}` : ""}`}</title>
          </circle>
        );
      })}
    </svg>
  );
}
