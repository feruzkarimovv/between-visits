import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <p className="text-lg font-semibold">Page not found</p>
      <p className="mt-1 text-sm text-ink-muted">That page doesn&apos;t exist in Between Visits.</p>
      <Link href="/" className="mt-4 rounded-md bg-accent-700 px-4 py-2 text-sm font-medium text-white hover:bg-accent-800">
        Back to Today
      </Link>
    </div>
  );
}
