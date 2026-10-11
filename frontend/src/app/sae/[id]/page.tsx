"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Check, CheckCircle2, FilePlus2, Inbox, PenLine, Save, Send } from "lucide-react";
import type { SAEReport } from "@/lib/types";
import { useApiMutation, useSae } from "@/lib/queries";
import { useIdentity } from "@/lib/role";
import { hasErrorCode } from "@/lib/api";
import { formatAbsolute, formatClock, formatDay, formatSpan, humanize, parseTs } from "@/lib/format";
import { RELATEDNESS_LABELS, SERIOUSNESS_LABELS } from "@/lib/labels";
import { Button, ButtonLink, Card, CardHeader, EmptyState, ErrorState, Field, Label, Skeleton, inputClass, cn } from "@/components/ui/primitives";
import { Chip, SaeStatusChip } from "@/components/chips";
import { CountdownClock } from "@/components/CountdownClock";
import { GradeBadge } from "@/components/GradeBadge";
import { AiBlock, AiLabel } from "@/components/AiLabel";
import { DownloadButton } from "@/components/DownloadButton";

export default function SaePage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const q = useSae(id);

  if (q.isPending)
    return (
      <div className="space-y-5">
        <Skeleton className="h-5 w-32" />
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)]">
          <Skeleton className="h-56 rounded-2xl" />
          <Skeleton className="h-56 rounded-2xl" />
        </div>
        <Skeleton className="h-96 rounded-2xl" />
      </div>
    );
  if (q.isError) {
    if (hasErrorCode(q.error, "sae_not_found"))
      return (
        <Card>
          <EmptyState title="Report not found" action={<ButtonLink href="/sae">All serious-event reports</ButtonLink>}>
            No serious-event report with ID <code className="font-mono">{id}</code>.
          </EmptyState>
        </Card>
      );
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />;
  }
  return <SaeView key={q.data.id} sae={q.data} />;
}

