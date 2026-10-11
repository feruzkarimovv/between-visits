"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ConversationProvider, useConversation } from "@elevenlabs/react";
import { Mic, MicOff, PhoneOff, Headphones, AlertTriangle, Loader2, FlaskConical } from "lucide-react";
import { toast } from "sonner";
import { apiFetch, errorMessage, USE_FIXTURES } from "@/lib/api";
import { clearWebSession, loadWebSession } from "@/lib/webSession";
import { formatDuration } from "@/lib/format";
import type { OkResponse, WebSession } from "@/lib/types";
import { Button, cn } from "./ui/primitives";

interface Props {
  checkinId: string;
  subjectId: string;
  /** Check-in status from the backend; the widget hides its Start button once the call is over. */
  checkinStatus: string;
  onStarted?: () => void;
}

/**
 * Browser call (ElevenLabs WebRTC). Uses the web_session returned by
 * POST /api/patients/{id}/checkins, stashed in sessionStorage by the Today page.
 */
export function WebCallWidget(props: Props) {
  // Rendered client-only (next/dynamic, ssr: false), so sessionStorage is readable here.
  const [session] = useState<WebSession | null | undefined>(() =>
    typeof window === "undefined" ? undefined : loadWebSession(props.checkinId),
  );

  return (
    <section aria-label="Browser call" className="on-dark relative overflow-hidden rounded-2xl border border-rail-line bg-rail-raised text-rail-ink shadow-raised">
      <div className="bv-grid pointer-events-none absolute inset-0 opacity-50" aria-hidden />
      <div className="relative flex flex-wrap items-start justify-between gap-3 border-b border-white/10 px-5 py-4">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-live/30 bg-live/10 text-live">
            <Headphones className="size-[18px]" aria-hidden />
          </span>
          <div>
            <h2 className="text-base font-semibold text-white">Browser call</h2>
            <p className="text-sm text-rail-muted">Talk to the agent from this computer. Use a headset to avoid echo.</p>
          </div>
        </div>
      </div>
      <div className="relative p-5">
        {session === undefined ? (
          <p className="text-sm text-rail-muted">Loading call session…</p>
        ) : USE_FIXTURES ? (
          <FixtureCall {...props} />
        ) : session === null ? (
          <p className="text-sm leading-6 text-rail-ink/90">
            This browser call&apos;s session isn&apos;t available in this tab (it is kept only in the tab that started the
            call). Start a new browser call from <strong className="text-white">Today</strong>.
          </p>
        ) : (
          <ConversationProvider>
            <LiveCall {...props} session={session} />
          </ConversationProvider>
        )}
      </div>
    </section>
  );
}

function usePostWebStarted(checkinId: string, onStarted?: () => void) {
  const posted = useRef(false);
  return useCallback(
    async (conversationId: string) => {
      if (posted.current) return;
      posted.current = true;
      try {
        await apiFetch<OkResponse>(`/api/checkins/${encodeURIComponent(checkinId)}/web-started`, {
          method: "POST",
          body: { conversation_id: conversationId },
        });
        onStarted?.();
      } catch (e) {
        posted.current = false;
        toast.error(`Call connected, but the backend wasn't told: ${errorMessage(e)}`);
      }
    },
    [checkinId, onStarted],
  );
}

