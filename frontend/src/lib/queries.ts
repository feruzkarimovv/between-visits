"use client";

import { useQuery, useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch, errorMessage, isApiError, type ApiInit } from "./api";
import { humanize } from "./format";
import type {
  AuditEvent,
  DemoScenario,
  DraftEntry,
  Escalation,
  EscalationLevel,
  EvalLatest,
  Health,
  PatientDetail,
  PatientSummary,
  Plan,
  AnswerKeyResponse,
  SAEReport,
  SiteSignalValidation,
  SitesResponse,
  SponsorInboxItem,
  Study,
  TodayRow,
  ValidationSummary,
  VoiceChecks,
} from "./types";

/** Don't retry 4xx; retry network/5xx once. */
function retry(failureCount: number, error: unknown): boolean {
  if (isApiError(error) && error.status >= 400 && error.status < 500) return false;
  return failureCount < 1;
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<Health>("/api/health"),
    staleTime: 60_000,
    retry,
  });
}

export function useStudy() {
  return useQuery({
    queryKey: ["study"],
    queryFn: () => apiFetch<Study>("/api/study"),
    staleTime: Infinity,
    retry,
  });
}

export function usePlan() {
  return useQuery({
    queryKey: ["plan"],
    queryFn: () => apiFetch<Plan>("/api/plan/active"),
    staleTime: 5 * 60_000,
    retry,
  });
}

export function useRedFlagLabel(id: string): { short: string; full: string; level: EscalationLevel } {
  const { data } = usePlan();
  const rf = data?.red_flags.find((r) => r.id === id);
  return {
    short: humanize(id),
    full: rf?.label_en ?? humanize(id),
    level: rf?.level ?? "urgent",
  };
}

export function usePatients() {
  return useQuery({
    queryKey: ["patients"],
    queryFn: () => apiFetch<PatientSummary[]>("/api/patients"),
    retry,
  });
}

/** Accepts either the flat shape (patient fields + checkins/timeline/dose_dates) or `{patient: {...}, ...}`. */
function normalizePatientDetail(raw: unknown): PatientDetail {
  const r = raw as Partial<PatientDetail> & { patient?: Partial<PatientDetail> };
  const base = r.patient ? { ...r.patient, ...r } : r;
  return {
    ...(base as PatientDetail),
    checkins: r.checkins ?? [],
    timeline: r.timeline ?? [],
    dose_dates: r.dose_dates ?? [],
  };
}

export function usePatient(id: string) {
  return useQuery({
    queryKey: ["patient", id],
    queryFn: async () => normalizePatientDetail(await apiFetch<unknown>(`/api/patients/${encodeURIComponent(id)}`)),
    retry,
  });
}

export function useTodayCheckins(date: string) {
  return useQuery({
    queryKey: ["checkins", date],
    queryFn: () => apiFetch<TodayRow[]>(`/api/checkins?date=${encodeURIComponent(date)}`),
    refetchInterval: 5000,
    retry,
  });
}

export function useEscalations(status?: "open" | "acknowledged" | "resolved", refetchInterval?: number) {
  return useQuery({
    queryKey: ["escalations", status ?? "all"],
    queryFn: () => apiFetch<Escalation[]>(status ? `/api/escalations?status=${status}` : "/api/escalations"),
    refetchInterval,
    retry,
  });
}

export interface DraftFilters {
  status?: string;
  kind?: string;
  patient_id?: string;
  checkin_id?: string;
}

export function useDrafts(filters: DraftFilters) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) if (v) qs.set(k, v);
  return useQuery({
    queryKey: ["drafts", filters],
    queryFn: async () => {
      const list = await apiFetch<DraftEntry[]>(`/api/drafts${qs.size ? `?${qs}` : ""}`);
      // Filter client-side too, in case the backend ignores a filter it doesn't know.
      return list.filter(
        (d) =>
          (!filters.status || d.status === filters.status) &&
          (!filters.kind || d.kind === filters.kind) &&
          (!filters.patient_id || d.patient_id === filters.patient_id) &&
          (!filters.checkin_id || d.checkin_id === filters.checkin_id),
      );
    },
    retry,
  });
}

export function useSae(id: string) {
  return useQuery({
    queryKey: ["sae", id],
    queryFn: () => apiFetch<SAEReport>(`/api/sae/${encodeURIComponent(id)}`),
    retry,
  });
}

