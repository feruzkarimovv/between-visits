import { cn } from "./ui/primitives";

/**
 * Provisional CTCAE grade. Always says "provisional"; amber at grade >= 3.
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
  const high = typeof grade === "number" && grade >= 3;
  const none = grade === null || grade === undefined;
  return (
    <span
      className={cn(
        "inline-flex items-baseline gap-1.5 rounded-md border px-2 py-0.5 whitespace-nowrap",
        size === "lg" ? "text-base" : "text-sm",
        high
          ? "border-amber-400 bg-amber-100 text-amber-950"
          : none
            ? "border-gray-300 bg-gray-50 text-ink-muted"
            : "border-gray-300 bg-white text-ink",
        className,
      )}
    >
      {none ? (
        <span className="font-medium">No rule grade · clinician to grade</span>
      ) : (
        <>
          <span className="font-semibold">Grade {grade}</span>
          <span className={cn("font-normal italic", high ? "text-amber-900" : "text-ink-subtle")}>provisional</span>
        </>
      )}
    </span>
  );
}
