"use client";

import Link from "next/link";
import { Users, Ear } from "lucide-react";
import { usePatients } from "@/lib/queries";
import { formatDay, fullName } from "@/lib/format";
import { Card, EmptyState, ErrorState, LoadingRows, PageHeader, Table, Td, Th } from "@/components/ui/primitives";
import { CaregiverChip, Chip, LanguageChip, PaceChip, StatusChip } from "@/components/chips";

export default function PatientsPage() {
  const q = usePatients();
  const list = q.data ?? [];
  return (
    <>
      <PageHeader title="Patients" subtitle="Enrolled participants at this site. Synthetic data only." />
      <Card>
        {q.isPending ? (
          <LoadingRows rows={6} />
        ) : q.isError ? (
          <div className="p-4">
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
                <Th>Subject</Th>
                <Th>Name</Th>
                <Th>Age</Th>
                <Th>Language · pace</Th>
                <Th>Hearing</Th>
                <Th>Caregiver</Th>
                <Th>Next due</Th>
                <Th>Last check-in</Th>
                <Th>Open escalations</Th>
              </tr>
            </thead>
            <tbody>
              {list.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <Td className="font-mono font-medium">
                    <Link href={`/patients/${p.id}`} className="text-accent-800 hover:underline">
                      {p.subject_id}
                    </Link>
                  </Td>
                  <Td>
                    <Link href={`/patients/${p.id}`} className="font-medium hover:underline">
                      {fullName(p)}
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
                      <div className="flex flex-col items-start gap-0.5">
                        <CaregiverChip name={p.caregiver_name} relation={p.caregiver_relation} />
                        <span className="text-sm text-ink-subtle">{p.caregiver_may_answer ? "May answer for patient" : "May not answer"}</span>
                      </div>
                    ) : (
                      <span className="text-ink-subtle">—</span>
                    )}
                  </Td>
                  <Td className="tabular">{p.next_due ? `${formatDay(p.next_due.date)} · day ${p.next_due.day_after_dose}` : "—"}</Td>
                  <Td>{p.last_checkin_status ? <StatusChip status={p.last_checkin_status} /> : <span className="text-ink-subtle">None yet</span>}</Td>
                  <Td>{p.open_escalations > 0 ? <Chip tone="amber">{p.open_escalations} open</Chip> : <span className="text-ink-subtle">0</span>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
