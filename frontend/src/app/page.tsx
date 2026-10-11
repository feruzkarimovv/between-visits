"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { CalendarCheck, Globe, Phone, PlayCircle, Users, ChevronRight } from "lucide-react";
import type { CreateCheckInResponse, ReplayResponse, TodayRow } from "@/lib/types";
import { useApiMutation, useHealth, useScenarios, useTodayCheckins } from "@/lib/queries";
import { formatDate, fullName, todayInTz } from "@/lib/format";
import { saveWebSession } from "@/lib/webSession";
import { useNow } from "@/lib/hooks";
import { Button, Card, CardHeader, EmptyState, ErrorState, LoadingRows, PageHeader, Table, Td, Th } from "@/components/ui/primitives";
import { LanguageChip, PaceChip, StatusChip } from "@/components/chips";
import { RelativeTime } from "@/components/RelativeTime";

const LIVE = new Set(["dialing", "in_progress"]);

interface CallVars {
  patientId: string;
  firstName: string;
  channel: "phone" | "web";
  dayAfterDose: number;
}

export default function TodayPage() {
  const router = useRouter();
  const now = useNow();
  const date = todayInTz(now || undefined);
  const today = useTodayCheckins(date);
  const health = useHealth();
  const scenarios = useScenarios();
  const demoMode = health.data?.demo_mode === true;
  const [scenarioId, setScenarioId] = useState<string>("");

  const call = useApiMutation<CallVars, CreateCheckInResponse>({
    request: (v) => ({
      path: `/api/patients/${encodeURIComponent(v.patientId)}/checkins`,
      init: { method: "POST", body: { channel: v.channel, day_after_dose: v.dayAfterDose } },
    }),
    success: (_r, v) => (v.channel === "web" ? `Browser call ready for ${v.firstName}` : `Calling ${v.firstName}…`),
    invalidate: [["checkins"], ["patients"]],
    onSuccess: (r) => {
      if (r.web_session) saveWebSession(r.checkin.id, r.web_session);
      router.push(`/checkins/${r.checkin.id}`);
    },
  });

  const replay = useApiMutation<string, ReplayResponse>({
    request: (id) => ({ path: `/api/demo/replay/${encodeURIComponent(id)}`, init: { method: "POST" } }),
    success: "Replay started",
    invalidate: [["checkins"]],
    onSuccess: (r) => router.push(`/checkins/${r.checkin_id}`),
  });

  const scenarioList = scenarios.data ?? [];
  const selectedScenario = scenarioId || scenarioList[0]?.id || "";
  const rows = today.data ?? [];
  const live = rows.filter((r) => LIVE.has(r.status)).length;
  const done = rows.filter((r) => r.status === "completed").length;
  const due = rows.filter((r) => r.status === "due").length;

  return (
    <>
      <PageHeader
        title="Today"
        subtitle={
          <span className="tabular">
            {now ? formatDate(new Date(now).toISOString()) : " "} · check-ins 1, 3 and 7 days after each dose
          </span>
        }
        actions={
          demoMode && scenarioList.length > 0 ? (
            <div className="flex items-center gap-2 rounded-lg border border-line bg-white p-1.5 pl-3">
              <label htmlFor="scenario" className="text-sm font-medium text-ink-muted">
                {demoMode ? "Demo mode" : "Replay"}
              </label>
              <select
                id="scenario"
                value={selectedScenario}
                onChange={(e) => setScenarioId(e.target.value)}
                className="h-8 max-w-64 rounded-md border border-line bg-white px-2 text-sm"
              >
                {scenarioList.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title} ({Math.round(s.duration_s / 60)} min)
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant="primary"
                icon={<PlayCircle className="size-4" aria-hidden />}
                loading={replay.isPending}
                disabled={!selectedScenario}
                onClick={() => replay.mutate(selectedScenario)}
              >
                Replay scenario
              </Button>
            </div>
          ) : null
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Due, not yet called" value={today.data ? due : null} />
        <Stat label="Live now" value={today.data ? live : null} tone={live ? "accent" : undefined} />
        <Stat label="Completed" value={today.data ? done : null} />
        <Stat label="Scheduled today" value={today.data ? rows.length : null} />
      </div>

      <Card>
        <CardHeader
          title="Check-ins due today"
          icon={<CalendarCheck className="size-4 text-ink-subtle" aria-hidden />}
          subtitle={
            demoMode
              ? "Demo mode: outbound phone calls are off. Use a browser call or replay a recorded scenario."
              : health.data?.phone_calls_enabled
                ? "Call by phone, or run the same check-in in the browser."
                : "Check-ins run in the browser with the same voice agent. Phone calling is off until a phone number is connected."
          }
        />
        {today.isPending ? (
          <LoadingRows rows={5} />
        ) : today.isError ? (
          <div className="p-4">
            <ErrorState error={today.error} onRetry={() => void today.refetch()} retrying={today.isFetching} />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState icon={<CalendarCheck className="size-6" aria-hidden />} title="No check-ins due today.">
            Patients appear here 1, 3 and 7 days after a dose.
          </EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Subject</Th>
                <Th>Name</Th>
                <Th>Day after dose</Th>
                <Th>Language · pace</Th>
                <Th>Caregiver</Th>
                <Th>Status</Th>
                <Th className="text-right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <TodayTableRow
                  key={row.id ?? row.patient.id}
                  row={row}
                  demoMode={demoMode}
                  phoneNote={health.data?.phone_calls_note ?? null}
                  webNote={health.data?.browser_calls_note ?? null}
                  pendingChannel={call.isPending && call.variables?.patientId === row.patient.id ? call.variables.channel : null}
                  anyPending={call.isPending}
                  onCall={(channel) =>
                    call.mutate({
                      patientId: row.patient.id,
                      firstName: row.patient.first_name ?? row.patient.subject_id,
                      channel,
                      dayAfterDose: row.day_after_dose ?? row.patient.next_due?.day_after_dose ?? 1,
                    })
                  }
                  onOpen={() => row.id && router.push(`/checkins/${row.id}`)}
                />
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}

function Stat({ label, value, tone }: { label: string; value: number | null; tone?: "accent" }) {
  return (
    <div className={`rounded-lg border bg-white px-4 py-3 ${tone === "accent" ? "border-accent-200" : "border-line"}`}>
      <div className="text-sm text-ink-subtle">{label}</div>
      <div className={`mt-0.5 text-2xl font-semibold tabular ${tone === "accent" ? "text-accent-800" : "text-ink"}`}>{value ?? "—"}</div>
    </div>
  );
}

function TodayTableRow({
  row,
  demoMode,
  phoneNote,
  webNote,
  pendingChannel,
  anyPending,
  onCall,
  onOpen,
}: {
  row: TodayRow;
  demoMode: boolean;
  phoneNote: string | null;
  webNote: string | null;
  pendingChannel: "phone" | "web" | null;
  anyPending: boolean;
  onCall: (channel: "phone" | "web") => void;
  onOpen: () => void;
}) {
  const isLive = LIVE.has(row.status);
  const clickable = !!row.id;
  return (
    <tr
      className={clickable ? "cursor-pointer hover:bg-gray-50" : undefined}
      onClick={(e) => {
        if (!clickable) return;
        if ((e.target as HTMLElement).closest("button, a, select")) return;
        onOpen();
      }}
    >
      <Td className="font-mono font-medium">
        {row.id ? (
          <Link href={`/checkins/${row.id}`} className="text-accent-800 hover:underline">
            {row.patient.subject_id}
          </Link>
        ) : (
          row.patient.subject_id
        )}
      </Td>
      <Td>
        <Link href={`/patients/${row.patient.id}`} className="font-medium text-ink hover:underline">
          {fullName(row.patient) || "—"}
        </Link>
      </Td>
      <Td className="tabular">{row.day_after_dose ? `Day ${row.day_after_dose}` : "—"}</Td>
      <Td>
        <div className="flex flex-wrap gap-1.5">
          <LanguageChip lang={row.patient.language} />
          <PaceChip pace={row.patient.pace} />
        </div>
      </Td>
      <Td>
        {row.patient.caregiver_name ? (
          <span className="inline-flex items-center gap-1.5 text-ink-muted" title={`Caregiver: ${row.patient.caregiver_name}`}>
            <Users className="size-4" aria-hidden />
            {row.patient.caregiver_name}
          </span>
        ) : (
          <span className="text-ink-subtle">—</span>
        )}
      </Td>
      <Td>
        <div className="flex flex-col items-start gap-0.5">
          <StatusChip status={row.status} />
          {row.started_at && !isLive ? (
            <span className="text-sm text-ink-subtle">
              <RelativeTime iso={row.started_at} />
            </span>
          ) : null}
        </div>
      </Td>
      <Td>
        <div className="flex items-center justify-end gap-2">
          {isLive && row.id ? (
            <Button size="sm" variant="primary" onClick={onOpen} icon={<ChevronRight className="size-4" aria-hidden />}>
              Open live call
            </Button>
          ) : (
            <>
              {!demoMode && !phoneNote ? (
                <span title={phoneNote ?? undefined}>
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Phone className="size-4" aria-hidden />}
                    loading={pendingChannel === "phone"}
                    disabled={anyPending || !!phoneNote}
                    onClick={() => onCall("phone")}
                  >
                    Call phone
                  </Button>
                </span>
              ) : null}
              <span title={webNote ?? undefined}>
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Globe className="size-4" aria-hidden />}
                  loading={pendingChannel === "web"}
                  disabled={anyPending || (!demoMode && !!webNote)}
                  onClick={() => onCall("web")}
                >
                  Call in browser
                </Button>
              </span>
            </>
          )}
        </div>
      </Td>
    </tr>
  );
}
