"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, CheckCircle2, Download, PenLine, Save, Send } from "lucide-react";
import type { SAEReport } from "@/lib/types";
import { useApiMutation, useSae } from "@/lib/queries";
import { useIdentity } from "@/lib/role";
import { API_BASE_URL, USE_FIXTURES, isApiError } from "@/lib/api";
import { formatAbsolute, formatClock, formatDay, formatSpan, humanize, parseTs } from "@/lib/format";
import { RELATEDNESS_LABELS, SERIOUSNESS_LABELS } from "@/lib/labels";
import { Button, ButtonLink, Card, CardHeader, EmptyState, ErrorState, Field, Label, Skeleton, inputClass } from "@/components/ui/primitives";
import { Chip, SaeStatusChip } from "@/components/chips";
import { CountdownClock } from "@/components/CountdownClock";
import { GradeBadge } from "@/components/GradeBadge";
import { AiBlock, AiLabel } from "@/components/AiLabel";

export default function SaePage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const q = useSae(id);

  if (q.isPending)
    return (
      <div className="space-y-4">
        <Skeleton className="h-32" />
        <Skeleton className="h-96" />
      </div>
    );
  if (q.isError) {
    if (isApiError(q.error) && q.error.status === 404)
      return (
        <Card>
          <EmptyState title="Report not found" action={<ButtonLink href="/review">Back to review</ButtonLink>}>
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
    <div className="space-y-4">
      <Link href="/review?status=confirmed" className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden />
        Review queue
      </Link>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
        <Card className="p-5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Serious-event report</h1>
            <SaeStatusChip status={sae.status} />
            <Chip tone="gray">{humanize(p.report_type)} report</Chip>
          </div>
          <p className="mt-1 text-base text-ink-muted">
            <span className="font-mono">{p.patient.subject_id}</span> · {p.reaction.term} · CIOMS I style
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label="Site aware">{formatAbsolute(sae.aware_at)}</Field>
            <Field label="Due to sponsor">{formatAbsolute(sae.due_at)}</Field>
            <Field label="Signed">{sae.signed_by ? `${sae.signed_by}, ${formatAbsolute(sae.signed_at)}` : "Not yet"}</Field>
            <Field label="Sent">{sae.sent_at ? formatAbsolute(sae.sent_at) : "Not yet"}</Field>
          </dl>
          {sent && received !== null ? (
            <div className="mt-4 flex items-center gap-2 rounded-md bg-green-700 px-3 py-2.5 text-white">
              <CheckCircle2 className="size-5 shrink-0" aria-hidden />
              <span className="text-[15px]">
                Received by sponsor at <strong className="tabular">{formatClock(sae.sponsor_received_at)}</strong>
                {margin !== null ? (margin >= 0 ? `, ${formatSpan(margin)} before deadline` : `, ${formatSpan(-margin)} after deadline`) : ""}
              </span>
            </div>
          ) : null}
        </Card>
        <CountdownClock dueAt={sae.due_at} stoppedAt={sae.sponsor_received_at} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="1 · Patient">
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

        <Section title="2 · Reaction">
          <Field label="Event term (CTCAE)">{p.reaction.term}</Field>
          <Field label="Onset">{formatDay(p.reaction.onset_date)}</Field>
          <Field label="Grade">
            <GradeBadge grade={p.reaction.provisional_ctcae_grade} />
            <span className="ml-1 text-ink-subtle">CTCAE v{p.reaction.ctcae_version}</span>
          </Field>
          <Field label="Outcome">{humanize(p.reaction.outcome)}</Field>
          <Field label="Description" className="col-span-2">
            {p.reaction.description}
          </Field>
        </Section>

        <Section title="3 · Seriousness">
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

        <Section title="4 · Suspect product">
          <Field label="Product" className="col-span-2">
            {p.suspect_product.description}
          </Field>
          <Field label="Route">{humanize(p.suspect_product.route)}</Field>
          <Field label="Last dose">{formatDay(p.suspect_product.last_dose_date)}</Field>
          <Field label="Concomitant medications" className="col-span-2">
            {p.concomitant.length ? p.concomitant.map((c) => `${c.medication}${c.otc ? " (OTC)" : ""}${c.start_date ? `, from ${formatDay(c.start_date)}` : ""}`).join("; ") : "None reported"}
          </Field>
        </Section>

        <Section title="5 · Causality">
          <Field label="Assessed by">{p.causality.assessed_by}</Field>
          <Field label="Result">{p.causality.result ? RELATEDNESS_LABELS[p.causality.result] : "—"}</Field>
        </Section>

        <Section title="6 · Reporter">
          <Field label="Name">{p.reporter.name}</Field>
          <Field label="Role">{humanize(p.reporter.role)}</Field>
          <Field label="Site" className="col-span-2">
            {p.reporter.site}
          </Field>
        </Section>
      </div>

      <Card>
        <CardHeader title="7 · Narrative" subtitle="The AI draft uses only facts in this report and the evidence quotes. The investigator edits and signs the final version." />
        <div className="grid gap-4 p-4 lg:grid-cols-2">
          <AiBlock label="AI draft">
            <p className="leading-6 whitespace-pre-wrap">{sae.narrative_ai_draft}</p>
          </AiBlock>
          <div>
            <div className="mb-1 flex items-center gap-2">
              <Label htmlFor="narrative">Final narrative (investigator)</Label>
              {!sae.narrative_final ? <AiLabel>Prefilled from AI draft</AiLabel> : null}
            </div>
            <textarea
              id="narrative"
              className={inputClass}
              rows={9}
              value={narrative}
              onChange={(e) => setNarrative(e.target.value)}
              disabled={!isInvestigator || sent}
            />
            {!isInvestigator && !sent ? <p className="mt-1 text-sm text-ink-subtle">Switch the demo role to Investigator to edit and sign.</p> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-line bg-gray-50/70 px-4 py-3">
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!isInvestigator || sent || !dirty || busy} icon={<Save className="size-4" aria-hidden />}>
            Save
          </Button>
          <Button
            variant="primary"
            onClick={() => (dirty ? save.mutateAsync().then(() => sign.mutate()).catch(() => undefined) : sign.mutate())}
            loading={sign.isPending}
            disabled={!isInvestigator || sae.status !== "draft" || busy}
            icon={<PenLine className="size-4" aria-hidden />}
          >
            {sae.status === "draft" ? `Sign as ${isInvestigator ? identity.user : "investigator"}` : "Signed"}
          </Button>
          <Button variant="success" onClick={() => send.mutate()} loading={send.isPending} disabled={sae.status !== "signed" || busy} icon={<Send className="size-4" aria-hidden />}>
            {sent ? "Sent to sponsor" : "Send to sponsor"}
          </Button>
          {!USE_FIXTURES ? (
            <a href={`${API_BASE_URL}/api/export/sae/${encodeURIComponent(sae.id)}.json`} className="ml-auto inline-flex items-center gap-1.5 text-sm font-medium text-accent-700 hover:underline" target="_blank" rel="noreferrer">
              <Download className="size-4" aria-hidden />
              CIOMS JSON
            </a>
          ) : null}
          {sent ? (
            <Link href="/sponsor" className="text-sm font-medium text-accent-700 hover:underline">
              View in sponsor inbox
            </Link>
          ) : null}
        </div>
      </Card>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader title={title} />
      <dl className="grid grid-cols-2 gap-3 p-4">{children}</dl>
    </Card>
  );
}
