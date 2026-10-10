"use client";

import Link from "next/link";
import { BellRing, CheckCircle2, PhoneCall, Siren, WifiOff } from "lucide-react";
import { useEscalations } from "@/lib/queries";
import { cn } from "./ui/primitives";

/** Open escalations pill in the top bar. Polls every 2 s. */
export function EscalationBanner() {
  const { data, isError, isPending } = useEscalations("open", 2000);
  const open = data ?? [];
  const emergency = open.filter((e) => e.level === "emergency").length;
  const urgent = open.filter((e) => e.level === "urgent").length;
  const callback = open.filter((e) => e.level === "callback").length;
  const paged = emergency + urgent;

  let tone: string;
  let icon: React.ReactNode;
  let text: string;
  if (isError && !data) {
    tone = "border-gray-300 bg-gray-50 text-ink-muted";
    icon = <WifiOff className="size-4" aria-hidden />;
    text = "Escalations unavailable";
  } else if (isPending) {
    tone = "border-line bg-white text-ink-subtle";
    icon = <BellRing className="size-4" aria-hidden />;
    text = "Checking escalations…";
  } else if (emergency > 0) {
    tone = "border-red-700 bg-red-700 text-white";
    icon = <Siren className="size-4" aria-hidden />;
    text = `${paged} open escalation${paged === 1 ? "" : "s"} · ${emergency} emergency`;
  } else if (urgent > 0) {
    tone = "border-amber-500 bg-amber-400 text-amber-950";
    icon = <BellRing className="size-4" aria-hidden />;
    text = `${urgent} urgent escalation${urgent === 1 ? "" : "s"} open`;
  } else if (callback > 0) {
    tone = "border-blue-200 bg-blue-50 text-blue-900";
    icon = <PhoneCall className="size-4" aria-hidden />;
    text = `${callback} callback${callback === 1 ? "" : "s"} waiting`;
  } else {
    tone = "border-green-200 bg-green-50 text-green-800";
    icon = <CheckCircle2 className="size-4" aria-hidden />;
    text = "No open escalations";
  }
  const extra = paged > 0 && callback > 0 ? ` · ${callback} callback${callback === 1 ? "" : "s"}` : "";

  return (
    <Link
      href="/escalations"
      aria-live="polite"
      className={cn(
        "inline-flex h-9 max-w-full min-w-0 shrink-0 items-center gap-2 rounded-full border px-3 text-sm font-semibold whitespace-nowrap transition-colors",
        tone,
        paged > 0 && "shadow-sm",
      )}
    >
      {icon}
      <span className="truncate">
        {text}
        {extra}
      </span>
    </Link>
  );
}
