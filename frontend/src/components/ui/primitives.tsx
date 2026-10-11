"use client";

import Link from "next/link";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2, RefreshCw, WifiOff, AlertTriangle } from "lucide-react";
import { isApiError } from "@/lib/api";

export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

// ------------------------------------------------------------------ Button

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success" | "soft" | "dark";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent-700 text-white border border-accent-800 shadow-[inset_0_1px_0_rgb(255_255_255/0.14),0_1px_2px_rgb(4_40_37/0.25)] hover:bg-accent-800",
  secondary: "bg-white text-ink border border-line-strong shadow-card hover:bg-gray-50 hover:border-gray-400/70",
  ghost: "bg-transparent text-ink-muted border border-transparent hover:bg-gray-100 hover:text-ink",
  danger:
    "bg-red-700 text-white border border-red-800 shadow-[inset_0_1px_0_rgb(255_255_255/0.14),0_1px_2px_rgb(127_29_29/0.3)] hover:bg-red-800",
  success:
    "bg-green-700 text-white border border-green-800 shadow-[inset_0_1px_0_rgb(255_255_255/0.14),0_1px_2px_rgb(20_83_45/0.3)] hover:bg-green-800",
  soft: "bg-accent-50 text-accent-800 border border-accent-200 hover:bg-accent-100",
  dark: "bg-white/10 text-white border border-white/15 hover:bg-white/15",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-sm gap-1.5 rounded-lg",
  md: "h-10 px-4 text-sm gap-2 rounded-lg",
  lg: "h-12 px-5 text-base gap-2 rounded-xl",
};

const BUTTON_BASE =
  "inline-flex shrink-0 select-none items-center justify-center font-medium whitespace-nowrap transition-[background-color,border-color,box-shadow,transform] duration-150 active:translate-y-px";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, disabled, className, children, type, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        BUTTON_BASE,
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:active:translate-y-0",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  icon,
  className,
  children,
}: {
  href: string;
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={cn(BUTTON_BASE, VARIANTS[variant], SIZES[size], className)}>
      {icon}
      {children}
    </Link>
  );
}

// ------------------------------------------------------------------ layout

export function Card({
  children,
  className,
  as: As = "section",
  id,
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article";
  id?: string;
}) {
  return (
    <As id={id} className={cn("rounded-2xl border border-line bg-surface shadow-card", className)}>
      {children}
    </As>
  );
}

