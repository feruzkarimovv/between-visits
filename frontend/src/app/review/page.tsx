"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { toast } from "sonner";
import { ArrowUpRight, Check, ClipboardCheck, FileWarning, Hourglass, Pencil, PenLine, ShieldAlert, X, XCircle } from "lucide-react";
import type {
  AEPayload,
  CMPayload,
  DraftEntry,
  InvestigatorRequest,
  InvestigatorResponse,
  NurseTaskPayload,
  Relatedness,
  SeriousnessCriterion,
} from "@/lib/types";
import { useApiMutation, useDrafts, usePatients, type DraftFilters } from "@/lib/queries";
import { useIdentity } from "@/lib/role";
import { formatDay, fullName, humanize } from "@/lib/format";
import { NURSE_TASK_LABELS, RELATEDNESS_LABELS, RELATEDNESS_ORDER, SERIOUSNESS_LABELS, SERIOUSNESS_ORDER } from "@/lib/labels";
import {
  Avatar,
  Button,
  ButtonLink,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Label,
  LoadingRows,
  PageHeader,
  Segmented,
  inputClass,
  selectClass,
  cn,
} from "@/components/ui/primitives";
import { Chip, DraftStatusChip, OriginTag } from "@/components/chips";
import { GradeBadge } from "@/components/GradeBadge";
import { EvidenceQuote } from "@/components/EvidenceQuote";
import { AiLabel } from "@/components/AiLabel";
import { RelativeTime } from "@/components/RelativeTime";
import { DraftKindIcon, KIND_LABEL, draftTitle } from "@/components/DraftKind";
import { ExportDownloads } from "@/components/DownloadButton";

export default function ReviewPage() {
  return (
    <Suspense fallback={<LoadingRows rows={4} />}>
      <ReviewQueue />
    </Suspense>
  );
}

const KINDS = [
  { value: "", label: "All kinds" },
  { value: "AE", label: "Side effects (AE)" },
  { value: "CM", label: "Medications (CM)" },
  { value: "NURSE_TASK", label: "Nurse tasks" },
];

type StatusValue = "draft" | "confirmed" | "rejected" | "";

const STATUSES: { value: StatusValue; label: string }[] = [
  { value: "draft", label: "Needs review" },
  { value: "confirmed", label: "Confirmed" },
  { value: "rejected", label: "Rejected" },
  { value: "", label: "All" },
];

