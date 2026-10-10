"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ConversationProvider, useConversation } from "@elevenlabs/react";
import { Mic, MicOff, PhoneOff, Headphones, AlertTriangle, Loader2, FlaskConical } from "lucide-react";
import { toast } from "sonner";
import { apiFetch, errorMessage, USE_FIXTURES } from "@/lib/api";
import { clearWebSession, loadWebSession } from "@/lib/webSession";
import { formatDuration } from "@/lib/format";
import type { OkResponse, WebSession } from "@/lib/types";
import { Button, Card, CardHeader, cn } from "./ui/primitives";

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
    <Card className="border-accent-200">
      <CardHeader
        title="Browser call"
        icon={<Headphones className="size-4 text-accent-700" aria-hidden />}
        subtitle="Talk to the agent from this computer. Use a headset to avoid echo."
      />
      <div className="p-4">
        {session === undefined ? (
          <p className="text-sm text-ink-subtle">Loading call session…</p>
        ) : USE_FIXTURES ? (
          <FixtureCall {...props} />
        ) : session === null ? (
          <p className="text-sm text-ink-muted">
            This browser call&apos;s session isn&apos;t available in this tab (it is kept only in the tab that started the
            call). Start a new browser call from <strong>Today</strong>.
          </p>
        ) : (
          <ConversationProvider>
            <LiveCall {...props} session={session} />
          </ConversationProvider>
        )}
      </div>
    </Card>
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
      <div className="flex flex-wrap items-center gap-3">
        <ConnectionPill status={convo.status} />
        {connected ? (
          <span className="text-sm text-ink-muted tabular">
            {convo.isSpeaking ? "Agent speaking" : "Listening"} · {formatDuration(elapsed)}
          </span>
        ) : null}
      </div>

      <MicMeter level={connected ? level : 0} muted={convo.isMuted} active={connected} />

      <div className="flex flex-wrap gap-2">
        {!connected ? (
          <Button variant="primary" size="lg" onClick={() => void start()} loading={connecting} disabled={over} icon={<Mic className="size-5" aria-hidden />}>
            {over ? "Call ended" : "Start call"}
          </Button>
        ) : (
          <>
            <Button
              variant="secondary"
              onClick={() => convo.setMuted(!convo.isMuted)}
              icon={convo.isMuted ? <MicOff className="size-4" aria-hidden /> : <Mic className="size-4" aria-hidden />}
            >
              {convo.isMuted ? "Unmute" : "Mute"}
            </Button>
            <Button variant="danger" onClick={() => convo.endSession()} icon={<PhoneOff className="size-4" aria-hidden />}>
              End call
            </Button>
          </>
        )}
      </div>

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
    <div className="space-y-3">
      <p className="flex items-start gap-2 text-sm text-ink-muted">
        <FlaskConical className="mt-0.5 size-4 shrink-0" aria-hidden />
        Fixture mode: no audio. Starting the call plays a scripted conversation into this page.
      </p>
      <MicMeter level={started && checkinStatus === "in_progress" ? 0.35 : 0} muted={false} active={checkinStatus === "in_progress"} />
      <Button
        variant="primary"
        size="lg"
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
    </div>
  );
}

function ConnectionPill({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    disconnected: { label: "Not connected", cls: "border-gray-300 bg-gray-50 text-ink-muted" },
    connecting: { label: "Connecting…", cls: "border-accent-200 bg-accent-50 text-accent-800" },
    connected: { label: "Connected", cls: "border-green-300 bg-green-50 text-green-800" },
    error: { label: "Connection error", cls: "border-red-300 bg-red-50 text-red-800" },
  };
  const s = map[status] ?? map.disconnected;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm font-medium", s.cls)}>
      {status === "connecting" ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <span className={cn("size-2 rounded-full", status === "connected" ? "bg-green-600" : status === "error" ? "bg-red-600" : "bg-gray-400")} aria-hidden />}
      {s.label}
    </span>
  );
}

function MicMeter({ level, muted, active }: { level: number; muted: boolean; active: boolean }) {
  const bars = 16;
  const lit = Math.round(level * bars);
  return (
    <div className="flex items-center gap-3" aria-label={active ? (muted ? "Microphone muted" : "Microphone level") : "Microphone idle"}>
      {muted ? <MicOff className="size-4 text-ink-subtle" aria-hidden /> : <Mic className="size-4 text-ink-subtle" aria-hidden />}
      <div className="flex h-5 items-end gap-0.5" aria-hidden>
        {Array.from({ length: bars }, (_, i) => (
          <span
            key={i}
            className={cn("w-1.5 rounded-sm transition-[height,background-color] duration-75", i < lit && !muted ? "bg-accent-600" : "bg-gray-200")}
            style={{ height: `${30 + (i / bars) * 70}%` }}
          />
        ))}
      </div>
      <span className="text-sm text-ink-subtle">{!active ? "Mic idle" : muted ? "Muted" : "Mic on"}</span>
    </div>
  );
}

function Problem({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      {children}
    </p>
  );
}
