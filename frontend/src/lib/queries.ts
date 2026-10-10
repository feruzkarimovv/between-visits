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
  SAEReport,
  SponsorInboxItem,
  Study,
  TodayRow,
  ValidationSummary,
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

export function useValidation() {
  return useQuery({
    queryKey: ["validation"],
    queryFn: () => apiFetch<ValidationSummary>("/api/validation/latest"),
    retry,
  });
}

export function useScenarios() {
  return useQuery({
    queryKey: ["demo-scenarios"],
    queryFn: () => apiFetch<DemoScenario[]>("/api/demo/scenarios"),
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
