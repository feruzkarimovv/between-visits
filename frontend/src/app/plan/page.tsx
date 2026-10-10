"use client";

import { CheckCircle2, ListChecks, ShieldAlert } from "lucide-react";
import { usePlan } from "@/lib/queries";
import { formatAbsolute, humanize } from "@/lib/format";
import type { PlanItem } from "@/lib/types";
import { Card, CardHeader, EmptyState, ErrorState, Field, LoadingRows, PageHeader, Table, Td, Th, cn } from "@/components/ui/primitives";
import { Chip, LevelChip } from "@/components/chips";

export default function PlanPage() {
  const q = usePlan();
  if (q.isPending) return <LoadingRows rows={8} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />;
  const plan = q.data;
  const rank = { emergency: 0, urgent: 1, callback: 2 } as const;
  const flags = [...plan.red_flags].sort((a, b) => rank[a.level] - rank[b.level]);

  return (
    <>
      <PageHeader
        title="Check-in plan"
        subtitle="What the agent asks, word for word, in English and Spanish. Approved by the study team; the agent may not change it."
      />
      <Card className="mb-4 p-4">
        <dl className="grid grid-cols-2 gap-4 md:grid-cols-5">
          <Field label="Version">
            v{plan.version}{" "}
            {plan.status === "approved" ? (
              <Chip tone="green" icon={<CheckCircle2 className="size-3.5" aria-hidden />} className="ml-1">
                Approved
              </Chip>
            ) : (
              <Chip tone="amber" className="ml-1">
                {humanize(plan.status)}
              </Chip>
            )}
          </Field>
          <Field label="Approved by">{plan.approved_by ?? "—"}</Field>
          <Field label="Approved at">{formatAbsolute(plan.approved_at)}</Field>
          <Field label="Schedule">Days {plan.schedule_days_after_dose.join(", ")} after each dose</Field>
          <Field label="Source">{plan.source === "protocol_pdf" ? "Proposed from protocol PDF" : "Study team (seed)"}</Field>
        </dl>
        <p className="mt-3 text-sm text-ink-subtle">
          Questions are our own plain-language wording (not NCI PRO-CTCAE items). Answers are graded with NCI CTCAE v5.0 rules. Follow-up questions are asked only when the parent answer calls for them.
        </p>
      </Card>

      <Card className="mb-4">
        <CardHeader title="Questions" icon={<ListChecks className="size-4 text-ink-subtle" aria-hidden />} subtitle={`${plan.items.length} items, in the order asked`} />
        {plan.items.length === 0 ? (
          <EmptyState title="This plan has no items." />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="w-56">Item</Th>
                <Th>English</Th>
                <Th>Español</Th>
              </tr>
            </thead>
            <tbody>
              {plan.items.map((it) => (
                <ItemRow key={it.item_code} item={it} />
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Red flags"
          icon={<ShieldAlert className="size-4 text-ink-subtle" aria-hidden />}
          subtitle="Any of these pages the on-call nurse (urgent) or tells the person to call 911 and pages (emergency). Condensed from the public Medication Guide."
        />
        {flags.length === 0 ? (
          <EmptyState title="No red flags configured." />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Level</Th>
                <Th>Red flag</Th>
                <Th>Detected by</Th>
              </tr>
            </thead>
            <tbody>
              {flags.map((f) => (
                <tr key={f.id}>
                  <Td>
                    <LevelChip level={f.level} />
                  </Td>
                  <Td>
                    <div className="font-medium">{f.label_en}</div>
                    <div className="font-mono text-sm text-ink-subtle">{f.id}</div>
                  </Td>
                  <Td className="text-ink-muted">{f.rule_based ? "Answer rule, or agent report" : "Agent report or post-call safety net"}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}

function ItemRow({ item }: { item: PlanItem }) {
  const followup = item.kind === "followup";
  return (
    <tr className={cn("align-top", followup && "bg-gray-50/60")}>
      <Td className="align-top">
        <div className={cn(followup && "border-l-2 border-line pl-3")}>
          <div className="font-mono text-sm font-medium">{item.item_code}</div>
          <div className="mt-0.5 flex flex-wrap gap-1">
            {item.term ? <Chip tone="gray">{item.term}</Chip> : null}
            <span className="text-sm text-ink-subtle">{followup ? "follow-up" : humanize(item.kind)}</span>
          </div>
        </div>
      </Td>
      {(["en", "es"] as const).map((lang) => (
        <Td key={lang} className="align-top">
          <p lang={lang} className="text-[15px] leading-6 text-ink">
            {item.text[lang] ?? <span className="text-ink-subtle">—</span>}
          </p>
          {item.options_say?.[lang] ? (
            <p lang={lang} className="mt-1 text-sm text-ink-muted">
              {item.options_say[lang]}
            </p>
          ) : null}
        </Td>
      ))}
    </tr>
  );
}
