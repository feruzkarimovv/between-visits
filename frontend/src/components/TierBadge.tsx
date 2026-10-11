import { CircleSlash, Eye, Minus, ScanSearch, type LucideIcon } from "lucide-react";
import type { NotComputedReason, SignalTier, SiteSignalLabels } from "@/lib/types";
import { cn } from "./ui/primitives";

/**
 * Site Signal tier badge (docs/06 § Site Signal pages, docs/10 §6.1).
 *
 * Tiers have their own neutral slate scale and never reuse the clinical state colors, so a
 * statistical tier is never read as an escalation and no tier ever reads as "fine":
 *   watch        strongest emphasis: dark slate fill, white text
 *   look         medium emphasis: slate outline
 *   none         neutral slate text ("No signal at this sample size")
 *   not_computed light slate, always with its reason
 * All text comes from `labels` in `GET /api/sites` (data/signal_rules.json); this file holds no label
 * literals. Without labels (503 `site_signal_unavailable`, or not loaded yet) the badge renders the
 * not-computed style with `unavailableText`, for example the API error message.
 */

const STYLES: Record<SignalTier, { className: string; icon: LucideIcon }> = {
  watch: { className: "border-slate-800 bg-slate-800 font-medium text-white", icon: Eye },
  look: { className: "border-slate-600 bg-white font-medium text-slate-900", icon: ScanSearch },
  none: { className: "border-transparent bg-transparent font-normal text-slate-600", icon: Minus },
  not_computed: { className: "border-slate-200 bg-slate-100 font-normal text-slate-700", icon: CircleSlash },
};

const PILL = "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-sm leading-5";

export function TierBadge({
  tier,
  reason,
  labels,
  unavailableText,
  reasonDisplay = "visible",
  className,
}: {
  tier: SignalTier;
  /** `not_computed_reason`; used for `not_computed` only. */
  reason?: NotComputedReason | null;
  /** `labels` from `GET /api/sites`; null or undefined while unavailable. */
  labels: SiteSignalLabels | null | undefined;
  /** Text shown when `labels` is unavailable (for example the 503 error message). */
  unavailableText?: string;
  /**
   * `visible`: the reason sentence follows the badge (default; cards and wide cells).
   * `tooltip`: the reason is the badge's tooltip and stays in its accessible text (dense tables).
   */
  reasonDisplay?: "visible" | "tooltip";
  className?: string;
}) {
  if (!labels) {
    const Icon = STYLES.not_computed.icon;
    return (
      <span className={cn(PILL, STYLES.not_computed.className, className)} data-tier="unavailable">
        <Icon className="size-3.5" aria-hidden />
        {unavailableText}
      </span>
    );
  }

  // An unexpected tier string from the API renders in the not-computed style with its raw value.
  const style = STYLES[tier] ?? STYLES.not_computed;
  const Icon = style.icon;
  const text = labels[tier] ?? tier;
  const reasonText = tier === "not_computed" && reason ? (labels.reasons[reason] ?? reason) : null;
  const inlineReason = reasonText !== null && reasonDisplay === "visible";

  const pill = (
    <span
      className={cn(PILL, "whitespace-nowrap", style.className, !inlineReason && className)}
      title={reasonText && !inlineReason ? reasonText : undefined}
      data-tier={tier}
    >
      <Icon className="size-3.5" aria-hidden />
      {text}
      {reasonText && !inlineReason ? <span className="sr-only">: {reasonText}</span> : null}
    </span>
  );

  if (!inlineReason) return pill;

  return (
    <span className={cn("inline-flex flex-wrap items-baseline gap-x-2 gap-y-1", className)}>
      {pill}
      <span className="sr-only">: </span>
      <span className="text-sm leading-5 text-slate-600">{reasonText}</span>
    </span>
  );
}
