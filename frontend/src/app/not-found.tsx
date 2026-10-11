import Link from "next/link";
import { BrandMark } from "@/components/BrandMark";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <BrandMark className="size-14" />
      <p className="mt-6 font-display text-[2.5rem] leading-none text-ink">Page not found</p>
      <p className="mt-3 text-[15px] text-ink-muted">That page doesn&apos;t exist in Between Visits.</p>
      <Link
        href="/"
        className="mt-6 inline-flex h-10 items-center rounded-lg border border-accent-800 bg-accent-700 px-4 text-sm font-medium text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.14)] hover:bg-accent-800"
      >
        Back to Today
      </Link>
    </div>
  );
}
