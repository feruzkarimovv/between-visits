"use client";

import { BadgeCheck, CornerDownRight, ListChecks, PhoneCall, ShieldAlert, Siren, AlertTriangle, Syringe } from "lucide-react";
import { usePlan } from "@/lib/queries";
import { formatAbsolute, humanize } from "@/lib/format";
import type { PlanItem, PlanRedFlag } from "@/lib/types";
import { Card, CardHeader, EmptyState, ErrorState, Field, LoadingRows, PageHeader, cn } from "@/components/ui/primitives";
import { Chip } from "@/components/chips";

export default function PlanPage() {
  const q = usePlan();
  if (q.isPending) return <LoadingRows rows={8} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />;
  const plan = q.data;
  const byLevel = (level: PlanRedFlag["level"]) => plan.red_flags.filter((f) => f.level === level);
  // Number the main questions; follow-ups hang off the one above them.
  const numbers = plan.items.reduce<(number | null)[]>((acc, it) => {
    const last = acc.reduce<number>((m, v) => (v ?? m), 0);
    acc.push(it.kind === "followup" ? null : last + 1);
    return acc;
  }, []);

  return (
    <>
      <PageHeader
        eyebrow="Approved words only"
        title="Check-in plan"
        subtitle="What the agent asks, word for word, in English and Spanish. Approved by the study team; the agent may not change it."
      />

      <Card className="mb-5 overflow-hidden">
        <div className="grid gap-6 p-6 lg:grid-cols-[auto_minmax(0,1fr)_minmax(0,1.1fr)] lg:items-center">
          <div className="flex items-center gap-4">
            <span className="flex size-16 flex-col items-center justify-center rounded-2xl bg-accent-700 text-white shadow-raised">
              <span className="text-sm leading-none text-accent-100">version</span>
              <span className="text-3xl leading-none font-semibold tracking-tight">{plan.version}</span>
            </span>
            {plan.status === "approved" ? (
              <Chip tone="green" icon={<BadgeCheck className="size-4" aria-hidden />}>
                Approved
              </Chip>
            ) : (
              <Chip tone="amber">{humanize(plan.status)}</Chip>
            )}
          </div>
          <dl className="grid grid-cols-2 gap-4">
            <Field label="Approved by">{plan.approved_by ?? "—"}</Field>
            <Field label="Approved at">{formatAbsolute(plan.approved_at)}</Field>
            <Field label="Source">{plan.source === "protocol_pdf" ? "Proposed from protocol PDF" : "Study team (seed)"}</Field>
            <Field label="Questions">
              {plan.items.length} items · {plan.red_flags.length} red flags
            </Field>
          </dl>
          <Schedule days={plan.schedule_days_after_dose} />
        </div>
        <p className="border-t border-line bg-gray-50/70 px-6 py-3 text-sm leading-6 text-ink-muted">
          Questions are our own plain-language wording (not NCI PRO-CTCAE items). Answers are graded with NCI CTCAE v5.0 rules. Follow-up questions are asked only when the parent answer calls for them.
        </p>
      </Card>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <Card className="overflow-hidden">
          <CardHeader title="Questions" icon={<ListChecks className="size-4" aria-hidden />} subtitle={`${plan.items.length} items, in the order asked`} />
          {plan.items.length === 0 ? (
            <EmptyState title="This plan has no items." />
          ) : (
            <>
              <div className="hidden grid-cols-[3rem_minmax(0,1fr)_minmax(0,1fr)] gap-5 border-b border-line bg-gray-50/70 px-5 py-2.5 text-sm font-medium text-ink-subtle md:grid">
                <span>#</span>
                <span>English</span>
                <span>Español</span>
              </div>
              <ol>
                {plan.items.map((it, i) => (
                  <ItemRow key={it.item_code} item={it} n={numbers[i]} />
                ))}
              </ol>
            </>
          )}
        </Card>

        <div className="space-y-4 xl:sticky xl:top-24">
          <Card>
            <CardHeader
              title="Red flags"
              icon={<ShieldAlert className="size-4" aria-hidden />}
              subtitle="Urgent pages the on-call nurse. Emergency tells the person to call 911 and pages. Condensed from the public Medication Guide."
            />
            {plan.red_flags.length === 0 ? (
              <EmptyState title="No red flags configured." />
            ) : (
              <div className="space-y-4 p-4">
                <FlagGroup level="emergency" flags={byLevel("emergency")} />
                <FlagGroup level="urgent" flags={byLevel("urgent")} />
                <FlagGroup level="callback" flags={byLevel("callback")} />
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

function Schedule({ days }: { days: number[] }) {
  const max = Math.max(7, ...days);
  return (
    <div>
      <div className="mb-3 text-sm font-medium text-ink-subtle">Calls after each dose</div>
      <div className="relative h-16">
        <div className="absolute inset-x-3 top-4 h-1 rounded-full bg-gradient-to-r from-accent-700 via-accent-300 to-gray-200" aria-hidden />
        <div className="absolute top-0 left-0 flex -translate-x-0 flex-col items-center gap-1.5">
          <span className="flex size-9 items-center justify-center rounded-full bg-accent-700 text-white ring-4 ring-white">
            <Syringe className="size-4" aria-hidden />
          </span>
          <span className="text-sm font-medium text-ink">Dose</span>
        </div>
        {days.map((d) => (
          <div key={d} className="absolute top-0 flex -translate-x-1/2 flex-col items-center gap-1.5" style={{ left: `calc(1.25rem + (100% - 2.5rem) * ${d / max})` }}>
            <span className="flex size-9 items-center justify-center rounded-full border-2 border-accent-600 bg-white text-accent-800 ring-4 ring-white">
              <PhoneCall className="size-4" aria-hidden />
            </span>
            <span className="text-sm font-medium whitespace-nowrap text-ink">Day {d}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ItemRow({ item, n }: { item: PlanItem; n: number | null }) {
  const followup = item.kind === "followup";
  return (
    <li className={cn("grid gap-x-5 gap-y-2 border-b border-line/80 px-5 py-4 last:border-b-0 md:grid-cols-[3rem_minmax(0,1fr)_minmax(0,1fr)]", followup && "bg-gray-50/60")}>
      <div className="flex items-start gap-2 md:flex-col md:gap-1">
        {followup ? (
          <CornerDownRight className="mt-1 size-4 text-ink-subtle md:ml-2" aria-label="Follow-up" />
        ) : (
          <span className="flex size-8 items-center justify-center rounded-lg bg-ink font-mono text-sm font-semibold text-white">{n}</span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 md:col-span-2">
        <code className="font-mono text-sm font-medium text-ink-muted">{item.item_code}</code>
        {item.term ? <Chip tone="gray">{item.term}</Chip> : null}
        <span className="text-sm text-ink-subtle">{followup ? "follow-up" : humanize(item.kind)}</span>
      </div>
      {(["en", "es"] as const).map((lang) => (
        <div key={lang} className={cn("min-w-0", lang === "en" ? "md:col-start-2" : "md:col-start-3")}>
          <span className="mb-1 inline-block rounded-md bg-gray-100 px-1.5 font-mono text-sm text-ink-subtle md:hidden">{lang.toUpperCase()}</span>
          <p lang={lang} className="text-[15px] leading-6 text-ink">
            {item.text[lang] ?? <span className="text-ink-subtle">—</span>}
          </p>
          {item.options_say?.[lang] ? (
            <p lang={lang} className="mt-1.5 border-l-2 border-line pl-2.5 text-sm leading-6 text-ink-muted">
              {item.options_say[lang]}
            </p>
          ) : null}
        </div>
      ))}
    </li>
  );
}

const FLAG_STYLE = {
  emergency: { label: "Emergency", icon: Siren, head: "bg-red-700 text-white", ring: "border-red-200", dot: "bg-red-600" },
  urgent: { label: "Urgent", icon: AlertTriangle, head: "bg-amber-400 text-amber-950", ring: "border-amber-200", dot: "bg-amber-500" },
  callback: { label: "Callback", icon: PhoneCall, head: "bg-blue-50 text-blue-900 border-b border-blue-200", ring: "border-blue-200", dot: "bg-blue-500" },
} as const;

function FlagGroup({ level, flags }: { level: PlanRedFlag["level"]; flags: PlanRedFlag[] }) {
  if (!flags.length) return null;
  const s = FLAG_STYLE[level];
  const Icon = s.icon;
  return (
    <section className={cn("overflow-hidden rounded-xl border", s.ring)}>
      <h3 className={cn("flex items-center justify-between px-3 py-2 text-sm font-semibold", s.head)}>
        <span className="inline-flex items-center gap-1.5">
          <Icon className="size-4" aria-hidden />
          {s.label}
        </span>
        <span className="tabular">{flags.length}</span>
      </h3>
      <ul className="divide-y divide-line/80 bg-white">
        {flags.map((f) => (
          <li key={f.id} className="px-3 py-2.5">
            <div className="text-sm leading-5 font-medium text-ink">{f.label_en}</div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-ink-subtle">
              <code className="font-mono">{f.id}</code>
              <span aria-hidden>·</span>
              <span>{f.rule_based ? "Answer rule, or agent report" : "Agent report or post-call safety net"}</span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
