"use client";

import type { ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Download } from "lucide-react";
import { apiDownload, errorMessage, type DownloadResult } from "@/lib/api";
import { Button, type ButtonProps } from "./ui/primitives";

/**
 * Downloads an export through `apiDownload()` (same headers as every API call, so it also works when the
 * dashboard token is on). Toasts the file name and the export's `X-BV-Note`; disabled while the file loads.
 */
export function DownloadButton({
  path,
  filename,
  children,
  variant = "secondary",
  size = "sm",
  className,
}: {
  /** API path, e.g. `/api/export/ae.csv`. */
  path: string;
  /** File name to use when the response has no Content-Disposition. */
  filename: string;
  children: ReactNode;
  variant?: ButtonProps["variant"];
  size?: ButtonProps["size"];
  className?: string;
}) {
  const download = useMutation<DownloadResult, unknown, void>({
    mutationFn: () => apiDownload(path, filename),
    onSuccess: (r) => toast.success(`Downloaded ${r.filename}`, r.note ? { description: r.note } : undefined),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Button
      variant={variant}
      size={size}
      className={className}
      loading={download.isPending}
      icon={<Download className="size-4" aria-hidden />}
      onClick={() => download.mutate()}
    >
      {children}
    </Button>
  );
}

/**
 * "Download AE.csv" and "Download CM.csv": confirmed entries only, SDTM-style, header row first (docs/03 §6.5).
 * The export's note (`X-BV-Note`) shows in the success toast.
 */
export function ExportDownloads({ variant = "secondary" }: { variant?: ButtonProps["variant"] }) {
  return (
    <>
      <DownloadButton path="/api/export/ae.csv" filename="ae.csv" variant={variant}>
        Download AE.csv
      </DownloadButton>
      <DownloadButton path="/api/export/cm.csv" filename="cm.csv" variant={variant}>
        Download CM.csv
      </DownloadButton>
    </>
  );
}
