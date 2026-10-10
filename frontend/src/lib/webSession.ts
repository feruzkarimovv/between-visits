"use client";

import type { WebSession } from "./types";

// The create-checkin POST returns the browser call's web_session once; the live
// page needs it after navigation, so it is stashed per check-in in sessionStorage.

const key = (checkinId: string) => `bv.webSession.${checkinId}`;

export function saveWebSession(checkinId: string, session: WebSession): void {
  try {
    window.sessionStorage.setItem(key(checkinId), JSON.stringify(session));
  } catch {
    // storage unavailable: the live page will explain that the session is missing
  }
}

export function loadWebSession(checkinId: string): WebSession | null {
  try {
    const raw = window.sessionStorage.getItem(key(checkinId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as WebSession;
    return parsed && typeof parsed.conversation_token === "string" ? parsed : null;
  } catch {
    return null;
  }
}

export function clearWebSession(checkinId: string): void {
  try {
    window.sessionStorage.removeItem(key(checkinId));
  } catch {
    // ignore
  }
}
