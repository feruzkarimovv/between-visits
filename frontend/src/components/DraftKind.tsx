import { ClipboardList, Pill, Stethoscope } from "lucide-react";
import type { DraftEntry } from "@/lib/types";
import { humanize } from "@/lib/format";
import { NURSE_TASK_LABELS } from "@/lib/labels";
import { cn } from "./ui/primitives";

export const KIND_LABEL = { AE: "Adverse event", CM: "Medication", NURSE_TASK: "Nurse task" } as const;

export function draftTitle(d: DraftEntry): string {
  if (d.kind === "AE") return d.payload.term;
  if (d.kind === "CM") return d.payload.medication_name;
  return NURSE_TASK_LABELS[d.payload.category] ?? humanize(d.payload.category);
}

/** Icon tile for a draft's kind: side effect, medication or nurse task. Decorative; the kind is always written next to it. */
export function DraftKindIcon({ kind, className }: { kind: DraftEntry["kind"]; className?: string }) {
  const Icon = kind === "AE" ? Stethoscope : kind === "CM" ? Pill : ClipboardList;
  return (
    <span
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-lg ring-1",
        kind === "NURSE_TASK"
          ? "bg-blue-50 text-blue-700 ring-blue-200"
          : kind === "CM"
            ? "bg-gray-100 text-ink-muted ring-line"
            : "bg-accent-50 text-accent-700 ring-accent-200",
        className,
      )}
      aria-hidden
    >
      <Icon className="size-[18px]" />
    </span>
  );
}
