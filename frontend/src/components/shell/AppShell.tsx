"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CalendarCheck,
  BellRing,
  ClipboardCheck,
  FileWarning,
  Users,
  ListChecks,
  Gauge,
  Inbox,
  ScrollText,
  Activity,
  FlaskConical,
  Building2,
  Mailbox,
} from "lucide-react";
import { useStudy } from "@/lib/queries";
import { USE_FIXTURES } from "@/lib/api";
import { EscalationBanner } from "../EscalationBanner";
import { RoleSwitch } from "../RoleSwitch";
import { cn } from "../ui/primitives";

const NAV = [
  { href: "/", label: "Today", icon: CalendarCheck },
  { href: "/escalations", label: "Escalations", icon: BellRing },
  { href: "/review", label: "Review", icon: ClipboardCheck },
  { href: "/sae", label: "Serious events", icon: FileWarning },
  { href: "/patients", label: "Patients", icon: Users },
  { href: "/plan", label: "Plan", icon: ListChecks },
  { href: "/report-card", label: "Report card", icon: Gauge },
  { href: "/sponsor", label: "Sponsor inbox", icon: Inbox },
  { href: "/sites", label: "Sites", icon: Building2 },
  { href: "/site-inbox", label: "Site inbox", icon: Mailbox },
  { href: "/audit", label: "Audit", icon: ScrollText },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/checkins");
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const study = useStudy();
  const sponsor = pathname.startsWith("/sponsor");

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur">
        <div className="flex min-h-14 flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2">
          <Link href="/" className="flex shrink-0 items-center gap-2 font-semibold text-ink">
            <span className="flex size-7 items-center justify-center rounded-md bg-accent-700 text-white">
              <Activity className="size-4" aria-hidden />
            </span>
            <span className="text-base whitespace-nowrap">Between Visits</span>
          </Link>
          <div className="hidden min-w-0 flex-1 border-l border-line pl-4 text-sm lg:block">
            {study.data ? (
              <div className="min-w-0 leading-tight">
                <div className="truncate font-medium text-ink" title={study.data.title_short}>
                  {study.data.title_short}
                </div>
                <div className="truncate text-ink-subtle">
                  {study.data.nct_id} · Site {study.data.site_id}, {study.data.site_name}
                </div>
              </div>
            ) : (
              <span className="text-ink-subtle">{study.isError ? "Study unavailable" : "Loading study…"}</span>
            )}
          </div>
          <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2 sm:gap-3">
            {USE_FIXTURES ? (
              <span className="hidden items-center gap-1 rounded-full border border-dashed border-gray-400 px-2 py-0.5 text-sm text-ink-muted md:inline-flex" title="NEXT_PUBLIC_USE_FIXTURES=1: data comes from src/fixtures, not the backend">
                <FlaskConical className="size-3.5" aria-hidden />
                Fixture data
              </span>
            ) : null}
            <EscalationBanner />
            <RoleSwitch />
          </div>
        </div>
      </header>
      <div className="flex flex-1">
        <nav aria-label="Main" className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-52 overflow-y-auto shrink-0 border-r border-line bg-white px-2 py-3 md:block">
          <ul className="space-y-0.5">
            {NAV.map(({ href, label, icon: Icon }) => {
              const active = isActive(pathname, href);
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium",
                      active ? "bg-accent-50 text-accent-800" : "text-ink-muted hover:bg-gray-100 hover:text-ink",
                    )}
                  >
                    <Icon className="size-4" aria-hidden />
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
          <p className="mt-6 px-3 text-sm leading-snug text-ink-subtle">
            Synthetic data only. Not a medical device. Grades are provisional; clinicians decide.
          </p>
        </nav>
        <nav aria-label="Main (mobile)" className="fixed inset-x-0 bottom-0 z-30 flex overflow-x-auto border-t border-line bg-white md:hidden">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn("flex min-w-20 flex-col items-center gap-0.5 px-2 py-2 text-sm whitespace-nowrap", active ? "text-accent-800" : "text-ink-muted")}
              >
                <Icon className="size-4" aria-hidden />
                {label}
              </Link>
            );
          })}
        </nav>
        <main id="main" className={cn("min-w-0 flex-1 px-4 py-6 pb-24 md:px-6 md:pb-8 lg:px-8", sponsor && "bg-sponsor-50")}>
          <div className="mx-auto max-w-[1400px]">{children}</div>
        </main>
      </div>
    </div>
  );
}