export function useSaeList() {
  return useQuery({
    queryKey: ["sae-list"],
    queryFn: () => apiFetch<SAEReport[]>("/api/sae"),
    refetchInterval: 10_000,
    retry,
  });
}

export function useSponsorInbox() {
  return useQuery({
    queryKey: ["sponsor-inbox"],
    queryFn: () => apiFetch<SponsorInboxItem[]>("/api/sponsor/inbox"),
    refetchInterval: 10_000,
    retry,
  });
}

export function useAudit(entityId?: string) {
  return useQuery({
    queryKey: ["audit", entityId ?? "all"],
    queryFn: () =>
      apiFetch<AuditEvent[]>(`/api/audit?limit=200${entityId ? `&entity_id=${encodeURIComponent(entityId)}` : ""}`),
    retry,
  });
}

export function useEval() {
  return useQuery({
    queryKey: ["eval"],
    queryFn: () => apiFetch<EvalLatest>("/api/eval/latest"),
    retry,
  });
}

/** Real browser calls (MEASURED, docs/03 §6.11); 404 `no_voice_checks` until V10 logs calls (not retried). */
export function useVoiceChecks() {
  return useQuery({
    queryKey: ["eval-voice-checks"],
    queryFn: () => apiFetch<VoiceChecks>("/api/eval/voice-checks"),
    retry,
  });
}

export function useValidation() {
  return useQuery({
    queryKey: ["validation"],
    queryFn: () => apiFetch<ValidationSummary>("/api/validation/latest"),
    retry,
  });
}

/**
 * Site Signal committed study (`GET /api/sites`, cra and sponsor). `enabled` is false for other roles, which
 * see the role notice instead; a 403 `wrong_role` or 503 `site_signal_unavailable` is not retried.
 */
export function useSites(enabled = true) {
  return useQuery({
    queryKey: ["sites"],
    queryFn: () => apiFetch<SitesResponse>("/api/sites"),
    enabled,
    staleTime: 60_000,
    retry,
  });
}

/** Site Signal operating characteristics (`GET /api/site-signal/validation`, any role); 404 `no_validation_run`. */
export function useSiteValidation(enabled = true) {
  return useQuery({
    queryKey: ["site-signal-validation"],
    queryFn: () => apiFetch<SiteSignalValidation>("/api/site-signal/validation"),
    enabled,
    staleTime: 5 * 60_000,
    retry,
  });
}

/** Committed study's answer key (`GET /api/site-signal/answer-key`, cra and sponsor); fetched only after "Reveal". */
export function useAnswerKey(enabled: boolean) {
  return useQuery({
    queryKey: ["site-signal-answer-key"],
    queryFn: () => apiFetch<AnswerKeyResponse>("/api/site-signal/answer-key"),
    enabled,
    staleTime: 5 * 60_000,
    retry,
  });
}

/** Demo replay scenarios; only fetched when `GET /api/health` says `demo_mode: true` (otherwise 404 `demo_disabled`). */
export function useScenarios(enabled: boolean) {
  return useQuery({
    queryKey: ["demo-scenarios"],
    queryFn: () => apiFetch<DemoScenario[]>("/api/demo/scenarios"),
    enabled,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

/**
 * Mutation helper: calls the API, toasts success/failure, invalidates keys.
 * Buttons read `isPending` to disable themselves.
 */
export function useApiMutation<TVars, TResult>(opts: {
  request: (vars: TVars) => { path: string; init: ApiInit };
  success?: string | ((result: TResult, vars: TVars) => string | null);
  invalidate?: QueryKey[];
  onSuccess?: (result: TResult, vars: TVars) => void;
}) {
  const qc = useQueryClient();
  return useMutation<TResult, unknown, TVars>({
    mutationFn: (vars) => {
      const { path, init } = opts.request(vars);
      return apiFetch<TResult>(path, init);
    },
    onSuccess: (result, vars) => {
      const msg = typeof opts.success === "function" ? opts.success(result, vars) : opts.success;
      if (msg) toast.success(msg);
      opts.onSuccess?.(result, vars);
      for (const key of opts.invalidate ?? []) void qc.invalidateQueries({ queryKey: key });
    },
    onError: (e) => {
      toast.error(errorMessage(e));
    },
  });
}
