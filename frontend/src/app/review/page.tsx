"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { toast } from "sonner";
import { Check, ClipboardCheck, FileWarning, Pencil, PenLine, X, XCircle } from "lucide-react";
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
  Button,
  ButtonLink,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Label,
  LoadingRows,
  PageHeader,
  inputClass,
  cn,
} from "@/components/ui/primitives";
import { Chip, DraftStatusChip } from "@/components/chips";
import { GradeBadge } from "@/components/GradeBadge";
import { EvidenceQuote } from "@/components/EvidenceQuote";
import { AiLabel } from "@/components/AiLabel";
import { RelativeTime } from "@/components/RelativeTime";

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

const STATUSES = [
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
  const patients = usePatients();

  const setFilter = (key: keyof DraftFilters, value: string) => {
    const next = new URLSearchParams(sp.toString());
    if (key === "status") next.set("status", value);
    else if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  const list = drafts.data ?? [];

  return (
    <>
      <PageHeader
        title="Review queue"
        subtitle="Every entry is a draft until someone on the study team confirms it. Evidence shows the patient's own words."
      />

      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-line bg-white p-3">
        <div>
          <Label htmlFor="f-status">Status</Label>
          <select id="f-status" className={cn(inputClass, "w-44")} value={filters.status} onChange={(e) => setFilter("status", e.target.value)}>
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="f-kind">Kind</Label>
          <select id="f-kind" className={cn(inputClass, "w-48")} value={filters.kind} onChange={(e) => setFilter("kind", e.target.value)}>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="f-patient">Patient</Label>
          <select id="f-patient" className={cn(inputClass, "w-56")} value={filters.patient_id} onChange={(e) => setFilter("patient_id", e.target.value)}>
            <option value="">All patients</option>
            {(patients.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.subject_id} · {fullName(p)}
              </option>
            ))}
          </select>
        </div>
        {filters.checkin_id ? (
          <div className="flex items-center gap-2 self-center pt-5">
            <Chip tone="accent">
              Check-in {filters.checkin_id}
              <button type="button" onClick={() => setFilter("checkin_id", "")} className="ml-1 rounded hover:bg-accent-100" aria-label="Clear check-in filter">
                <X className="size-3.5" aria-hidden />
              </button>
            </Chip>
          </div>
        ) : null}
        <div className="ml-auto self-center pt-5 text-sm text-ink-subtle tabular">
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
        <div className="space-y-4">
          {list.map((d) => (
            <DraftCard key={d.id} draft={d} />
          ))}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- draft card

function draftTitle(d: DraftEntry): string {
  if (d.kind === "AE") return d.payload.term;
  if (d.kind === "CM") return d.payload.medication_name;
  return NURSE_TASK_LABELS[d.payload.category] ?? humanize(d.payload.category);
}

const KIND_LABEL = { AE: "Adverse event", CM: "Medication", NURSE_TASK: "Nurse task" } as const;

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

  return (
    <Card as="article" className={cn(d.status === "rejected" && "opacity-75")}>
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        <Chip tone={d.kind === "NURSE_TASK" ? "blue" : "gray"}>{KIND_LABEL[d.kind]}</Chip>
        <h2 className="text-lg font-semibold text-ink">{draftTitle(d)}</h2>
        {d.kind === "AE" ? <GradeBadge grade={d.payload.provisional_grade} /> : null}
        <DraftStatusChip status={d.status} />
        <div className="ml-auto flex flex-wrap items-center gap-x-3 text-sm text-ink-subtle">
          {d.patient ? (
            <Link href={`/patients/${d.patient.id}`} className="hover:underline">
              <span className="font-medium text-ink">{fullName(d.patient)}</span> <span className="font-mono">{d.patient.subject_id}</span>
            </Link>
          ) : null}
          <Link href={`/checkins/${d.checkin_id}`} className="text-accent-700 hover:underline">
            Check-in
          </Link>
          {d.created_at ? <RelativeTime iso={d.created_at} /> : null}
        </div>
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="min-w-0 space-y-3">
          {mode === "edit" ? (
            <EditForm draft={d} onDone={() => setMode("view")} />
          ) : (
            <PayloadView draft={d} nonEnglish={nonEnglish} />
          )}
          {d.status !== "draft" && d.reviewed_by ? (
            <p className="text-sm text-ink-muted">
              {d.status === "confirmed" ? "Confirmed" : "Rejected"} by <strong>{d.reviewed_by}</strong>{" "}
              {d.reviewed_at ? <RelativeTime iso={d.reviewed_at} /> : null}
              {d.review_note ? <> · “{d.review_note}”</> : null}
            </p>
          ) : null}
        </div>
        <div className="min-w-0 space-y-2">
          <h3 className="text-sm font-medium text-ink-subtle">
            Evidence ({d.evidence.length})
          </h3>
          {d.evidence.length === 0 ? (
            <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">No evidence attached. Don&apos;t confirm without checking the call.</p>
          ) : (
            d.evidence.map((ev, i) => <EvidenceQuote key={i} evidence={ev} checkinId={d.checkin_id} />)
          )}
        </div>
      </div>

      {d.status === "draft" && mode !== "edit" ? (
        <div className="border-t border-line bg-gray-50/70 px-4 py-3">
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
            <div className="flex flex-wrap gap-2">
              <Button variant="success" loading={confirm.isPending} disabled={busy} onClick={() => confirm.mutate()} icon={<Check className="size-4" aria-hidden />}>
                Confirm
              </Button>
              <Button disabled={busy} onClick={() => setMode("edit")} icon={<Pencil className="size-4" aria-hidden />}>
                Edit
              </Button>
              <Button variant="ghost" disabled={busy} onClick={() => setMode("reject")} icon={<X className="size-4" aria-hidden />}>
                Reject
              </Button>
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
          <div className="mb-1 flex items-center gap-2 text-sm text-ink-subtle">
            Verbatim (English){nonEnglish ? <AiLabel>AI translation, verify</AiLabel> : null}
          </div>
          <p className="text-[15px] text-ink">{p.verbatim_en}</p>
        </div>
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Onset">{formatDay(p.onset_date)}</Field>
          <Field label="Ongoing">{p.ongoing ? "Yes" : "No"}</Field>
        </dl>
        <div className="rounded-md bg-gray-50 p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <GradeBadge grade={p.provisional_grade} />
            {p.rule_id ? <span className="font-mono text-ink-muted">{p.rule_id}</span> : null}
          </div>
          <p className="mt-1.5 text-ink-muted">
            {p.grade_basis === "rule" && p.rule_text ? <>CTCAE v5.0: {p.rule_text}</> : "No phone-gradable CTCAE rule. A clinician assigns the grade."}
          </p>
          {p.answers.length ? (
            <p className="mt-1.5 text-ink-subtle">
              Answers: {p.answers.map((a) => `${humanize(a.item_code)} = ${a.numeric_value ?? humanize(a.option_code ?? "")}`).join(" · ")}
            </p>
          ) : null}
        </div>
      </>
    );
  }
  if (d.kind === "CM") {
    const p = d.payload;
    return (
      <dl className="grid grid-cols-2 gap-3">
        <Field label="Medication">{p.medication_name}</Field>
        {p.as_reported_en ? (
          <Field label={<span className="inline-flex items-center gap-1.5">As reported <AiLabel>AI extraction, verify</AiLabel></span>}>{p.as_reported_en}</Field>
        ) : null}
        <Field label="Over the counter">{p.otc ? "Yes" : "No"}</Field>
        <Field label={<span className="inline-flex items-center gap-1.5">Indication {nonEnglish ? <AiLabel>AI translation, verify</AiLabel> : null}</span>}>{p.indication_en ?? "—"}</Field>
        <Field label="Start date">{formatDay(p.start_date)}</Field>
        <Field label="Dose">{p.dose_text ?? "Not reported"}</Field>
      </dl>
    );
  }
  const p = d.payload;
  return (
    <div className="space-y-2">
      <Field label="Category">{NURSE_TASK_LABELS[p.category] ?? humanize(p.category)}</Field>
      <div>
        <div className="mb-1 flex items-center gap-2 text-sm text-ink-subtle">
          What the patient asked or said{nonEnglish ? <AiLabel>AI translation, verify</AiLabel> : null}
        </div>
        <p className="text-[15px] text-ink">{p.text_en}</p>
        {p.detail ? <p className="mt-1 text-sm text-ink-muted">{p.detail}</p> : null}
      </div>
      {p.category === "medical_question" ? (
        <p className="text-sm text-ink-subtle">The agent gave no advice and told the patient the nurse will follow up.</p>
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
      className="space-y-3 rounded-md border border-accent-200 bg-accent-50/30 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
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
                className={inputClass}
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
            <input type="checkbox" className="size-4" checked={!!ae.ongoing} onChange={(e) => setAe({ ...ae, ongoing: e.target.checked })} />
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
            <input type="checkbox" className="size-4" checked={!!cm.otc} onChange={(e) => setCm({ ...cm, otc: e.target.checked })} />
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
      <div className="border-t border-line bg-white px-4 py-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <PenLine className="size-4 text-ink-subtle" aria-hidden />
          <span>
            Investigator assessment signed by <strong>{inv.signed_by}</strong> {inv.signed_at ? <RelativeTime iso={inv.signed_at} /> : null}
          </span>
          {inv.is_serious ? <Chip tone="red">Serious</Chip> : <Chip tone="gray">Not serious</Chip>}
          {inv.seriousness_criteria.map((c) => (
            <Chip key={c} tone="gray">
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
      <div className="border-t border-line bg-gray-50/70 px-4 py-3 text-sm text-ink-muted">
        Waiting for the investigator&apos;s seriousness and relatedness assessment. (Switch the demo role to <strong>Investigator</strong> to sign.)
      </div>
    );
  }

  const serious = criteria.length > 0;
  return (
    <form
      className="border-t-2 border-accent-200 bg-accent-50/30 px-4 py-4"
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
      <div className="mt-3 grid gap-4 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium text-ink-muted">Seriousness (ICH E2A): check all that apply</legend>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {SERIOUSNESS_ORDER.map((c) => (
              <label key={c} className="flex min-h-9 items-center gap-2 rounded-md border border-line bg-white px-2.5 py-1.5 text-sm has-[:checked]:border-red-300 has-[:checked]:bg-red-50">
                <input
                  type="checkbox"
                  className="size-4"
                  checked={criteria.includes(c)}
                  onChange={(e) => setCriteria(e.target.checked ? [...criteria, c] : criteria.filter((x) => x !== c))}
                />
                {SERIOUSNESS_LABELS[c]}
              </label>
            ))}
          </div>
          <p className="mt-2 text-sm text-ink-muted">
            {serious ? (
              <strong className="text-red-800">Serious: a sponsor report will be drafted and the 24-hour clock starts.</strong>
            ) : (
              "No criteria checked: not serious."
            )}
          </p>
        </fieldset>
        <div className="space-y-3">
          <div>
            <Label htmlFor={`rel-${d.id}`}>Relatedness to study drug</Label>
            <select id={`rel-${d.id}`} className={inputClass} value={relatedness} onChange={(e) => setRelatedness(e.target.value as Relatedness | "")} required>
              <option value="">Select…</option>
              {RELATEDNESS_ORDER.map((r) => (
                <option key={r} value={r}>
                  {RELATEDNESS_LABELS[r]}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" variant="primary" size="lg" className="w-full" loading={sign.isPending} disabled={!relatedness} icon={<PenLine className="size-4" aria-hidden />}>
            Sign as {identity.user}
          </Button>
        </div>
      </div>
    </form>
  );
}
