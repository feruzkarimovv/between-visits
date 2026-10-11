"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { LucideIcon } from "lucide-react";
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
  FlaskConical,
  PlayCircle,
  ShieldCheck,
  Building2,
  Mailbox,
} from "lucide-react";
import { useDrafts, useEscalations, useHealth, useStudy } from "@/lib/queries";
import { USE_FIXTURES } from "@/lib/api";
import { useNow } from "@/lib/hooks";
import { DISPLAY_TZ } from "@/lib/format";
import { EscalationBanner } from "../EscalationBanner";
import { ReplayAudioBar } from "../ReplayAudioBar";
import { RoleSwitch } from "../RoleSwitch";
import { BrandMark } from "../BrandMark";
import { cn } from "../ui/primitives";

interface NavItem {
  href: string;
  label: string;
  short: string;
  icon: LucideIcon;
  badge?: "escalations" | "drafts";
  tag?: string;
}

const GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Care team",
    items: [
      { href: "/", label: "Today", short: "Today", icon: CalendarCheck },
      { href: "/escalations", label: "Escalations", short: "Escalations", icon: BellRing, badge: "escalations" },
      { href: "/review", label: "Review queue", short: "Review", icon: ClipboardCheck, badge: "drafts" },
      { href: "/sae", label: "Serious events", short: "Serious events", icon: FileWarning },
      { href: "/patients", label: "Patients", short: "Patients", icon: Users },
    ],
  },
  {
    label: "Study",
    items: [
      { href: "/plan", label: "Check-in plan", short: "Plan", icon: ListChecks },
      { href: "/report-card", label: "Safety report card", short: "Report card", icon: Gauge },
      { href: "/audit", label: "Audit trail", short: "Audit", icon: ScrollText },
    ],
  },
  {
    // Sponsor side: Site Signal (CRA), the mock site inbox its queries land in, and the mock sponsor safety inbox.
    label: "Sponsor",
    items: [
      { href: "/sites", label: "Sites", short: "Sites", icon: Building2 },
      { href: "/site-inbox", label: "Site inbox", short: "Site inbox", icon: Mailbox, tag: "mock" },
      { href: "/sponsor", label: "Sponsor inbox", short: "Sponsor inbox", icon: Inbox, tag: "mock" },
    ],
  },
];

const NAV = GROUPS.flatMap((g) => g.items);

/** `/sae` has its own nav item; `/sites` and `/site-inbox` must not light each other up. */
function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/checkins");
  return pathname === href || pathname.startsWith(`${href}/`);
}

// The rail (desktop) and the compact top-bar switch (phones) are never mounted together, so the
// "Demo role" label always names exactly one select. The server render assumes desktop.
const DESKTOP_QUERY = "(min-width: 768px)";

function subscribeDesktop(listener: () => void): () => void {
  const mq = window.matchMedia(DESKTOP_QUERY);
  mq.addEventListener("change", listener);
  return () => mq.removeEventListener("change", listener);
}

