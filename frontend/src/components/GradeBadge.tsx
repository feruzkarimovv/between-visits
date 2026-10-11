import { cn } from "./ui/primitives";

const BAR_HEIGHTS = ["h-1.5", "h-2", "h-2.5", "h-3", "h-3.5"];
const BAR_HEIGHTS_LG = ["h-2", "h-2.5", "h-3", "h-3.5", "h-4"];

/**
 * Provisional CTCAE grade. Always says "provisional"; amber at grade >= 3.
 * The rising bars are a quick visual for grade 1–5; the text carries the meaning.
 * `null` grade = the rules couldn't grade from phone data (needs clinician).
 */
export function GradeBadge({
  grade,
  size = "md",
  className,
}: {
  grade: number | null | undefined;
  size?: "md" | "lg";
  className?: string;
}) {
  const none = grade === null || grade === undefined;
  if (none) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-lg border border-dashed border-gray-400 bg-white px-2 py-0.5 whitespace-nowrap text-ink-muted",
          size === "lg" ? "text-base" : "text-sm",
          className,
        )}
      >
        <span className="font-medium">No rule grade · clinician to grade</span>
      </span>
    );
  }
  const high = grade >= 3;
  const heights = size === "lg" ? BAR_HEIGHTS_LG : BAR_HEIGHTS;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-lg border px-2 py-0.5 whitespace-nowrap",
        size === "lg" ? "text-base" : "text-sm",
        high ? "border-amber-400 bg-amber-100/80 text-amber-950" : "border-gray-300 bg-white text-ink",
        className,
      )}
    >
      <span className="flex items-end gap-[2px]" aria-hidden>
        {heights.map((h, i) => (
          <span
            key={h}
            className={cn(
              "w-[3px] rounded-[1px]",
              h,
              i < grade ? (high ? "bg-amber-600" : "bg-ink/75") : high ? "bg-amber-300/70" : "bg-gray-300",
            )}
          />
        ))}
      </span>
      <span className="font-semibold">Grade {grade}</span>
      <span className={cn("font-normal italic", high ? "text-amber-900" : "text-ink-subtle")}>provisional</span>
    </span>
  );
}
