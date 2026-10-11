"use client";

import Link from "next/link";
import { Users, Ear, ChevronRight } from "lucide-react";
import { usePatients } from "@/lib/queries";
import { formatDay, fullName } from "@/lib/format";
import { Avatar, Card, EmptyState, ErrorState, LoadingRows, PageHeader, Table, Td, Th } from "@/components/ui/primitives";
import { CaregiverChip, Chip, LanguageChip, PaceChip, StatusChip } from "@/components/chips";

export default function PatientsPage() {
  const q = usePatients();
  const list = q.data ?? [];
  const spanish = list.filter((p) => p.language === "es").length;
  const extra = list.filter((p) => p.pace === "extra_time").length;
  const caregivers = list.filter((p) => p.caregiver_name).length;

  return (
    <>
      <PageHeader
        eyebrow="Site cohort"
        title="Patients"
        subtitle="Enrolled participants at this site. Synthetic data only."
        actions={
          q.data ? (
            <dl className="flex gap-2">
              <Stat label="Enrolled" value={list.length} />
              <Stat label="Spanish" value={spanish} />
              <Stat label="Extra time" value={extra} />
              <Stat label="Caregiver" value={caregivers} />
            </dl>
          ) : null
        }
      />
      <Card className="overflow-hidden">
        {q.isPending ? (
          <LoadingRows rows={6} />
        ) : q.isError ? (
          <div className="p-5">
            <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />
          </div>
        ) : list.length === 0 ? (
          <EmptyState icon={<Users className="size-6" aria-hidden />} title="No patients enrolled yet.">
            Run <code className="font-mono">make seed</code> to load the synthetic study cohort.
          </EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Patient</Th>
                <Th>Age</Th>
                <Th>Language · pace</Th>
                <Th>Hearing</Th>
                <Th>Caregiver</Th>
                <Th>Next due</Th>
                <Th>Last check-in</Th>
                <Th>Open escalations</Th>
                <Th>
                  <span className="sr-only">Open</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {list.map((p) => {
                const name = fullName(p) || p.subject_id;
                return (
                  <tr key={p.id} className="group transition-colors hover:bg-accent-50/40">
                    <Td>
                      <Link href={`/patients/${p.id}`} className="flex items-center gap-3">
                        <Avatar name={name} seed={p.id} />
                        <span className="leading-tight">
                          <span className="block text-[15px] font-semibold whitespace-nowrap text-ink group-hover:underline">{name}</span>
                          <span className="font-mono text-sm text-ink-subtle">{p.subject_id}</span>
                        </span>
                      </Link>
                    </Td>
                    <Td className="tabular">{p.age}</Td>
                    <Td>
                      <div className="flex flex-wrap gap-1.5">
                        <LanguageChip lang={p.language} />
                        <PaceChip pace={p.pace} />
                      </div>
                    </Td>
                    <Td>
                      {p.hearing === "hard_of_hearing" ? (
                        <Chip icon={<Ear className="size-3.5" aria-hidden />}>Hard of hearing</Chip>
                      ) : (
                        <span className="text-ink-subtle">Typical</span>
                      )}
                    </Td>
                    <Td>
                      {p.caregiver_name ? (
                        <div className="flex flex-col items-start gap-1">
                          <CaregiverChip name={p.caregiver_name} relation={p.caregiver_relation} />
                          <span className="text-sm text-ink-subtle">{p.caregiver_may_answer ? "May answer for patient" : "May not answer"}</span>
                        </div>
                      ) : (
                        <span className="text-ink-subtle">—</span>
                      )}
                    </Td>
                    <Td className="whitespace-nowrap tabular">
                      {p.next_due ? (
                        <span className="leading-tight">
                          <span className="block font-medium text-ink">{formatDay(p.next_due.date)}</span>
                          <span className="text-sm text-ink-subtle">Day {p.next_due.day_after_dose}</span>
                        </span>
                      ) : (
                        "—"
                      )}
                    </Td>
                    <Td>{p.last_checkin_status ? <StatusChip status={p.last_checkin_status} /> : <span className="text-ink-subtle">None yet</span>}</Td>
                    <Td>{p.open_escalations > 0 ? <Chip tone="amber">{p.open_escalations} open</Chip> : <span className="text-ink-subtle">0</span>}</Td>
                    <Td className="w-10">
                      <ChevronRight className="size-4 text-ink-subtle transition-transform group-hover:translate-x-0.5" aria-hidden />
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="min-w-20 rounded-xl border border-line bg-white px-3 py-2 shadow-card">
      <dt className="text-sm text-ink-subtle">{label}</dt>
      <dd className="text-2xl leading-tight font-semibold tracking-tight text-ink tabular">{value}</dd>
    </div>
  );
}
