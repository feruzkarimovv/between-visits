"use client";

import type { ReactNode } from "react";
import { Clock, Languages, Siren, AlertTriangle, PhoneCall, Users } from "lucide-react";
import type {
  CheckInStatus,
  DraftEntry,
  DraftStatus,
  EscalationLevel,
  EscalationStatus,
  FindingEscalationLevel,
  Lang,
  Pace,
  SaeStatus,
  TodayStatus,
} from "@/lib/types";
import { useRedFlagLabel } from "@/lib/queries";
import { humanize } from "@/lib/format";
import { cn } from "./ui/primitives";

export type Tone = "gray" | "red" | "amber" | "blue" | "green" | "violet" | "accent";

const TONES: Record<Tone, string> = {
  gray: "bg-gray-100 text-gray-800 border-gray-200",
  red: "bg-red-50 text-red-800 border-red-200",
  amber: "bg-amber-50 text-amber-900 border-amber-300",
  blue: "bg-blue-50 text-blue-800 border-blue-200",
  green: "bg-green-50 text-green-800 border-green-200",
  violet: "bg-white text-violet-800 border-violet-400 border-dashed",
  accent: "bg-accent-50 text-accent-800 border-accent-200",
};

export function Chip({
  tone = "gray",
  icon,
  children,
  className,
  title,
  strong,
}: {
  tone?: Tone;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  title?: string;
  strong?: boolean;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-sm leading-5 font-medium whitespace-nowrap",
        TONES[tone],
        strong && tone === "red" && "border-red-700 bg-red-700 text-white",
        strong && tone === "amber" && "border-amber-500 bg-amber-400 text-amber-950",
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

const STATUS: Record<TodayStatus, { label: string; tone: Tone; live?: boolean }> = {
  due: { label: "Due", tone: "gray" },
  scheduled: { label: "Scheduled", tone: "gray" },
  dialing: { label: "Dialing", tone: "accent", live: true },
  in_progress: { label: "In call", tone: "accent", live: true },
  completed: { label: "Completed", tone: "green" },
  no_answer: { label: "No answer", tone: "amber" },
  failed: { label: "Failed", tone: "red" },
  cancelled: { label: "Cancelled", tone: "gray" },
};

export function StatusChip({ status }: { status: TodayStatus | CheckInStatus }) {
  const s = STATUS[status] ?? { label: humanize(status), tone: "gray" as Tone };
  return (
    <Chip tone={s.tone}>
      {s.live ? (
        <span className="relative flex size-2" aria-hidden>
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent-600 opacity-60" />
          <span className="relative inline-flex size-2 rounded-full bg-accent-600" />
        </span>
      ) : null}
      {s.label}
    </Chip>
  );
}

export function LevelChip({
  level,
  strong,
}: {
  level: EscalationLevel | FindingEscalationLevel;
  strong?: boolean;
}) {
  if (level === "emergency")
    return (
      <Chip tone="red" strong={strong} icon={<Siren className="size-3.5" aria-hidden />}>
        Emergency
      </Chip>
    );
  if (level === "urgent")
    return (
      <Chip tone="amber" strong={strong} icon={<AlertTriangle className="size-3.5" aria-hidden />}>
        Urgent
      </Chip>
    );
  if (level === "callback")
    return (
      <Chip tone="blue" icon={<PhoneCall className="size-3.5" aria-hidden />}>
        Callback
      </Chip>
    );
  return <Chip tone="gray">No escalation</Chip>;
}

export function EscalationStatusChip({ status }: { status: EscalationStatus }) {
  if (status === "open") return <Chip tone="red">Open</Chip>;
  if (status === "acknowledged") return <Chip tone="green">Acknowledged</Chip>;
  return <Chip tone="gray">Resolved</Chip>;
}

export function LanguageChip({ lang }: { lang: Lang | undefined }) {
  if (!lang) return null;
  return (
    <Chip tone={lang === "es" ? "accent" : "gray"} icon={<Languages className="size-3.5" aria-hidden />} title={lang === "es" ? "Spanish" : "English"}>
      {lang.toUpperCase()}
    </Chip>
  );
}

export function PaceChip({ pace, hideStandard = true }: { pace: Pace | undefined; hideStandard?: boolean }) {
  if (!pace) return null;
  if (pace === "standard") return hideStandard ? null : <Chip tone="gray">Standard pace</Chip>;
  return (
    <Chip tone="accent" icon={<Clock className="size-3.5" aria-hidden />}>
      Extra time
    </Chip>
  );
}

export function CaregiverChip({ name, relation }: { name: string | null | undefined; relation?: string | null }) {
  if (!name) return null;
  return (
    <Chip tone="gray" icon={<Users className="size-3.5" aria-hidden />} title={`Caregiver: ${name}${relation ? ` (${relation})` : ""}`}>
      {name}
      {relation ? <span className="font-normal text-ink-subtle"> · {relation}</span> : null}
    </Chip>
  );
}

export function RedFlagChip({ id }: { id: string }) {
  const { short, full, level } = useRedFlagLabel(id);
  return (
    <Chip tone={level === "emergency" ? "red" : "amber"} title={full} icon={<AlertTriangle className="size-3.5" aria-hidden />}>
      {short}
    </Chip>
  );
}

export function DraftStatusChip({ status }: { status: DraftStatus }) {
  if (status === "confirmed") return <Chip tone="green">Confirmed</Chip>;
  if (status === "rejected") return <Chip tone="gray">Rejected</Chip>;
  return <Chip tone="blue">Draft</Chip>;
}

export function SaeStatusChip({ status }: { status: SaeStatus }) {
  if (status === "sent") return <Chip tone="green">Sent to sponsor</Chip>;
  if (status === "signed") return <Chip tone="blue">Signed</Chip>;
  return <Chip tone="amber">Draft</Chip>;
}

/**
 * Origin of a confirmed draft (docs/03 §6.5): `DraftOut.origin`, and the sponsor-defined `ORIGIN` column of ae.csv.
 * Every serious-event report is built from a confirmed Between Visits AE draft, so it carries the same origin.
 */
export const BETWEEN_VISITS_ORIGIN: DraftEntry["origin"] = "between_visits";

export function OriginTag({ origin = BETWEEN_VISITS_ORIGIN }: { origin?: string }) {
  return (
    <Chip tone="gray" className="font-mono" title="ORIGIN column in ae.csv: this entry came from a confirmed Between Visits draft">
      origin: {origin}
    </Chip>
  );
}
