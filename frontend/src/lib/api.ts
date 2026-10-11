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

  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-BV-User": identity.user,
    "X-BV-Role": identity.role,
  };
  if (DASHBOARD_TOKEN) headers["X-BV-Token"] = DASHBOARD_TOKEN;
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

  const text = await res.text();
  let json: unknown = null;
  if (text) {
    try {
      json = JSON.parse(text);
    } catch {
      json = null;
    }
  }
  if (!res.ok) throw parseError(res.status, json);
  return json as T;
}

/** Human message for a toast or error state. */
export function errorMessage(e: unknown): string {
  if (isApiError(e)) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}
