import { Sparkles } from "lucide-react";
import { cn } from "./ui/primitives";

/** Marks any LLM-produced string. Always visible, always text (not color only). */
export function AiLabel({
  children = "AI draft",
  className,
}: {
  children?: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-dashed border-violet-400 bg-violet-50/70 px-2 py-px text-sm leading-5 font-medium whitespace-nowrap text-violet-800",
        className,
      )}
    >
      <Sparkles className="size-3.5" aria-hidden />
      {children}
    </span>
  );
}

/** Violet-outlined box for a block of AI-produced text. */
export function AiBlock({
  label = "AI draft",
  children,
  className,
}: {
  label?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border border-dashed border-violet-300 bg-gradient-to-b from-violet-50/70 to-white p-4", className)}>
      <AiLabel className="mb-2.5">{label}</AiLabel>
      <div className="text-[15px] leading-7 text-ink">{children}</div>
    </div>
  );
}
