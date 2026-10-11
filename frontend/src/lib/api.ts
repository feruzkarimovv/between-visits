"use client";

import { getIdentity } from "./role";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");

export const USE_FIXTURES = process.env.NEXT_PUBLIC_USE_FIXTURES === "1";

/**
 * Optional dashboard token for the private live instance (docs/03 §6.8). Inlined into the browser bundle,
 * so it keeps casual traffic off that instance; it is not authentication. Unset by default and in demo mode.
 */
const DASHBOARD_TOKEN = process.env.NEXT_PUBLIC_BV_DASHBOARD_TOKEN || "";

export const NETWORK_ERROR_MESSAGE =
  "Can't reach the backend. Check that `make dev` is running.";

/** Error thrown for any non-2xx response or network failure. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }

  get isNetwork(): boolean {
    return this.code === "network_error";
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

export interface ApiInit {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  /** JSON body; serialized for you. */
  body?: unknown;
  signal?: AbortSignal;
}

interface ErrorEnvelope {
  error?: { code?: unknown; message?: unknown };
  detail?: unknown;
}

function parseError(status: number, json: unknown): ApiError {
  const env = (json ?? {}) as ErrorEnvelope;
  if (env.error && typeof env.error === "object") {
    const code = typeof env.error.code === "string" ? env.error.code : `http_${status}`;
    const message =
      typeof env.error.message === "string" ? env.error.message : `Request failed (${status})`;
    return new ApiError(status, code, message);
  }
  // FastAPI default validation errors use {"detail": ...}
  if (typeof env.detail === "string") return new ApiError(status, `http_${status}`, env.detail);
  return new ApiError(status, `http_${status}`, `Request failed (${status})`);
}

/** Demo identity headers, plus X-BV-Token when NEXT_PUBLIC_BV_DASHBOARD_TOKEN is set (docs/03 §6.8). */
function requestHeaders(accept: string): Record<string, string> {
  const identity = getIdentity();
  const headers: Record<string, string> = {
    Accept: accept,
    "X-BV-User": identity.user,
    "X-BV-Role": identity.role,
  };
  if (DASHBOARD_TOKEN) headers["X-BV-Token"] = DASHBOARD_TOKEN;
  return headers;
}

function parseJson(text: string): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * The one way the dashboard talks to the backend. Adds the demo identity
 * headers (and X-BV-Token when NEXT_PUBLIC_BV_DASHBOARD_TOKEN is set), parses
 * JSON and throws `ApiError` for `{"error":{code,message}}`.
 * With NEXT_PUBLIC_USE_FIXTURES=1 every call is served from src/fixtures.
 */
export async function apiFetch<T>(path: string, init: ApiInit = {}): Promise<T> {
  const method = init.method ?? "GET";
  const identity = getIdentity();

  if (USE_FIXTURES) {
    const { handleFixture } = await import("@/fixtures");
    await new Promise((r) => setTimeout(r, 120));
    const res = handleFixture(method, path, init.body, identity);
    if (res.status >= 400) throw parseError(res.status, res.body);
    return res.body as T;
  }

  const headers = requestHeaders("application/json");
  let body: string | undefined;
  if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.body);
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body,
      signal: init.signal,
      cache: "no-store",
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "network_error", NETWORK_ERROR_MESSAGE);
  }

  const json = parseJson(await res.text());
  if (!res.ok) throw parseError(res.status, json);
  return json as T;
}

export interface DownloadResult {
  /** The file name the browser saved (from Content-Disposition, else the fallback). */
  filename: string;
  /** The `X-BV-Note` response header (docs/03 §6.5), when the export sends one. */
  note: string | null;
  bytes: number;
}

/** `filename` from a Content-Disposition header (`filename*=UTF-8''...` first), without any path part. */
function filenameFrom(disposition: string | null): string | null {
  if (!disposition) return null;
  const star = /filename\*\s*=\s*(?:[\w-]+'[^']*')?([^;]+)/i.exec(disposition);
  const plain = /filename\s*=\s*("([^"]*)"|[^;]+)/i.exec(disposition);
  let name: string | null = null;
  if (star) {
    try {
      name = decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      name = null;
    }
  }
  if (!name && plain) name = (plain[2] ?? plain[1]).trim();
  const base = name?.split(/[\\/]/).pop()?.trim();
  return base ? base : null;
}

/**
 * Downloads a file from the API with the same headers as `apiFetch()` (a plain link would not send X-BV-Token),
 * then hands it to the browser as a blob. Throws `ApiError` like `apiFetch()`, keyed on `error.code`.
 */
export async function apiDownload(path: string, fallbackFilename: string): Promise<DownloadResult> {
  if (USE_FIXTURES) {
    throw new ApiError(404, "export_unavailable", "Downloads need the backend; fixture mode has no export files.");
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { method: "GET", headers: requestHeaders("*/*"), cache: "no-store" });
  } catch {
    throw new ApiError(0, "network_error", NETWORK_ERROR_MESSAGE);
  }
  if (!res.ok) throw parseError(res.status, parseJson(await res.text()));

  const blob = await res.blob();
  const filename = filenameFrom(res.headers.get("Content-Disposition")) ?? fallbackFilename;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoke later: some browsers read the blob after click() returns.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  return { filename, note: res.headers.get("X-BV-Note"), bytes: blob.size };
}

/** True when `e` is an `ApiError` with one of these `error.code` values. Handle errors by code, not HTTP status. */
export function hasErrorCode(e: unknown, ...codes: string[]): e is ApiError {
  return isApiError(e) && codes.includes(e.code);
}

/** Extra guidance shown after the server's message, keyed on `error.code`. */
const CODE_HINTS: Record<string, string> = {
  wrong_role: "Switch the demo role in the top bar.",
};

/** Human message for a toast or error state. */
export function errorMessage(e: unknown): string {
  if (isApiError(e)) {
    const hint = CODE_HINTS[e.code];
    return hint ? `${e.message} ${hint}` : e.message;
  }
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}