function ReviewQueue() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const identity = useIdentity();
  const filters: DraftFilters = {
    // Investigators mostly work on confirmed AEs awaiting their signature.
    status: sp.get("status") ?? (identity.role === "investigator" ? "confirmed" : "draft"),
    kind: sp.get("kind") ?? "",
    patient_id: sp.get("patient_id") ?? "",
    checkin_id: sp.get("checkin_id") ?? "",
  };
  const drafts = useDrafts(filters);
  // Same filters without the status, for the counts on the status tabs.
  const all = useDrafts({ ...filters, status: "" });
  const patients = usePatients();

  const setFilter = (key: keyof DraftFilters, value: string) => {
    const next = new URLSearchParams(sp.toString());
    if (key === "status") next.set("status", value);
    else if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  const list = drafts.data ?? [];
  const counts = (s: StatusValue) => (all.data ? (s ? all.data.filter((d) => d.status === s).length : all.data.length) : null);

  return (
    <>
      <PageHeader
        eyebrow="Humans decide"
        title="Review queue"
        subtitle="Every entry is a draft until someone on the study team confirms it. Evidence shows the patient's own words, in their language, with the second it was said."
        actions={<ExportDownloads />}
      />

      <div className="mb-5 flex flex-wrap items-end gap-3 rounded-2xl border border-line bg-white p-3 shadow-card">
        <div className="max-w-full min-w-0">
          <div className="mb-1.5 text-sm font-medium text-ink-muted">Status</div>
          <Segmented<StatusValue>
            className="max-w-full overflow-x-auto"
            label="Status"
            value={(filters.status ?? "") as StatusValue}
            onChange={(v) => setFilter("status", v)}
            options={STATUSES.map((s) => ({ value: s.value, label: s.label, count: counts(s.value) }))}
          />
        </div>
        <div>
          <Label htmlFor="f-kind">Kind</Label>
          <select id="f-kind" className={cn(selectClass, "h-10 w-48")} value={filters.kind} onChange={(e) => setFilter("kind", e.target.value)}>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="f-patient">Patient</Label>
          <select id="f-patient" className={cn(selectClass, "h-10 w-60")} value={filters.patient_id} onChange={(e) => setFilter("patient_id", e.target.value)}>
            <option value="">All patients</option>
            {(patients.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.subject_id} · {fullName(p)}
              </option>
            ))}
          </select>
        </div>
        {filters.checkin_id ? (
          <div className="flex h-10 items-center">
            <Chip tone="accent" className="h-8 pr-1">
              Check-in <span className="font-mono">{filters.checkin_id}</span>
              <button type="button" onClick={() => setFilter("checkin_id", "")} className="ml-1 rounded-full p-0.5 hover:bg-accent-100" aria-label="Clear check-in filter">
                <X className="size-3.5" aria-hidden />
              </button>
            </Chip>
          </div>
        ) : null}
        <div className="ml-auto flex h-10 items-center px-2 text-sm text-ink-subtle tabular">
          {drafts.data ? `${list.length} entr${list.length === 1 ? "y" : "ies"}` : ""}
        </div>
      </div>

      {drafts.isPending ? (
        <LoadingRows rows={3} />
      ) : drafts.isError ? (
        <ErrorState error={drafts.error} onRetry={() => void drafts.refetch()} retrying={drafts.isFetching} />
      ) : list.length === 0 ? (
        <Card>
          <EmptyState icon={<ClipboardCheck className="size-6" aria-hidden />} title={filters.status === "draft" ? "Nothing waiting for review." : "No entries match these filters."}>
            Draft side-effect, medication and nurse-task entries appear here after each check-in.
          </EmptyState>
        </Card>
      ) : (
        <div className="space-y-5">
          {list.map((d) => (
            <DraftCard key={d.id} draft={d} />
          ))}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- draft card

function DraftCard({ draft: d }: { draft: DraftEntry }) {
  const [mode, setMode] = useState<"view" | "edit" | "reject">("view");
  const [rejectReason, setRejectReason] = useState("");
  const nonEnglish = d.evidence.some((e) => e.quote_lang !== "en");
  const invalidate = [["drafts"], ["checkin", d.checkin_id], ["audit"]];

  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const confirm = useApiMutation<void, DraftEntry>({
    request: () => ({ path: `/api/drafts/${encodeURIComponent(d.id)}/confirm`, init: { method: "POST", body: { note: null } } }),
    invalidate,
    onSuccess: () => {
      if (d.kind !== "AE") {
        toast.success("Draft confirmed");
        return;
      }
      toast.success("Draft confirmed", {
        description: "Confirmed side effects wait for the investigator's seriousness assessment.",
        action: {
          label: "Show confirmed",
          onClick: () => {
            const next = new URLSearchParams(sp.toString());
            next.set("status", "confirmed");
            router.replace(`${pathname}?${next.toString()}`, { scroll: false });
          },
        },
      });
    },
  });
  const reject = useApiMutation<string, DraftEntry>({
    request: (reason) => ({ path: `/api/drafts/${encodeURIComponent(d.id)}/reject`, init: { method: "POST", body: { reason } } }),
    success: "Draft rejected",
    invalidate,
    onSuccess: () => setMode("view"),
  });
  const busy = confirm.isPending || reject.isPending;
  const patientName = d.patient ? fullName(d.patient) || d.patient.subject_id : null;

  return (
    <Card as="article" className={cn("bv-enter overflow-hidden", d.status === "rejected" && "opacity-75")}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-line px-5 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <DraftKindIcon kind={d.kind} className="size-11" />
          <div className="min-w-0">
            <div className="text-sm text-ink-subtle">{KIND_LABEL[d.kind]}</div>
            <h2 className="truncate text-xl leading-7 font-semibold text-ink">{draftTitle(d)}</h2>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {d.kind === "AE" ? <GradeBadge grade={d.payload.provisional_grade} /> : null}
          <DraftStatusChip status={d.status} />
          {d.kind === "AE" && d.status === "confirmed" ? <OriginTag origin={d.origin} /> : null}
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-subtle">
          {d.patient && patientName ? (
            <Link href={`/patients/${d.patient.id}`} className="group inline-flex items-center gap-2">
              <Avatar name={patientName} seed={d.patient.id} size="sm" />
              <span className="leading-tight">
                <span className="block font-medium text-ink group-hover:underline">{patientName}</span>
                <span className="font-mono">{d.patient.subject_id}</span>
              </span>
            </Link>
          ) : null}
          <span className="flex flex-col items-end leading-tight">
            <Link href={`/checkins/${d.checkin_id}`} className="inline-flex items-center gap-0.5 font-medium text-accent-700 hover:underline">
              Open check-in
              <ArrowUpRight className="size-3.5" aria-hidden />
            </Link>
            {d.created_at ? <RelativeTime iso={d.created_at} /> : null}
          </span>
        </div>
      </div>

      <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="min-w-0 space-y-4">
          {mode === "edit" ? <EditForm draft={d} onDone={() => setMode("view")} /> : <PayloadView draft={d} nonEnglish={nonEnglish} />}
          {d.status !== "draft" && d.reviewed_by ? (
            <p className="flex flex-wrap items-center gap-1.5 rounded-lg bg-gray-50 px-3 py-2 text-sm text-ink-muted">
              {d.status === "confirmed" ? <Check className="size-4 text-green-700" aria-hidden /> : <XCircle className="size-4 text-ink-subtle" aria-hidden />}
              {d.status === "confirmed" ? "Confirmed" : "Rejected"} by <strong className="text-ink">{d.reviewed_by}</strong>{" "}
              {d.reviewed_at ? <RelativeTime iso={d.reviewed_at} /> : null}
              {d.review_note ? <> · “{d.review_note}”</> : null}
            </p>
          ) : null}
        </div>
        <div className="min-w-0 space-y-3">
          <h3 className="flex items-center gap-2 text-sm font-medium text-ink-subtle">
            Evidence
            <span className="rounded-full bg-gray-100 px-1.5 text-ink-muted tabular">{d.evidence.length}</span>
          </h3>
          {d.evidence.length === 0 ? (
            <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-900">No evidence attached. Don&apos;t confirm without checking the call.</p>
          ) : (
            d.evidence.map((ev, i) => <EvidenceQuote key={i} evidence={ev} checkinId={d.checkin_id} />)
          )}
        </div>
      </div>

      {d.status === "draft" && mode !== "edit" ? (
        <div className="border-t border-line bg-gray-50/80 px-5 py-3.5">
          {mode === "reject" ? (
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (rejectReason.trim()) reject.mutate(rejectReason.trim());
              }}
            >
              <div className="min-w-64 flex-1">
                <Label htmlFor={`reason-${d.id}`}>Reason for rejecting (required)</Label>
                <input id={`reason-${d.id}`} className={inputClass} value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="e.g. Duplicate of earlier report" autoFocus />
              </div>
              <Button type="submit" variant="danger" loading={reject.isPending} disabled={!rejectReason.trim()} icon={<XCircle className="size-4" aria-hidden />}>
                Reject draft
              </Button>
              <Button variant="ghost" onClick={() => setMode("view")}>
                Cancel
              </Button>
            </form>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="success" loading={confirm.isPending} disabled={busy} onClick={() => confirm.mutate()} icon={<Check className="size-4" aria-hidden />}>
                Confirm
              </Button>
              <Button disabled={busy} onClick={() => setMode("edit")} icon={<Pencil className="size-4" aria-hidden />}>
                Edit
              </Button>
              <Button variant="ghost" disabled={busy} onClick={() => setMode("reject")} icon={<X className="size-4" aria-hidden />}>
                Reject
              </Button>
              <span className="ml-auto hidden text-sm text-ink-subtle sm:block">Your decision is saved to the audit trail.</span>
            </div>
          )}
        </div>
      ) : null}

      {d.kind === "AE" && d.status === "confirmed" ? <InvestigatorPanel draft={d} /> : null}
    </Card>
  );
}

