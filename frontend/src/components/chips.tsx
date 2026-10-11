"use client";

import type { ReactNode } from "react";
import {
  AlertTriangle,
  Ban,
  CalendarClock,
  CheckCircle2,
  CircleDashed,
  Clock,
  Languages,
  PhoneCall,
  PhoneMissed,
  Siren,
  Users,
  XCircle,
} from "lucide-react";
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
  amber: "bg-amber-50 text-amber-900 border-amber-300/80",
  blue: "bg-blue-50 text-blue-800 border-blue-200",
  green: "bg-green-50 text-green-800 border-green-200",
  violet: "bg-violet-50/60 text-violet-800 border-violet-400 border-dashed",
  accent: "bg-accent-50 text-accent-800 border-accent-200",
};

const STRONG: Partial<Record<Tone, string>> = {
  red: "border-red-700 bg-red-700 text-white",
  amber: "border-amber-500 bg-amber-400 text-amber-950",
  green: "border-green-700 bg-green-700 text-white",
  blue: "border-blue-700 bg-blue-700 text-white",
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
        "inline-flex items-center gap-1 rounded-full border px-2 py-px text-sm leading-5 font-medium whitespace-nowrap",
        strong && STRONG[tone] ? STRONG[tone] : TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

/** Pulsing dot for anything happening right now. */
export function LiveDot({ className, tone = "accent" }: { className?: string; tone?: "accent" | "red" | "amber" | "live" }) {
  const color = { accent: "bg-accent-600", red: "bg-red-600", amber: "bg-amber-500", live: "bg-live" }[tone];
  return (
    <span className={cn("relative flex size-2 shrink-0", className)} aria-hidden>
      <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-60", color)} />
      <span className={cn("relative inline-flex size-2 rounded-full", color)} />
    </span>
  );
}

const STATUS: Record<TodayStatus, { label: string; tone: Tone; live?: boolean; icon?: ReactNode }> = {
  due: { label: "Due", tone: "gray", icon: <CircleDashed className="size-3.5" aria-hidden /> },
  scheduled: { label: "Scheduled", tone: "gray", icon: <CalendarClock className="size-3.5" aria-hidden /> },
  dialing: { label: "Dialing", tone: "accent", live: true },
  in_progress: { label: "In call", tone: "accent", live: true },
  completed: { label: "Completed", tone: "green", icon: <CheckCircle2 className="size-3.5" aria-hidden /> },
  no_answer: { label: "No answer", tone: "amber", icon: <PhoneMissed className="size-3.5" aria-hidden /> },
  failed: { label: "Failed", tone: "red", icon: <XCircle className="size-3.5" aria-hidden /> },
  cancelled: { label: "Cancelled", tone: "gray", icon: <Ban className="size-3.5" aria-hidden /> },
};

export function StatusChip({ status }: { status: TodayStatus | CheckInStatus }) {
  const s = STATUS[status] ?? { label: humanize(status), tone: "gray" as Tone };
  return (
    <Chip tone={s.tone} icon={s.live ? <LiveDot className="mr-0.5" /> : s.icon}>
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
  if (status === "acknowledged")
    return (
      <Chip tone="green" icon={<CheckCircle2 className="size-3.5" aria-hidden />}>
        Acknowledged
      </Chip>
    );
  return <Chip tone="gray">Resolved</Chip>;
}

export const LANGUAGE_NAMES: Record<Lang, string> = { en: "English", es: "Spanish" };

export function LanguageChip({ lang, long = false }: { lang: Lang | undefined; long?: boolean }) {
  if (!lang) return null;
  return (
    <Chip
      tone={lang === "es" ? "accent" : "gray"}
      icon={<Languages className="size-3.5" aria-hidden />}
      title={LANGUAGE_NAMES[lang]}
    >
      {long ? (lang === "es" ? "Español" : "English") : lang.toUpperCase()}
      {long ? null : <span className="sr-only"> ({LANGUAGE_NAMES[lang]})</span>}
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
    <Chip
      tone={level === "emergency" ? "red" : "amber"}
      title={full}
      icon={level === "emergency" ? <Siren className="size-3.5" aria-hidden /> : <AlertTriangle className="size-3.5" aria-hidden />}
    >
      {short}
    </Chip>
  );
}

export function DraftStatusChip({ status }: { status: DraftStatus }) {
  if (status === "confirmed")
    return (
      <Chip tone="green" icon={<CheckCircle2 className="size-3.5" aria-hidden />}>
        Confirmed
      </Chip>
    );
  if (status === "rejected")
    return (
      <Chip tone="gray" icon={<XCircle className="size-3.5" aria-hidden />}>
        Rejected
      </Chip>
    );
  return <Chip tone="blue">Draft</Chip>;
}

export function SaeStatusChip({ status }: { status: SaeStatus }) {
  if (status === "sent")
    return (
      <Chip tone="green" icon={<CheckCircle2 className="size-3.5" aria-hidden />}>
        Sent to sponsor
      </Chip>
    );
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
