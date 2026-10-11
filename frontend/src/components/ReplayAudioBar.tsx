"use client";

import { AudioLines, Play, Volume2, VolumeX, X } from "lucide-react";
import { startReplayAudioRetry, stopReplayAudio, toggleReplayMute, useReplayAudio } from "@/lib/replayAudio";
import { cn } from "./ui/primitives";

function clock(s: number): string {
  const t = Math.max(0, Math.floor(s));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

/** Floating player for the demo replay's audio; stays on screen across pages until stopped or finished. */
export function ReplayAudioBar() {
  const a = useReplayAudio();
  if (!a) return null;
  const pct = a.duration > 0 ? Math.min(100, (a.current / a.duration) * 100) : 0;
  const done = !a.playing && !a.blocked && a.duration > 0 && a.current >= a.duration;

  return (
    <div
      role="region"
      aria-label="Replay audio"
      className="on-dark fixed bottom-20 left-4 z-40 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-rail-line bg-rail text-rail-ink shadow-pop md:bottom-6 md:left-[calc(16rem+1.5rem)] lg:left-[calc(16rem+2.5rem)]"
    >
      <div className="flex items-center gap-3 p-3">
        <AudioLines className={cn("size-5 shrink-0 text-live", a.playing && "animate-pulse")} aria-hidden />
        <div className="min-w-0 flex-1 leading-tight">
          <div className="truncate text-sm font-medium" title={a.title}>
            {a.title}
          </div>
          <div className="text-sm text-rail-muted tabular">
            {a.blocked ? "Browser blocked sound" : done ? "Call ended" : `${clock(a.current)} / ${clock(a.duration)}`} · {a.speed}x ·
            Scripted, synthesized voices
          </div>
        </div>
        {a.blocked ? (
          <button
            type="button"
            onClick={startReplayAudioRetry}
            className="rounded-lg p-1.5 text-rail-muted hover:bg-rail-raised hover:text-rail-ink"
            aria-label="Play sound"
          >
            <Play className="size-4" aria-hidden />
          </button>
        ) : (
          <button
            type="button"
            onClick={toggleReplayMute}
            className="rounded-lg p-1.5 text-rail-muted hover:bg-rail-raised hover:text-rail-ink"
            aria-label={a.muted ? "Unmute" : "Mute"}
          >
            {a.muted ? <VolumeX className="size-4" aria-hidden /> : <Volume2 className="size-4" aria-hidden />}
          </button>
        )}
        <button
          type="button"
          onClick={stopReplayAudio}
          className="rounded-lg p-1.5 text-rail-muted hover:bg-rail-raised hover:text-rail-ink"
          aria-label="Close player"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>
      <div className="h-1 bg-rail-raised">
        <div className="h-full bg-live transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