function PayloadView({ draft: d, nonEnglish }: { draft: DraftEntry; nonEnglish: boolean }) {
  if (d.kind === "AE") {
    const p = d.payload;
    return (
      <>
        <div>
          <div className="mb-1.5 flex items-center gap-2 text-sm text-ink-subtle">
            Verbatim (English){nonEnglish ? <AiLabel>AI translation, verify</AiLabel> : null}
          </div>
          <p className="text-lg leading-7 text-ink">{p.verbatim_en}</p>
        </div>
        <dl className="grid grid-cols-2 gap-4">
          <Field label="Onset">{formatDay(p.onset_date)}</Field>
          <Field label="Ongoing">{p.ongoing ? "Yes" : "No"}</Field>
        </dl>
        <div className="rounded-xl border border-line bg-gray-50/70 p-3.5 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <GradeBadge grade={p.provisional_grade} />
            {p.rule_id ? <span className="font-mono text-ink-muted">{p.rule_id}</span> : null}
          </div>
          <p className="mt-2 leading-6 text-ink-muted">
            {p.grade_basis === "rule" && p.rule_text ? (
              <>
                <span className="font-medium text-ink">CTCAE v5.0:</span> {p.rule_text}
              </>
            ) : (
              "No phone-gradable CTCAE rule. A clinician assigns the grade."
            )}
          </p>
          {p.answers.length ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {p.answers.map((a, i) => (
                <code key={i} className="rounded-md bg-white px-1.5 py-0.5 font-mono text-sm text-ink-muted ring-1 ring-line">
                  {humanize(a.item_code)} = {a.numeric_value ?? humanize(a.option_code ?? "")}
                </code>
              ))}
            </div>
          ) : null}
        </div>
      </>
    );
  }
  if (d.kind === "CM") {
    const p = d.payload;
    return (
      <dl className="grid grid-cols-2 gap-4">
        <Field label="Medication">{p.medication_name}</Field>
        {p.as_reported_en ? (
          <Field label={<span className="flex flex-wrap items-center gap-1.5">As reported <AiLabel>AI extraction, verify</AiLabel></span>}>{p.as_reported_en}</Field>
        ) : null}
        <Field label="Over the counter">{p.otc ? "Yes" : "No"}</Field>
        <Field label={<span className="flex flex-wrap items-center gap-1.5">Indication {nonEnglish ? <AiLabel>AI translation, verify</AiLabel> : null}</span>}>{p.indication_en ?? "—"}</Field>
        <Field label="Start date">{formatDay(p.start_date)}</Field>
        <Field label="Dose">{p.dose_text ?? "Not reported"}</Field>
      </dl>
    );
  }
  const p = d.payload;
  return (
    <div className="space-y-3">
      <Field label="Category">{NURSE_TASK_LABELS[p.category] ?? humanize(p.category)}</Field>
      <div>
        <div className="mb-1.5 flex items-center gap-2 text-sm text-ink-subtle">
          What the patient asked or said{nonEnglish ? <AiLabel>AI translation, verify</AiLabel> : null}
        </div>
        <p className="text-lg leading-7 text-ink">{p.text_en}</p>
        {p.detail ? <p className="mt-1 text-sm text-ink-muted">{p.detail}</p> : null}
      </div>
      {p.category === "medical_question" ? (
        <p className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">The agent gave no advice and told the patient the nurse will follow up.</p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- edit

function EditForm({ draft: d, onDone }: { draft: DraftEntry; onDone: () => void }) {
  const [ae, setAe] = useState<Partial<AEPayload>>(d.kind === "AE" ? { onset_date: d.payload.onset_date, ongoing: d.payload.ongoing, provisional_grade: d.payload.provisional_grade, verbatim_en: d.payload.verbatim_en } : {});
  const [cm, setCm] = useState<Partial<CMPayload>>(d.kind === "CM" ? { ...d.payload } : {});
  const [task, setTask] = useState<Partial<NurseTaskPayload>>(d.kind === "NURSE_TASK" ? { ...d.payload } : {});
  const [note, setNote] = useState("");
  const save = useApiMutation<void, DraftEntry>({
    request: () => ({
      path: `/api/drafts/${encodeURIComponent(d.id)}`,
      init: { method: "PATCH", body: { payload: d.kind === "AE" ? ae : d.kind === "CM" ? cm : task, note: note.trim() || null } },
    }),
    success: "Draft saved",
    invalidate: [["drafts"], ["audit"], ["checkin", d.checkin_id]],
    onSuccess: onDone,
  });
  const id = (k: string) => `${d.id}-${k}`;

  return (
    <form
      className="space-y-3 rounded-xl border border-accent-200 bg-accent-50/40 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-accent-900">
        <Pencil className="size-4" aria-hidden />
        Editing draft
      </div>
      {d.kind === "AE" ? (
        <>
          <div>
            <Label htmlFor={id("verbatim")}>Verbatim (English)</Label>
            <textarea id={id("verbatim")} className={inputClass} rows={2} value={ae.verbatim_en ?? ""} onChange={(e) => setAe({ ...ae, verbatim_en: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor={id("onset")}>Onset date</Label>
              <input id={id("onset")} type="date" className={inputClass} value={ae.onset_date ?? ""} onChange={(e) => setAe({ ...ae, onset_date: e.target.value || null })} />
            </div>
            <div>
              <Label htmlFor={id("grade")}>Grade (clinician)</Label>
              <select
                id={id("grade")}
                className={selectClass}
                value={ae.provisional_grade ?? ""}
                onChange={(e) => setAe({ ...ae, provisional_grade: e.target.value ? Number(e.target.value) : null })}
              >
                <option value="">Not graded</option>
                {[1, 2, 3, 4, 5].map((g) => (
                  <option key={g} value={g}>
                    Grade {g}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-accent-700" checked={!!ae.ongoing} onChange={(e) => setAe({ ...ae, ongoing: e.target.checked })} />
            Ongoing
          </label>
        </>
      ) : d.kind === "CM" ? (
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label htmlFor={id("med")}>Medication (as reported)</Label>
            <input id={id("med")} className={inputClass} value={cm.medication_name ?? ""} onChange={(e) => setCm({ ...cm, medication_name: e.target.value })} />
          </div>
          <div>
            <Label htmlFor={id("ind")}>Indication</Label>
            <input id={id("ind")} className={inputClass} value={cm.indication_en ?? ""} onChange={(e) => setCm({ ...cm, indication_en: e.target.value || null })} />
          </div>
          <div>
            <Label htmlFor={id("start")}>Start date</Label>
            <input id={id("start")} type="date" className={inputClass} value={cm.start_date ?? ""} onChange={(e) => setCm({ ...cm, start_date: e.target.value || null })} />
          </div>
          <div>
            <Label htmlFor={id("dose")}>Dose</Label>
            <input id={id("dose")} className={inputClass} value={cm.dose_text ?? ""} onChange={(e) => setCm({ ...cm, dose_text: e.target.value || null })} />
          </div>
          <label className="flex items-center gap-2 self-end pb-2 text-sm">
            <input type="checkbox" className="size-4 accent-accent-700" checked={!!cm.otc} onChange={(e) => setCm({ ...cm, otc: e.target.checked })} />
            Over the counter
          </label>
        </div>
      ) : (
        <div>
          <Label htmlFor={id("task")}>Task text</Label>
          <textarea id={id("task")} className={inputClass} rows={2} value={task.text_en ?? ""} onChange={(e) => setTask({ ...task, text_en: e.target.value })} />
        </div>
      )}
      <div>
        <Label htmlFor={id("note")}>Why are you changing it? (saved to the audit trail)</Label>
        <input id={id("note")} className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Patient corrected the count on the nurse call" />
      </div>
      <div className="flex gap-2">
        <Button type="submit" variant="primary" loading={save.isPending}>
          Save
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={save.isPending}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- investigator

function InvestigatorPanel({ draft: d }: { draft: DraftEntry & { kind: "AE" } }) {
  const identity = useIdentity();
  const router = useRouter();
  const [criteria, setCriteria] = useState<SeriousnessCriterion[]>([]);
  const [relatedness, setRelatedness] = useState<Relatedness | "">("");
  const [createdSae, setCreatedSae] = useState<string | null>(null);
  const sign = useApiMutation<InvestigatorRequest, InvestigatorResponse>({
    request: (body) => ({ path: `/api/drafts/${encodeURIComponent(d.id)}/investigator`, init: { method: "POST", body } }),
    invalidate: [["drafts"], ["audit"], ["sae-list"]],
    success: (r) => (r.sae_report ? null : "Assessment signed"),
    onSuccess: (r) => {
      if (r.sae_report) {
        const id = r.sae_report.id;
        setCreatedSae(id);
        toast.success("Serious event: sponsor report drafted, 24-hour clock started", {
          duration: 12000,
          action: { label: "Open report", onClick: () => router.push(`/sae/${id}`) },
        });
      }
    },
  });

  const inv = d.investigator;
  const saeId = d.sae_report_id ?? createdSae;

  if (inv?.signed_by) {
    return (
      <div className={cn("border-t px-5 py-4", inv.is_serious ? "border-red-200 bg-red-50/50" : "border-line bg-white")}>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="flex size-8 items-center justify-center rounded-lg bg-white text-ink-muted ring-1 ring-line">
            <PenLine className="size-4" aria-hidden />
          </span>
          <span>
            Investigator assessment signed by <strong>{inv.signed_by}</strong> {inv.signed_at ? <RelativeTime iso={inv.signed_at} /> : null}
          </span>
          {inv.is_serious ? (
            <Chip tone="red" strong icon={<ShieldAlert className="size-3.5" aria-hidden />}>
              Serious
            </Chip>
          ) : (
            <Chip tone="gray">Not serious</Chip>
          )}
          {inv.seriousness_criteria.map((c) => (
            <Chip key={c} tone="red">
              {SERIOUSNESS_LABELS[c]}
            </Chip>
          ))}
          {inv.relatedness ? <Chip tone="gray">{RELATEDNESS_LABELS[inv.relatedness]}</Chip> : null}
          {saeId ? (
            <ButtonLink href={`/sae/${saeId}`} size="sm" variant="primary" icon={<FileWarning className="size-4" aria-hidden />} className="ml-auto">
              Open serious-event report
            </ButtonLink>
          ) : null}
        </div>
      </div>
    );
  }

  if (identity.role !== "investigator") {
    return (
      <div className="flex items-center gap-3 border-t border-line bg-gray-50/80 px-5 py-3.5 text-sm text-ink-muted">
        <Hourglass className="size-4 shrink-0 text-ink-subtle" aria-hidden />
        <span>
          Waiting for the investigator&apos;s seriousness and relatedness assessment. (Switch the demo role to <strong className="text-ink">Investigator</strong> to sign.)
        </span>
      </div>
    );
  }

  const serious = criteria.length > 0;
  return (
    <form
      className="border-t-2 border-accent-200 bg-gradient-to-b from-accent-50/70 to-white px-5 py-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!relatedness) return;
        sign.mutate({ is_serious: serious, seriousness_criteria: criteria, relatedness, sign: true });
      }}
    >
      <h3 className="flex items-center gap-2 text-base font-semibold">
        <PenLine className="size-4" aria-hidden />
        Investigator assessment
      </h3>
      <div className="mt-4 grid gap-6 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-ink-muted">Seriousness (ICH E2A): check all that apply</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {SERIOUSNESS_ORDER.map((c) => (
              <label
                key={c}
                className="flex min-h-11 cursor-pointer items-center gap-2.5 rounded-xl border border-line bg-white px-3 py-2 text-sm shadow-card transition-colors hover:border-gray-400/70 has-[:checked]:border-red-300 has-[:checked]:bg-red-50 has-[:checked]:text-red-950"
              >
                <input
                  type="checkbox"
                  className="size-4 accent-red-700"
                  checked={criteria.includes(c)}
                  onChange={(e) => setCriteria(e.target.checked ? [...criteria, c] : criteria.filter((x) => x !== c))}
                />
                {SERIOUSNESS_LABELS[c]}
              </label>
            ))}
          </div>
          <p className={cn("mt-3 rounded-lg px-3 py-2 text-sm", serious ? "bg-red-700 font-medium text-white" : "bg-gray-100 text-ink-muted")}>
            {serious ? "Serious: a sponsor report will be drafted and the 24-hour clock starts." : "No criteria checked: not serious."}
          </p>
        </fieldset>
        <div className="space-y-4">
          <div>
            <Label htmlFor={`rel-${d.id}`}>Relatedness to study drug</Label>
            <select
              id={`rel-${d.id}`}
              className={cn(selectClass, "h-11 bg-white shadow-card")}
              value={relatedness}
              onChange={(e) => setRelatedness(e.target.value as Relatedness | "")}
              required
            >
              <option value="">Select…</option>
              {RELATEDNESS_ORDER.map((r) => (
                <option key={r} value={r}>
                  {RELATEDNESS_LABELS[r]}
                </option>
              ))}
            </select>
            <div className="mt-2 flex items-center gap-2 text-sm text-ink-subtle" aria-hidden>
              <span className="flex gap-0.5">
                {RELATEDNESS_ORDER.map((r, j) => (
                  <span
                    key={r}
                    className={cn("h-3 w-1.5 rounded-sm", relatedness && j <= RELATEDNESS_ORDER.indexOf(relatedness) ? "bg-accent-600" : "bg-gray-200")}
                  />
                ))}
              </span>
              {relatedness ? RELATEDNESS_LABELS[relatedness] : "Not selected"}
            </div>
          </div>
          <Button type="submit" variant="primary" size="lg" className="w-full" loading={sign.isPending} disabled={!relatedness} icon={<PenLine className="size-4" aria-hidden />}>
            Sign as {identity.user}
          </Button>
        </div>
      </div>
    </form>
  );
}