function LiveCall({ checkinId, subjectId, checkinStatus, onStarted, session }: Props & { session: WebSession }) {
  const [micError, setMicError] = useState<string | null>(null);
  const [connError, setConnError] = useState<string | null>(null);
  const [connectedAt, setConnectedAt] = useState<number | null>(null);
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const postStarted = usePostWebStarted(checkinId, onStarted);

  const convo = useConversation({
    onConnect: ({ conversationId }) => {
      setConnectedAt(Date.now());
      setConnError(null);
      void postStarted(conversationId || session.conversation_id || "");
    },
    onDisconnect: () => {
      setConnectedAt(null);
      clearWebSession(checkinId);
    },
    onError: (message) => setConnError(typeof message === "string" ? message : "Connection error"),
  });

  const connected = convo.status === "connected";
  const connecting = convo.status === "connecting";

  // mic level + elapsed time while connected
  useEffect(() => {
    if (!connected) return;
    let raf = 0;
    const loop = () => {
      try {
        setLevel(Math.min(1, convo.getInputVolume() * 2.5));
      } catch {
        setLevel(0);
      }
      if (connectedAt) setElapsed((Date.now() - connectedAt) / 1000);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [connected, connectedAt, convo]);

  const start = async () => {
    setMicError(null);
    setConnError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
    } catch (e) {
      const denied = e instanceof DOMException && (e.name === "NotAllowedError" || e.name === "SecurityError");
      setMicError(
        denied
          ? "Microphone access was blocked. Allow the microphone for this site in the browser's address bar, then press Start call again."
          : "No microphone was found. Plug in a headset and try again.",
      );
      return;
    }
    convo.startSession({
      conversationToken: session.conversation_token,
      connectionType: "webrtc",
      dynamicVariables: session.dynamic_variables,
      userId: subjectId,
    });
  };

  const over = ["completed", "cancelled", "failed", "no_answer"].includes(checkinStatus);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-4">
        {!connected ? (
          <Button
            variant="primary"
            size="lg"
            className="border-live/40 bg-accent-600 px-6 hover:bg-accent-500"
            onClick={() => void start()}
            loading={connecting}
            disabled={over}
            icon={<Mic className="size-5" aria-hidden />}
          >
            {over ? "Call ended" : "Start call"}
          </Button>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="dark"
              size="lg"
              onClick={() => convo.setMuted(!convo.isMuted)}
              icon={convo.isMuted ? <MicOff className="size-5" aria-hidden /> : <Mic className="size-5" aria-hidden />}
            >
              {convo.isMuted ? "Unmute" : "Mute"}
            </Button>
            <Button variant="danger" size="lg" onClick={() => convo.endSession()} icon={<PhoneOff className="size-5" aria-hidden />}>
              End call
            </Button>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <ConnectionPill status={convo.status} />
          {connected ? (
            <span className="text-sm text-rail-ink/90 tabular">
              {convo.isSpeaking ? "Agent speaking" : "Listening"} · {formatDuration(elapsed)}
            </span>
          ) : null}
        </div>
      </div>

      <MicMeter level={connected ? level : 0} muted={convo.isMuted} active={connected} />

      {micError ? <Problem>{micError}</Problem> : null}
      {connError ? <Problem>{`Call connection problem: ${connError}. The token is valid for 15 minutes after the call was created; if it expired, start a new browser call from Today.`}</Problem> : null}
    </div>
  );
}

/** Fixture mode: no ElevenLabs; pressing Start just tells the fixture backend the call began. */
function FixtureCall({ checkinId, checkinStatus, onStarted }: Props) {
  const postStarted = usePostWebStarted(checkinId, onStarted);
  const [pending, setPending] = useState(false);
  const started = checkinStatus !== "dialing";
  return (
    <div className="space-y-4">
      <p className="flex items-start gap-2 text-sm text-rail-muted">
        <FlaskConical className="mt-0.5 size-4 shrink-0" aria-hidden />
        Fixture mode: no audio. Starting the call plays a scripted conversation into this page.
      </p>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-4">
        <Button
          variant="primary"
          size="lg"
          className="border-live/40 bg-accent-600 px-6 hover:bg-accent-500"
          disabled={started}
          loading={pending}
          icon={<Mic className="size-5" aria-hidden />}
          onClick={async () => {
            setPending(true);
            await postStarted(`conv_fixture_${checkinId}`);
            setPending(false);
          }}
        >
          {["completed", "cancelled", "failed", "no_answer"].includes(checkinStatus) ? "Call ended" : started ? "Call started" : "Start call"}
        </Button>
        <ConnectionPill status={checkinStatus === "in_progress" ? "connected" : "disconnected"} />
      </div>
      <MicMeter level={started && checkinStatus === "in_progress" ? 0.35 : 0} muted={false} active={checkinStatus === "in_progress"} />
    </div>
  );
}

function ConnectionPill({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    disconnected: { label: "Not connected", cls: "border-white/15 bg-white/5 text-rail-muted" },
    connecting: { label: "Connecting…", cls: "border-live/40 bg-live/10 text-live" },
    connected: { label: "Connected", cls: "border-green-400/50 bg-green-500/15 text-green-200" },
    error: { label: "Connection error", cls: "border-red-400/60 bg-red-500/15 text-red-200" },
  };
  const s = map[status] ?? map.disconnected;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm font-medium", s.cls)}>
      {status === "connecting" ? (
        <Loader2 className="size-3.5 animate-spin" aria-hidden />
      ) : (
        <span className={cn("size-2 rounded-full", status === "connected" ? "bg-green-400" : status === "error" ? "bg-red-400" : "bg-rail-muted")} aria-hidden />
      )}
      {s.label}
    </span>
  );
}

function MicMeter({ level, muted, active }: { level: number; muted: boolean; active: boolean }) {
  const bars = 32;
  const lit = Math.round(level * bars);
  return (
    <div className="flex items-center gap-3" aria-label={active ? (muted ? "Microphone muted" : "Microphone level") : "Microphone idle"}>
      {muted ? <MicOff className="size-4 text-rail-muted" aria-hidden /> : <Mic className="size-4 text-rail-muted" aria-hidden />}
      <div className="flex h-6 flex-1 items-end gap-[3px]" aria-hidden>
        {Array.from({ length: bars }, (_, i) => (
          <span
            key={i}
            className={cn("max-w-2 flex-1 rounded-sm transition-[height,background-color] duration-75", i < lit && !muted ? "bg-live" : "bg-white/10")}
            style={{ height: `${30 + (i / bars) * 70}%` }}
          />
        ))}
      </div>
      <span className="w-16 text-sm text-rail-muted">{!active ? "Mic idle" : muted ? "Muted" : "Mic on"}</span>
    </div>
  );
}

function Problem({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="flex items-start gap-2 rounded-lg border border-red-400/40 bg-red-500/10 p-3 text-sm leading-6 text-red-100">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-red-300" aria-hidden />
      {children}
    </p>
  );
}
