"use client";

import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { UserRound } from "lucide-react";
import { DEMO_IDENTITIES, setRole, useIdentity } from "@/lib/role";
import type { Role } from "@/lib/types";

/** Demo identity switch. Sends X-BV-User / X-BV-Role; there is no authentication. */
export function RoleSwitch() {
  const identity = useIdentity();
  const qc = useQueryClient();
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="bv-role" className="sr-only">
        Demo role
      </label>
      <div className="relative">
        <UserRound className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 text-ink-subtle" aria-hidden />
        <select
          id="bv-role"
          value={identity.role}
          onChange={(e) => {
            const role = e.target.value as Role;
            setRole(role);
            toast.message(`Demo role: ${DEMO_IDENTITIES[role].label} · ${DEMO_IDENTITIES[role].user}`);
            void qc.invalidateQueries();
          }}
          className="h-9 rounded-md border border-line bg-white pr-7 pl-8 text-sm font-medium text-ink"
        >
          {(Object.keys(DEMO_IDENTITIES) as Role[]).map((r) => (
            <option key={r} value={r}>
              {DEMO_IDENTITIES[r].label} · {DEMO_IDENTITIES[r].user}
            </option>
          ))}
        </select>
      </div>
      <span className="hidden text-sm leading-tight text-ink-subtle xl:block">
        Demo role,
        <br />
        no authentication
      </span>
    </div>
  );
}
