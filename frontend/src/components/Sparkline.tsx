import type { TimelinePoint } from "@/lib/types";
import { formatDay } from "@/lib/format";

/**
 * Small-multiple chart of provisional grade (0-4) over time for one term.
 * Dose dates are vertical dashed markers. Ungraded points are hollow at the baseline.
 */
export function Sparkline({
  term,
  points,
  doseDates,
  width = 280,
  height = 72,
}: {
  term: string;
  points: TimelinePoint[];
  doseDates: string[];
  width?: number;
  height?: number;
}) {
  const padX = 8;
  const padTop = 8;
  const padBottom = 6;
  const days = [...points.map((p) => p.date), ...doseDates].map((d) => Date.parse(`${d.slice(0, 10)}T12:00:00Z`)).filter((n) => !Number.isNaN(n));
  if (!points.length || !days.length) return null;
  const min = Math.min(...days);
  const max = Math.max(...days, min + 86_400_000);
  const x = (d: string) => padX + ((Date.parse(`${d.slice(0, 10)}T12:00:00Z`) - min) / (max - min)) * (width - padX * 2);
  const y = (g: number) => padTop + (1 - g / 4) * (height - padTop - padBottom);
  const graded = points.filter((p) => typeof p.provisional_grade === "number");
  const path = graded.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.provisional_grade ?? 0).toFixed(1)}`).join(" ");
  const maxGrade = Math.max(0, ...graded.map((p) => p.provisional_grade ?? 0));
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
      {[1, 2, 3, 4].map((g) => (
        <line key={g} x1={padX} x2={width - padX} y1={y(g)} y2={y(g)} stroke={g === 3 ? "#fcd34d" : "#eef0f3"} strokeWidth={1} strokeDasharray={g === 3 ? "3 3" : undefined} />
      ))}
      <line x1={padX} x2={width - padX} y1={y(0)} y2={y(0)} stroke="#d1d5db" strokeWidth={1} />
      {doseDates.map((d) => (
        <g key={d}>
          <title>{`Dose ${formatDay(d)}`}</title>
          <line x1={x(d)} x2={x(d)} y1={padTop - 4} y2={height - padBottom} stroke="#0f766e" strokeWidth={1.25} strokeDasharray="2 3" />
        </g>
      ))}
      {path ? <path d={path} fill="none" stroke={maxGrade >= 3 ? "#b45309" : "#374151"} strokeWidth={1.75} strokeLinejoin="round" /> : null}
      {points.map((p) => {
        const g = p.provisional_grade;
        const cx = x(p.date);
        if (g === null) return <circle key={p.checkin_id} cx={cx} cy={y(0)} r={3} fill="white" stroke="#9ca3af" strokeWidth={1.25}><title>{`${formatDay(p.date)}: not graded${p.answer ? ` (${p.answer})` : ""}`}</title></circle>;
        return (
          <circle key={p.checkin_id} cx={cx} cy={y(g)} r={3.5} fill={g >= 3 ? "#d97706" : "#374151"} stroke="white" strokeWidth={1}>
            <title>{`${formatDay(p.date)}: grade ${g} (provisional)${p.answer ? `, answer ${p.answer}` : ""}`}</title>
          </circle>
        );
      })}
    </svg>
  );
}
