// Display helpers. Display timezone is America/New_York (DISPLAY_TZ).

export const DISPLAY_TZ = "America/New_York";

const absFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: DISPLAY_TZ,
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  timeZoneName: "short",
});

const timeFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: DISPLAY_TZ,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const dateFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: DISPLAY_TZ,
  month: "short",
  day: "numeric",
  year: "numeric",
});

const shortDateFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  month: "short",
  day: "numeric",
});

export function parseTs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

export function formatAbsolute(iso: string | null | undefined): string {
  const t = parseTs(iso);
  return t === null ? "—" : absFmt.format(t);
}

/** 24-hour clock time, e.g. "15:42". */
export function formatClock(iso: string | null | undefined): string {
  const t = parseTs(iso);
  return t === null ? "—" : timeFmt.format(t);
}

export function formatDate(iso: string | null | undefined): string {
  const t = parseTs(iso);
  return t === null ? "—" : dateFmt.format(t);
}

/** For plain YYYY-MM-DD dates (no time); avoids timezone shifting. */
export function formatDay(day: string | null | undefined): string {
  if (!day) return "—";
  const t = Date.parse(`${day.slice(0, 10)}T12:00:00Z`);
  return Number.isNaN(t) ? day : shortDateFmt.format(t);
}

/** Today's date (YYYY-MM-DD) in the display timezone. */
export function todayInTz(now = Date.now()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: DISPLAY_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

/** "0:21", "12:05", "1:02:09" */
export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds === null || totalSeconds === undefined || Number.isNaN(totalSeconds)) return "—";
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => n.toString().padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

/** "21 s", "4 min", "3 h 12 m", "2 d" */
export function formatSpan(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return m ? `${h} h ${m} m` : `${h} h`;
  }
  return `${Math.floor(s / 86400)} d`;
}

export function formatRelative(iso: string | null | undefined, now: number): string {
  const t = parseTs(iso);
  if (t === null) return "—";
  const diff = (now - t) / 1000;
  if (Math.abs(diff) < 5) return "just now";
  return diff >= 0 ? `${formatSpan(diff)} ago` : `in ${formatSpan(-diff)}`;
}

export function formatPercent(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

/** snake_case / SCREAMING_CASE → "Sentence case". */
export function humanize(code: string | null | undefined): string {
  if (!code) return "—";
  const s = code.replace(/^RF_/, "").replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function fullName(p: { first_name?: string | null; last_name?: string | null } | null | undefined): string {
  if (!p) return "";
  return [p.first_name, p.last_name].filter(Boolean).join(" ");
}