export function CardHeader({
  title,
  subtitle,
  actions,
  icon,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-line px-5 py-4", className)}>
      <div className="flex min-w-0 items-start gap-3">
        {icon ? (
          <span className="mt-px flex size-8 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-ink-muted ring-1 ring-line">
            {icon}
          </span>
        ) : null}
        <div className="min-w-0">
          <h2 className="flex flex-wrap items-center gap-2 text-base leading-7 font-semibold text-ink">{title}</h2>
          {subtitle ? <p className="text-sm leading-5 text-ink-subtle">{subtitle}</p> : null}
        </div>
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="min-w-0">
        {eyebrow ? <div className="mb-1 text-sm font-medium text-accent-700">{eyebrow}</div> : null}
        <h1 className="font-display text-[2.5rem] leading-[1.05] text-ink">{title}</h1>
        {subtitle ? <div className="mt-2 max-w-3xl text-[15px] leading-6 text-ink-muted">{subtitle}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Field({ label, children, className }: { label: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-sm text-ink-subtle">{label}</dt>
      <dd className="mt-1 text-[15px] leading-6 font-medium break-words text-ink">{children}</dd>
    </div>
  );
}

// ------------------------------------------------------------------ identity

const AVATAR_TONES = [
  "bg-accent-100 text-accent-900 ring-accent-200",
  "bg-[#e6ebf1] text-[#2f3d4f] ring-[#d3dbe5]",
  "bg-[#f1ebe1] text-[#5a4630] ring-[#e4d9c8]",
  "bg-[#e6efe7] text-[#2f4f35] ring-[#d2e2d4]",
  "bg-[#eeeae6] text-[#4a423b] ring-[#ddd6cf]",
];

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/** Initials avatar with a calm, deterministic tint. Decorative: the name is always next to it. */
export function Avatar({
  name,
  seed,
  size = "md",
  className,
}: {
  name: string;
  seed?: string;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}) {
  const initials =
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase())
      .join("") || "?";
  const tone = AVATAR_TONES[hashString(seed ?? name) % AVATAR_TONES.length];
  const sizes = {
    sm: "size-8 text-sm",
    md: "size-10 text-[15px]",
    lg: "size-12 text-base",
    xl: "size-16 text-xl",
  };
  return (
    <span aria-hidden className={cn("inline-flex shrink-0 items-center justify-center rounded-full font-semibold ring-1 ring-inset", tone, sizes[size], className)}>
      {initials}
    </span>
  );
}

// ------------------------------------------------------------------ states

export function EmptyState({
  icon,
  title,
  children,
  action,
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      {icon ? (
        <div className="relative mb-4 flex items-center justify-center">
          <span className="absolute size-20 rounded-full border border-dashed border-line-strong" aria-hidden />
          <span className="absolute size-14 rounded-full bg-gray-100" aria-hidden />
          <span className="relative text-ink-subtle">{icon}</span>
        </div>
      ) : null}
      <p className={cn("text-base font-semibold text-ink", icon ? "mt-4" : null)}>{title}</p>
      {children ? <div className="mt-1 max-w-md text-sm leading-6 text-ink-muted">{children}</div> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  retrying,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}) {
  const network = isApiError(error) && error.isNetwork;
  const message = isApiError(error)
    ? error.message
    : error instanceof Error
      ? error.message
      : "Something went wrong.";
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center rounded-2xl border border-red-200 bg-gradient-to-b from-red-50 to-white px-6 py-10 text-center",
        className,
      )}
    >
      <div className="mb-3 flex size-12 items-center justify-center rounded-full bg-red-100 text-red-700 ring-8 ring-red-50">
        {network ? <WifiOff className="size-5" aria-hidden /> : <AlertTriangle className="size-5" aria-hidden />}
      </div>
      <p className="text-base font-semibold text-red-900">{network ? "Can't reach the backend" : "Couldn't load this"}</p>
      <p className="mt-1 max-w-md text-sm text-red-800">
        {network ? (
          <>
            Check that <code className="rounded bg-red-100 px-1 font-mono">make dev</code> is running.
          </>
        ) : (
          message
        )}
      </p>
      {onRetry ? (
        <Button className="mt-5" onClick={onRetry} loading={retrying} icon={<RefreshCw className="size-4" aria-hidden />}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn("relative overflow-hidden rounded-lg bg-gray-200/60", className)} aria-hidden>
      <div className="bv-shimmer absolute inset-0" />
    </div>
  );
}

export function LoadingRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2.5 p-5" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ table

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("relative overflow-x-auto", className)}>
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  );
}

export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <th
      scope="col"
      className={cn(
        "border-b border-line bg-gray-50/70 px-3 py-2.5 text-sm font-medium whitespace-nowrap text-ink-subtle first:pl-5 last:pr-5",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({ children, className, colSpan }: { children?: ReactNode; className?: string; colSpan?: number }) {
  return (
    <td colSpan={colSpan} className={cn("border-b border-line/80 px-3 py-3 align-middle first:pl-5 last:pr-5", className)}>
      {children}
    </td>
  );
}

// ------------------------------------------------------------------ form

export const inputClass =
  "w-full rounded-lg border border-line-strong bg-white px-3 py-2 text-sm text-ink shadow-[inset_0_1px_1px_rgb(16_28_26/0.03)] placeholder:text-ink-subtle transition-[border-color,box-shadow] focus-visible:border-accent-600 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-accent-500/15 disabled:bg-gray-50 disabled:text-ink-muted";

export const selectClass = cn(inputClass, "bv-select cursor-pointer");

export function Label({ htmlFor, children }: { htmlFor?: string; children: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-medium text-ink-muted">
      {children}
    </label>
  );
}

/** Pill-style segmented control (exclusive choice). */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  className,
  size = "md",
}: {
  value: T;
  options: { value: T; label: ReactNode; count?: number | null }[];
  onChange: (v: T) => void;
  label: string;
  className?: string;
  size?: "sm" | "md";
}) {
  return (
    <div role="group" aria-label={label} className={cn("inline-flex rounded-xl border border-line bg-gray-100/80 p-1", className)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg font-medium whitespace-nowrap transition-colors",
              size === "sm" ? "h-7 px-2.5 text-sm" : "h-8 px-3 text-sm",
              active ? "bg-white text-ink shadow-card ring-1 ring-line" : "text-ink-muted hover:text-ink",
            )}
          >
            {o.label}
            {typeof o.count === "number" ? (
              <span className={cn("rounded-full px-1.5 text-sm tabular", active ? "bg-accent-100 text-accent-800" : "bg-gray-200/80 text-ink-muted")}>
                {o.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