function useIsDesktop(): boolean {
  return useSyncExternalStore(
    subscribeDesktop,
    () => window.matchMedia(DESKTOP_QUERY).matches,
    () => true,
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const sponsor = pathname.startsWith("/sponsor");
  const desktop = useIsDesktop();

  return (
    <div className="flex min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:shadow-pop"
      >
        Skip to content
      </a>
      <Rail pathname={pathname} roleSwitch={desktop} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar roleSwitch={!desktop} />
        <main id="main" className={cn("min-w-0 flex-1 px-4 pt-6 pb-28 sm:px-6 md:pb-10 lg:px-10 lg:pt-8", sponsor && "bg-sponsor-50")}>
          {/* keyed by route so each page fades in; query-string changes (filters) don't re-trigger it */}
          <div key={pathname} className="bv-enter mx-auto max-w-[1360px]">
            {children}
          </div>
        </main>
      </div>
      <MobileNav pathname={pathname} />
      <ReplayAudioBar />
    </div>
  );
}

// ---------------------------------------------------------------- rail (desktop)

function Rail({ pathname, roleSwitch }: { pathname: string; roleSwitch: boolean }) {
  const escalations = useEscalations("open", 2000);
  const drafts = useDrafts({ status: "draft", kind: "", patient_id: "", checkin_id: "" }, 10_000);
  const open = escalations.data ?? [];
  const emergency = open.some((e) => e.level === "emergency");
  const urgent = open.some((e) => e.level === "urgent");
  const draftCount = drafts.data?.length ?? 0;

  return (
    <aside className="on-dark sticky top-0 hidden h-screen w-64 shrink-0 flex-col bg-rail text-rail-ink md:flex">
      <div className="bv-grid pointer-events-none absolute inset-x-0 top-0 h-40 [mask-image:linear-gradient(to_bottom,black,transparent)]" aria-hidden />
      <Link href="/" className="relative flex items-center gap-3 px-5 pt-5 pb-6">
        <BrandMark className="size-9" />
        <span className="leading-tight">
          <span className="block font-display text-[1.45rem] leading-none text-white">Between Visits</span>
          <span className="mt-1 block text-sm text-rail-muted">Trial check-ins</span>
        </span>
      </Link>

      <nav aria-label="Main" className="bv-scroll-dark relative flex-1 overflow-y-auto px-3">
        {GROUPS.map((group) => (
          <div key={group.label} className="mb-4 last:mb-1">
            <div className="px-3 pb-1.5 text-sm font-medium text-rail-muted/80">{group.label}</div>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const active = isActive(pathname, item.href);
                const Icon = item.icon;
                let badge: React.ReactNode = null;
                if (item.badge === "escalations" && open.length > 0) {
                  badge = (
                    <span
                      className={cn(
                        "ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-sm font-semibold tabular",
                        emergency ? "bg-red-600 text-white" : urgent ? "bg-amber-400 text-amber-950" : "bg-blue-500 text-white",
                      )}
                    >
                      {open.length}
                      <span className="sr-only"> open</span>
                    </span>
                  );
                } else if (item.badge === "drafts" && draftCount > 0) {
                  badge = (
                    <span className="ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-white/12 px-1.5 text-sm font-semibold text-rail-ink tabular">
                      {draftCount}
                      <span className="sr-only"> to review</span>
                    </span>
                  );
                }
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "group relative flex h-9 items-center gap-3 rounded-lg px-3 text-[15px] font-medium transition-colors",
                        active ? "bg-white/[0.08] text-white" : "text-rail-ink/80 hover:bg-white/[0.05] hover:text-white",
                      )}
                    >
                      {active ? <span className="absolute top-2 bottom-2 -left-3 w-1 rounded-r-full bg-live" aria-hidden /> : null}
                      <Icon className={cn("size-[18px] shrink-0", active ? "text-live" : "text-rail-muted group-hover:text-rail-ink")} aria-hidden />
                      <span className="truncate">{item.label}</span>
                      {item.tag ? (
                        <span className="rounded-md border border-rail-line px-1.5 text-sm leading-5 font-normal text-rail-muted">{item.tag}</span>
                      ) : null}
                      {badge}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="relative space-y-3 border-t border-rail-line p-3">
        <div className="flex items-start gap-2 rounded-lg px-2 text-sm leading-5 text-rail-muted">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-live/80" aria-hidden />
          <p>Synthetic data only. Not a medical device. Grades are provisional; clinicians decide.</p>
        </div>
        {roleSwitch ? <RoleSwitch variant="dark" /> : null}
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------- top bar

function TopBar({ roleSwitch }: { roleSwitch: boolean }) {
  const study = useStudy();
  const health = useHealth();
  const demoMode = health.data?.demo_mode === true;

  return (
    <header className="sticky top-0 z-30 border-b border-line/80 bg-canvas/85 backdrop-blur-md supports-[backdrop-filter]:bg-canvas/70">
      <div className="flex min-h-16 flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6 lg:px-10">
        <Link href="/" className="flex shrink-0 items-center gap-2.5 md:hidden" aria-label="Between Visits, Today">
          <BrandMark className="size-8" />
          <span className="hidden font-display text-xl leading-none text-ink sm:inline">Between Visits</span>
        </Link>

        <div className="hidden min-w-0 flex-1 items-center gap-3 md:flex">
          {study.data ? (
            <>
              <span className="shrink-0 rounded-md border border-line-strong bg-white px-2 py-0.5 font-mono text-sm font-medium text-ink-muted shadow-card">
                {study.data.nct_id}
              </span>
              <div className="min-w-0 leading-tight">
                <div className="truncate text-sm font-semibold text-ink" title={study.data.title_short}>
                  {study.data.title_short}
                </div>
                <div className="truncate text-sm text-ink-subtle">
                  Site {study.data.site_id} · {study.data.site_name}
                </div>
              </div>
            </>
          ) : (
            <span className="text-sm text-ink-subtle">{study.isError ? "Study unavailable" : "Loading study…"}</span>
          )}
        </div>

        <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2 sm:gap-3">
          {USE_FIXTURES ? (
            <span
              className="hidden items-center gap-1.5 rounded-full border border-dashed border-gray-400 bg-white/60 px-2.5 py-0.5 text-sm text-ink-muted lg:inline-flex"
              title="NEXT_PUBLIC_USE_FIXTURES=1: data comes from src/fixtures, not the backend"
            >
              <FlaskConical className="size-3.5" aria-hidden />
              Fixture data
            </span>
          ) : demoMode ? (
            <span
              className="hidden items-center gap-1.5 rounded-full border border-dashed border-accent-300 bg-accent-50 px-2.5 py-0.5 text-sm text-accent-800 lg:inline-flex"
              title="DEMO_MODE=1: no external keys; calls run as recorded replays"
            >
              <PlayCircle className="size-3.5" aria-hidden />
              Demo mode
            </span>
          ) : null}
          <LiveClock />
          <EscalationBanner />
          {roleSwitch ? <RoleSwitch variant="compact" className="md:hidden" /> : null}
        </div>
      </div>
    </header>
  );
}

const clockFmt = new Intl.DateTimeFormat("en-US", { timeZone: DISPLAY_TZ, hour: "numeric", minute: "2-digit" });
const dayFmt = new Intl.DateTimeFormat("en-US", { timeZone: DISPLAY_TZ, weekday: "short", month: "short", day: "numeric" });

function LiveClock() {
  const now = useNow();
  if (!now) return null;
  return (
    <span className="hidden items-baseline gap-1.5 text-sm text-ink-subtle xl:inline-flex" title="Site time (America/New_York)">
      <span>{dayFmt.format(now)}</span>
      <span className="font-medium text-ink-muted tabular">{clockFmt.format(now)}</span>
      <span>ET</span>
    </span>
  );
}

// ---------------------------------------------------------------- mobile nav

function MobileNav({ pathname }: { pathname: string }) {
  return (
    <nav
      aria-label="Main (mobile)"
      className="on-dark bv-scroll-dark fixed inset-x-0 bottom-0 z-30 flex overflow-x-auto border-t border-rail-line bg-rail/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    >
      {NAV.map(({ href, short, icon: Icon }) => {
        const active = isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex min-w-[4.75rem] flex-1 flex-col items-center gap-1 px-2 py-2.5 text-sm whitespace-nowrap",
              active ? "text-live" : "text-rail-muted",
            )}
          >
            <Icon className="size-5" aria-hidden />
            {short}
          </Link>
        );
      })}
    </nav>
  );
}