function SaeView({ sae }: { sae: SAEReport }) {
  const identity = useIdentity();
  const isInvestigator = identity.role === "investigator";
  const sent = sae.status === "sent";
  const [narrative, setNarrative] = useState(sae.narrative_final ?? sae.narrative_ai_draft);
  const dirty = narrative !== (sae.narrative_final ?? sae.narrative_ai_draft);
  const inv = [["sae", sae.id], ["sae-list"], ["sponsor-inbox"], ["audit"]];

  const save = useApiMutation<void, SAEReport>({
    request: () => ({ path: `/api/sae/${encodeURIComponent(sae.id)}`, init: { method: "PATCH", body: { narrative_final: narrative } } }),
    success: "Report saved",
    invalidate: inv,
  });
  const sign = useApiMutation<void, SAEReport>({
    request: () => ({ path: `/api/sae/${encodeURIComponent(sae.id)}/sign`, init: { method: "POST" } }),
    success: "Report signed",
    invalidate: inv,
  });
  const send = useApiMutation<void, SAEReport>({
    request: () => ({ path: `/api/sae/${encodeURIComponent(sae.id)}/send`, init: { method: "POST" } }),
    success: (r) => `Received by sponsor at ${formatClock(r.sponsor_received_at)}`,
    invalidate: inv,
  });
  const busy = save.isPending || sign.isPending || send.isPending;
  const p = sae.payload;

  const received = parseTs(sae.sponsor_received_at);
  const due = parseTs(sae.due_at);
  const margin = received !== null && due !== null ? (due - received) / 1000 : null;

  return (
    <div className="space-y-5">
      <Link href="/sae" className="inline-flex items-center gap-1.5 rounded-md text-sm font-medium text-ink-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden />
        Serious-event reports
      </Link>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,30rem)]">
        <Card className="relative overflow-hidden p-6">
          <div className="bv-grid-light pointer-events-none absolute inset-y-0 right-0 w-2/5 [mask-image:linear-gradient(to_left,black,transparent)]" aria-hidden />
          <div className="relative">
            <div className="flex flex-wrap items-center gap-2">
              <SaeStatusChip status={sae.status} />
              <Chip tone="gray">{humanize(p.report_type)} report</Chip>
              <Chip tone="gray">CIOMS I style</Chip>
            </div>
            <h1 className="mt-3 font-display text-[2.5rem] leading-[1.05] text-ink">Serious-event report</h1>
            <p className="mt-2 text-base text-ink-muted">
              <span className="font-mono font-medium text-ink">{p.patient.subject_id}</span> · {p.reaction.term} · {p.study.nct_id}, site {p.study.site_id}
            </p>

            <ol className="mt-6 grid gap-3 sm:grid-cols-3" aria-label="Report progress">
              <Milestone done label="Drafted" detail={`Site aware ${formatAbsolute(sae.aware_at)}`} icon={<FilePlus2 className="size-4" aria-hidden />} />
              <Milestone
                done={!!sae.signed_by}
                label="Signed by investigator"
                detail={sae.signed_by ? `${sae.signed_by}, ${formatAbsolute(sae.signed_at)}` : "Not yet"}
                icon={<PenLine className="size-4" aria-hidden />}
              />
              <Milestone
                done={sent}
                label="Received by sponsor"
                detail={sae.sent_at ? formatAbsolute(sae.sponsor_received_at ?? sae.sent_at) : `Due ${formatAbsolute(sae.due_at)}`}
                icon={<Inbox className="size-4" aria-hidden />}
              />
            </ol>

            {sent && received !== null ? (
              <div className="mt-5 flex items-center gap-3 rounded-xl bg-gradient-to-r from-green-700 to-green-800 px-4 py-3 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.15)]">
                <CheckCircle2 className="size-5 shrink-0" aria-hidden />
                <span className="text-[15px]">
                  Received by sponsor at <strong className="tabular">{formatClock(sae.sponsor_received_at)}</strong>
                  {margin !== null ? (margin >= 0 ? `, ${formatSpan(margin)} before deadline` : `, ${formatSpan(-margin)} after deadline`) : ""}
                </span>
              </div>
            ) : null}
          </div>
        </Card>
        <CountdownClock dueAt={sae.due_at} stoppedAt={sae.sponsor_received_at} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section n={1} title="Patient">
          <Field label="Subject ID">
            <span className="font-mono">{p.patient.subject_id}</span>
          </Field>
          <Field label="Initials">{p.patient.initials ?? "—"}</Field>
          <Field label="Age">{p.patient.age ?? "—"}</Field>
          <Field label="Sex">{p.patient.sex ?? "—"}</Field>
          <Field label="Country">{p.patient.country ?? "—"}</Field>
          <Field label="Study / site">
            {p.study.nct_id} · site {p.study.site_id}
          </Field>
        </Section>

        <Section n={2} title="Reaction">
          <Field label="Event term (CTCAE)">{p.reaction.term}</Field>
          <Field label="Onset">{formatDay(p.reaction.onset_date)}</Field>
          <Field label="Grade">
            <span className="inline-flex flex-wrap items-center gap-1.5">
              <GradeBadge grade={p.reaction.provisional_ctcae_grade} />
              <span className="text-sm font-normal text-ink-subtle">CTCAE v{p.reaction.ctcae_version}</span>
            </span>
          </Field>
          <Field label="Outcome">{humanize(p.reaction.outcome)}</Field>
          <Field label="Description" className="col-span-2">
            {p.reaction.description}
          </Field>
        </Section>

        <Section n={3} title="Seriousness">
          <div className="col-span-2 flex flex-wrap gap-1.5">
            {p.seriousness.length ? (
              p.seriousness.map((c) => (
                <Chip key={c} tone="red">
                  {SERIOUSNESS_LABELS[c]}
                </Chip>
              ))
            ) : (
              <span className="text-sm text-ink-subtle">None recorded</span>
            )}
          </div>
        </Section>

        <Section n={4} title="Suspect product">
          <Field label="Product" className="col-span-2">
            {p.suspect_product.description}
          </Field>
          <Field label="Route">{humanize(p.suspect_product.route)}</Field>
          <Field label="Last dose">{formatDay(p.suspect_product.last_dose_date)}</Field>
          <Field label="Concomitant medications" className="col-span-2">
            {p.concomitant.length ? p.concomitant.map((c) => `${c.medication}${c.otc ? " (OTC)" : ""}${c.start_date ? `, from ${formatDay(c.start_date)}` : ""}`).join("; ") : "None reported"}
          </Field>
        </Section>

        <Section n={5} title="Causality">
          <Field label="Assessed by">{p.causality.assessed_by}</Field>
          <Field label="Result">{p.causality.result ? RELATEDNESS_LABELS[p.causality.result] : "—"}</Field>
        </Section>

        <Section n={6} title="Reporter">
          <Field label="Name">{p.reporter.name}</Field>
          <Field label="Role">{humanize(p.reporter.role)}</Field>
          <Field label="Site" className="col-span-2">
            {p.reporter.site}
          </Field>
        </Section>
      </div>

      <Card className="overflow-hidden">
        <CardHeader
          icon={<span className="font-mono text-sm font-semibold">7</span>}
          title="Narrative"
          subtitle="The AI draft uses only facts in this report and the evidence quotes. The investigator edits and signs the final version."
        />
        <div className="grid gap-5 p-5 lg:grid-cols-2">
          <AiBlock label="AI draft">
            <p className="whitespace-pre-wrap">{sae.narrative_ai_draft}</p>
          </AiBlock>
          <div>
            <div className="mb-1.5 flex items-center gap-2">
              <Label htmlFor="narrative">Final narrative (investigator)</Label>
              {!sae.narrative_final ? <AiLabel className="mb-1.5">Prefilled from AI draft</AiLabel> : null}
            </div>
            <textarea
              id="narrative"
              className={cn(inputClass, "text-[15px] leading-7")}
              rows={10}
              value={narrative}
              onChange={(e) => setNarrative(e.target.value)}
              disabled={!isInvestigator || sent}
            />
            {!isInvestigator && !sent ? <p className="mt-1.5 text-sm text-ink-subtle">Switch the demo role to Investigator to edit and sign.</p> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-line bg-gray-50/80 px-5 py-4">
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!isInvestigator || sent || !dirty || busy} icon={<Save className="size-4" aria-hidden />}>
            Save
          </Button>
          <Button
            variant="primary"
            onClick={() => (dirty ? save.mutateAsync().then(() => sign.mutate()).catch(() => undefined) : sign.mutate())}
            loading={sign.isPending}
            disabled={!isInvestigator || sae.status !== "draft" || busy}
            icon={sae.status === "draft" ? <PenLine className="size-4" aria-hidden /> : <Check className="size-4" aria-hidden />}
          >
            {sae.status === "draft" ? `Sign as ${isInvestigator ? identity.user : "investigator"}` : "Signed"}
          </Button>
          <Button variant="success" size="lg" onClick={() => send.mutate()} loading={send.isPending} disabled={sae.status !== "signed" || busy} icon={<Send className="size-4" aria-hidden />}>
            {sent ? "Sent to sponsor" : "Send to sponsor"}
          </Button>
          <div className="ml-auto flex flex-wrap items-center gap-4">
            <DownloadButton path={`/api/export/sae/${encodeURIComponent(sae.id)}.json`} filename={`${sae.id}.json`} variant="ghost" size="md">
              Download CIOMS JSON
            </DownloadButton>
            {sent ? (
              <Link href="/sponsor" className="inline-flex items-center gap-1.5 rounded-md text-sm font-medium text-accent-700 hover:underline">
                <Inbox className="size-4" aria-hidden />
                View in sponsor inbox
              </Link>
            ) : null}
          </div>
        </div>
      </Card>
    </div>
  );
}

function Milestone({ done, label, detail, icon }: { done: boolean; label: string; detail: string; icon: React.ReactNode }) {
  return (
    <li className={cn("rounded-xl border p-3", done ? "border-green-200 bg-green-50/70" : "border-dashed border-line-strong bg-white")}>
      <div className="flex items-center gap-2">
        <span className={cn("flex size-7 items-center justify-center rounded-full", done ? "bg-green-700 text-white" : "bg-gray-100 text-ink-subtle")}>
          {done ? <Check className="size-4" aria-hidden /> : icon}
        </span>
        <span className={cn("text-sm font-semibold", done ? "text-green-900" : "text-ink-muted")}>{label}</span>
        <span className="sr-only">{done ? "(done)" : "(not yet)"}</span>
      </div>
      <p className="mt-1.5 text-sm leading-5 text-ink-muted">{detail}</p>
    </li>
  );
}

function Section({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader icon={<span className="font-mono text-sm font-semibold">{n}</span>} title={title} />
      <dl className="grid grid-cols-2 gap-4 p-5">{children}</dl>
    </Card>
  );
}
