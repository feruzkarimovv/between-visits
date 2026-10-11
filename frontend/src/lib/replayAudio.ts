"use client";

import { useSyncExternalStore } from "react";
import { API_BASE_URL } from "./api";

/**
 * Demo replay audio (docs/03 §6.2 `audio_url`). One module-level <audio> element, so the call keeps playing when
 * Replay navigates from Today to the check-in page. It starts inside the Replay click (browsers only allow sound
 * after a user gesture) at the replay's speed; there is no pause, because the backend replay keeps running.
 */
export interface ReplayAudioState {
  title: string;
  speed: number;
  playing: boolean;
  muted: boolean;
  current: number;
  duration: number;
  blocked: boolean;
}

let audio: HTMLAudioElement | null = null;
let startedAt = 0;
let state: ReplayAudioState | null = null;
const listeners = new Set<() => void>();

function emit(next: ReplayAudioState | null) {
  state = next;
  for (const l of listeners) l();
}

function patch(p: Partial<ReplayAudioState>) {
  if (state) emit({ ...state, ...p });
}

export function startReplayAudio(audioUrl: string, opts: { title: string; speed: number }) {
  stopReplayAudio();
  const el = new Audio(`${API_BASE_URL}${audioUrl}`);
  el.preload = "auto";
  el.playbackRate = opts.speed;
  el.preservesPitch = true;
  el.ontimeupdate = () => patch({ current: el.currentTime, duration: Number.isFinite(el.duration) ? el.duration : 0 });
  el.onloadedmetadata = () => patch({ duration: el.duration });
  el.onended = () => patch({ playing: false, current: el.duration });
  audio = el;
  startedAt = Date.now();
  emit({ title: opts.title, speed: opts.speed, playing: true, muted: false, current: 0, duration: 0, blocked: false });
  el.play().catch(() => {
    if (audio === el) patch({ playing: false, blocked: true });
  });
}

/** After the browser blocked autoplay: play from where the replay is now, so sound and events stay in step. */
export function startReplayAudioRetry() {
  const el = audio;
  if (!el || !state) return;
  el.currentTime = ((Date.now() - startedAt) / 1000) * state.speed;
  patch({ playing: true, blocked: false });
  el.play().catch(() => {
    if (audio === el) patch({ playing: false, blocked: true });
  });
}

export function stopReplayAudio() {
  if (audio) {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    audio = null;
  }
  emit(null);
}

export function toggleReplayMute() {
  if (!audio || !state) return;
  audio.muted = !audio.muted;
  patch({ muted: audio.muted });
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useReplayAudio(): ReplayAudioState | null {
  return useSyncExternalStore(
    subscribe,
    () => state,
    () => null,
  );
}
