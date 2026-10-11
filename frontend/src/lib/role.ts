"use client";

import { useSyncExternalStore } from "react";
import type { Role } from "./types";

export interface DemoIdentity {
  role: Role;
  user: string;
  label: string;
}

export const DEMO_IDENTITIES: Record<Role, DemoIdentity> = {
  coordinator: { role: "coordinator", user: "Jess Kim", label: "Coordinator" },
  investigator: { role: "investigator", user: "Dr. Patel", label: "Investigator" },
  sponsor: { role: "sponsor", user: "Sponsor safety (mock)", label: "Sponsor" },
  cra: { role: "cra", user: "Sam Rivera", label: "CRA (sponsor)" },
};

const STORAGE_KEY = "bv.demoRole";
const DEFAULT_ROLE: Role = "coordinator";

let current: Role = DEFAULT_ROLE;
let loaded = false;
const listeners = new Set<() => void>();

function isRole(v: unknown): v is Role {
  return typeof v === "string" && Object.prototype.hasOwnProperty.call(DEMO_IDENTITIES, v);
}

function load(): void {
  if (loaded || typeof window === "undefined") return;
  loaded = true;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isRole(stored)) current = stored;
  } catch {
    // storage blocked (private window etc.): keep the default role
  }
}

export function getRole(): Role {
  load();
  return current;
}

export function getIdentity(): DemoIdentity {
  return DEMO_IDENTITIES[getRole()];
}

export function setRole(role: Role): void {
  current = role;
  try {
    window.localStorage.setItem(STORAGE_KEY, role);
  } catch {
    // ignore
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Current demo identity; server render always sees the default role. */
export function useIdentity(): DemoIdentity {
  const role = useSyncExternalStore(subscribe, getRole, () => DEFAULT_ROLE);
  return DEMO_IDENTITIES[role];
}
