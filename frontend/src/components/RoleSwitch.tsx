"use client";

import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronsUpDown } from "lucide-react";
import { DEMO_IDENTITIES, setRole, useIdentity } from "@/lib/role";
import type { Role } from "@/lib/types";
import { Avatar, cn } from "./ui/primitives";

/**
 * Demo identity switch. Sends X-BV-User / X-BV-Role; there is no authentication.
 * A native <select> sits invisibly over the identity card, so it stays fully
 * keyboard and screen-reader accessible; the card shows its focus ring.
 * `compact` (phone top bar) shows the avatar and role only.
 * AppShell mounts exactly one RoleSwitch at a time (rail on desktop, compact top bar on phones), so the
 * "Demo role" label always names a single select (the e2e specs pick the role through it).
 */
export function RoleSwitch({ variant = "light", className }: { variant?: "light" | "dark" | "compact"; className?: string }) {
  const identity = useIdentity();
  const qc = useQueryClient();
  const dark = variant === "dark";
  const compact = variant === "compact";
  return (
    <div className={className}>
      <label
        htmlFor={`bv-role-${variant}`}
        className={cn(compact ? "sr-only" : "mb-1.5 block px-1 text-sm", dark ? "text-rail-muted" : "text-ink-subtle")}
      >
        Demo role · no authentication
      </label>
      <div className="relative" title={compact ? `Demo role: ${identity.label} (${identity.user}) · no authentication` : undefined}>
        <select
          id={`bv-role-${variant}`}
          value={identity.role}
          onChange={(e) => {
            const role = e.target.value as Role;
            setRole(role);
            toast.message(`Demo role: ${DEMO_IDENTITIES[role].label} · ${DEMO_IDENTITIES[role].user}`);
            void qc.invalidateQueries();
          }}
          className="peer absolute inset-0 z-10 size-full cursor-pointer appearance-none rounded-xl opacity-0"
        >
          {(Object.keys(DEMO_IDENTITIES) as Role[]).map((r) => (
            <option key={r} value={r}>
              {DEMO_IDENTITIES[r].label} · {DEMO_IDENTITIES[r].user}
            </option>
          ))}
        </select>
        <div
          aria-hidden
          className={cn(
            "pointer-events-none flex items-center rounded-xl border transition-colors",
            "peer-focus-visible:ring-2 peer-focus-visible:ring-offset-2",
            compact ? "h-9 gap-1.5 py-0 pr-2 pl-1" : "gap-2.5 px-2.5 py-2",
            dark
              ? "border-rail-line bg-rail-raised/70 text-rail-ink peer-hover:bg-rail-raised peer-focus-visible:ring-live peer-focus-visible:ring-offset-rail"
              : "border-line-strong bg-white text-ink shadow-card peer-hover:bg-gray-50 peer-focus-visible:ring-accent-600",
          )}
        >
          <Avatar name={identity.user.replace(/^Dr\.\s*/, "")} seed={identity.role} size="sm" className={compact ? "size-7" : undefined} />
          {compact ? (
            <span className="hidden text-sm font-medium sm:inline">{identity.label}</span>
          ) : (
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block truncate text-sm font-semibold">{identity.user}</span>
              <span className={cn("block truncate text-sm", dark ? "text-rail-muted" : "text-ink-subtle")}>{identity.label}</span>
            </span>
          )}
          <ChevronsUpDown className={cn("size-4 shrink-0", dark ? "text-rail-muted" : "text-ink-subtle")} />
        </div>
      </div>
    </div>
  );
}
