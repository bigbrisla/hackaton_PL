import { useCallback, useReducer, useRef } from "react";
import type { ChaosReading, Enriched, MatchEvent, Meta, Moment, Overlay, Story, TeamSummary, Trace } from "./types";

export interface LiveEvent {
  event: MatchEvent;
  enriched: Enriched;
}

export interface MatchState {
  status: "idle" | "connecting" | "live" | "ended" | "error";
  sessionId: string | null;
  model: string;
  meta: Meta | null;
  now: number;
  clock: string;
  score: Record<string, number>;
  chaos: ChaosReading | null;
  chaosHistory: { ts: number; chaos: number }[];
  home: TeamSummary | null;
  away: TeamSummary | null;
  events: LiveEvent[];
  frame: [string, number, number][] | null;
  overlays: Overlay[];
  moments: Moment[];
  stories: Story[];
  traces: Trace[];
}

const initial: MatchState = {
  status: "idle", sessionId: null, model: "", meta: null, now: 0, clock: "0'", score: {}, chaos: null,
  chaosHistory: [], home: null, away: null, events: [], frame: null, overlays: [], moments: [], stories: [], traces: [],
};

type Action = { type: "reset" } | { type: "status"; status: MatchState["status"] } | { type: "msg"; msg: any };

function reducer(s: MatchState, a: Action): MatchState {
  if (a.type === "reset") return { ...initial, status: "connecting" };
  if (a.type === "status") return { ...s, status: a.status };
  const m = a.msg;
  switch (m.kind) {
    case "meta":
      return { ...s, status: "live", meta: m.meta, sessionId: m.session_id, model: m.model, now: m.start_ts,
               score: { [m.meta.home.id]: 0, [m.meta.away.id]: 0 } };
    case "bootstrap": {
      const st = m.state;
      return { ...s, clock: st.clock, score: st.score, chaos: st.chaos, home: st.home, away: st.away,
               chaosHistory: m.chaos_series, moments: m.moments, now: st.ts };
    }
    case "event":
      return { ...s, now: m.event.ts, frame: m.frame ?? s.frame,
               events: [...s.events.slice(-299), { event: m.event, enriched: m.enriched }] };
    case "overlay":
      return { ...s, overlays: [...s.overlays.slice(-60), { ...m, shownAt: performance.now() }] };
    case "state":
      return { ...s, clock: m.clock, score: m.score, chaos: m.chaos ?? s.chaos, home: m.home, away: m.away,
               chaosHistory: m.chaos ? [...s.chaosHistory, { ts: m.ts, chaos: m.chaos.chaos }] : s.chaosHistory };
    case "moment":
      return { ...s, moments: [...s.moments.slice(-199), { ...m, receivedAt: performance.now() }] };
    case "agent_trace":
      return { ...s, traces: [...s.traces.slice(-399), m] };
    case "story":
      return { ...s, stories: [...s.stories.slice(-99), { ...m, receivedAt: performance.now() }] };
    case "end":
      return { ...s, status: "ended" };
    default:
      return s;
  }
}

export interface StreamOptions {
  matchId: string;
  speed: number;
  startMinute: number;
  langs: string[];
  focusPlayer: string | null;
}

export function useMatchStream() {
  const [state, dispatch] = useReducer(reducer, initial);
  const ws = useRef<WebSocket | null>(null);
  const listeners = useRef(new Set<(msg: any) => void>());

  const start = useCallback((o: StreamOptions) => {
    ws.current?.close();
    dispatch({ type: "reset" });
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const params = new URLSearchParams({ speed: String(o.speed), start_minute: String(o.startMinute), langs: o.langs.join(",") });
    if (o.focusPlayer) params.set("focus_player", o.focusPlayer);
    const sock = new WebSocket(`${proto}://${location.host}/ws/matches/${o.matchId}?${params}`);
    sock.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      dispatch({ type: "msg", msg });
      listeners.current.forEach((fn) => fn(msg));
    };
    sock.onerror = () => dispatch({ type: "status", status: "error" });
    ws.current = sock;
  }, []);

  const stop = useCallback(() => ws.current?.close(), []);

  // side-effect subscribers (audio, speech) see every message without re-rendering
  const subscribe = useCallback((fn: (msg: any) => void) => {
    listeners.current.add(fn);
    return () => {
      listeners.current.delete(fn);
    };
  }, []);

  return { state, start, stop, subscribe };
}
