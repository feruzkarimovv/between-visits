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
        "inline-flex items-center gap-1 rounded-full border border-dashed border-violet-400 bg-white px-2 py-0.5 text-sm leading-5 font-medium whitespace-nowrap text-violet-800",
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
    <div className={cn("rounded-md border border-dashed border-violet-300 bg-violet-50/40 p-3", className)}>
      <AiLabel className="mb-2">{label}</AiLabel>
      <div className="text-sm text-ink">{children}</div>
    </div>
  );
}
