import type { LiveEvent } from "../useMatchStream";
import type { Meta, Overlay, XY } from "../types";

export interface Spotlight {
  kind: "missed_option" | "brave_pass";
  from: XY;
  to: XY;
  best?: { xy: XY; name: string };
  options: XY[];
  label: string;
}

interface Props {
  meta: Meta;
  events: LiveEvent[];
  overlays: Overlay[];
  spotlight: Spotlight | null;
  focusPlayer: string | null;
  dimmed?: boolean;
}

const ON_BALL = new Set(["pass", "carry", "shot", "tackle", "interception", "set_piece", "save"]);

function Lines() {
  const s = { fill: "none", stroke: "rgba(255,255,255,.55)", strokeWidth: 0.35 };
  return (
    <g>
      <rect x={0} y={0} width={105} height={68} {...s} />
      <line x1={52.5} y1={0} x2={52.5} y2={68} {...s} />
      <circle cx={52.5} cy={34} r={9.15} {...s} />
      <circle cx={52.5} cy={34} r={0.4} fill="rgba(255,255,255,.7)" />
      {[0, 105].map((x) => {
        const d = x === 0 ? 1 : -1;
        return (
          <g key={x}>
            <rect x={x === 0 ? 0 : 105 - 16.5} y={34 - 20.16} width={16.5} height={40.32} {...s} />
            <rect x={x === 0 ? 0 : 105 - 5.5} y={34 - 9.16} width={5.5} height={18.32} {...s} />
            <circle cx={x + d * 11} cy={34} r={0.35} fill="rgba(255,255,255,.7)" />
            <rect x={x === 0 ? -1.6 : 105} y={34 - 3.66} width={1.6} height={7.32} fill="rgba(255,255,255,.18)" stroke="rgba(255,255,255,.7)" strokeWidth={0.3} />
          </g>
        );
      })}
    </g>
  );
}

export default function Pitch({ meta, events, overlays, spotlight, focusPlayer, dimmed }: Props) {
  const color = (team: string | null) =>
    team === meta.home.id ? meta.home.colors[0] : team === meta.away.id ? meta.away.colors[0] : "#fff";
  const names = new Map([...meta.home.players, ...meta.away.players].map((p) => [p.id, p]));
  const onBall = events.filter((e) => ON_BALL.has(e.event.type) && e.enriched.home_xy);
  const trail = onBall.slice(-9);
  const last = onBall[onBall.length - 1];
  const ball: XY | null = last ? (last.enriched.home_end_xy && last.event.outcome === "complete" ? last.enriched.home_end_xy : last.enriched.home_xy) : null;
  const actor = last?.event.player_id ? names.get(last.event.player_id) : undefined;
  const now = performance.now();
  const speed = overlays.find((o) => o.template === "speed_tag" && o.data.player_id === last?.event.player_id && now - (o.shownAt ?? 0) < 3500);
  const focusLast = focusPlayer ? [...onBall].reverse().find((e) => e.event.player_id === focusPlayer) : undefined;

  return (
    <svg className={`pitch ${dimmed ? "dimmed" : ""}`} viewBox="-3 -3 111 74" preserveAspectRatio="xMidYMid meet">
      <defs>
        <pattern id="stripes" width={10.5} height={68} patternUnits="userSpaceOnUse">
          <rect width={5.25} height={68} fill="#1f6b3a" />
          <rect x={5.25} width={5.25} height={68} fill="#22733f" />
        </pattern>
        <marker id="arrow" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={4} markerHeight={4} orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#fff" />
        </marker>
        <marker id="arrow-gold" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={4} markerHeight={4} orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#ffd34d" />
        </marker>
        <filter id="glow"><feGaussianBlur stdDeviation={0.8} result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      <rect x={-3} y={-3} width={111} height={74} fill="#1b5e33" />
      <rect x={0} y={0} width={105} height={68} fill="url(#stripes)" />
      <Lines />
      <text x={2} y={66.5} className="pitch-dir">{meta.home.short_name} attack →</text>

      {trail.map((e, i) => {
        const a = e.enriched.home_xy!, b = e.enriched.home_end_xy;
        const op = 0.15 + (0.75 * (i + 1)) / trail.length;
        return b ? (
          <line key={e.event.id} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={color(e.event.team_id)} strokeWidth={0.45}
                strokeDasharray={e.event.type === "carry" ? "1 0.8" : undefined} opacity={op} strokeLinecap="round" />
        ) : (
          <circle key={e.event.id} cx={a[0]} cy={a[1]} r={0.6} fill={color(e.event.team_id)} opacity={op} />
        );
      })}

      {spotlight && (
        <g className="spotlight">
          {spotlight.options.map((o, i) => <circle key={i} cx={o[0]} cy={o[1]} r={1.1} fill="none" stroke="rgba(255,255,255,.7)" strokeWidth={0.3} />)}
          <line x1={spotlight.from[0]} y1={spotlight.from[1]} x2={spotlight.to[0]} y2={spotlight.to[1]}
                stroke={spotlight.kind === "brave_pass" ? "#ffd34d" : "#fff"} strokeWidth={0.7}
                markerEnd={`url(#${spotlight.kind === "brave_pass" ? "arrow-gold" : "arrow"})`} filter="url(#glow)" />
          {spotlight.best && (
            <g>
              <line x1={spotlight.from[0]} y1={spotlight.from[1]} x2={spotlight.best.xy[0]} y2={spotlight.best.xy[1]}
                    stroke="#ffd34d" strokeWidth={0.7} strokeDasharray="1.6 1" markerEnd="url(#arrow-gold)" filter="url(#glow)" className="ghost" />
              <circle cx={spotlight.best.xy[0]} cy={spotlight.best.xy[1]} r={1.6} fill="none" stroke="#ffd34d" strokeWidth={0.4} className="pulse-ring" />
              <text x={spotlight.best.xy[0]} y={spotlight.best.xy[1] - 2.6} className="ghost-label">{spotlight.best.name}</text>
            </g>
          )}
          <text x={spotlight.from[0]} y={spotlight.from[1] + 4} className="spot-label">{spotlight.label}</text>
        </g>
      )}

      {focusLast && focusLast !== last && (
        <circle cx={focusLast.enriched.home_xy![0]} cy={focusLast.enriched.home_xy![1]} r={1.8} fill="none" stroke="#7df9ff" strokeWidth={0.35} strokeDasharray="0.8 0.6" />
      )}

      {ball && (
        <g style={{ transform: `translate(${ball[0]}px, ${ball[1]}px)`, transition: "transform 380ms ease-out" }}>
          <circle r={1.25} fill="#fff" stroke="#111" strokeWidth={0.25} filter="url(#glow)" />
        </g>
      )}

      {last && actor && last.enriched.home_xy && (
        <g transform={`translate(${last.enriched.home_xy[0]}, ${last.enriched.home_xy[1]})`}>
          <circle r={1.6} fill={color(last.event.team_id)} stroke="#fff" strokeWidth={0.3} />
          <g transform="translate(2.4,-3.4)" className="tag">
            <rect width={actor.short_name.length * 1.35 + 5 + (speed ? 9 : 0)} height={3.6} rx={0.6} fill="rgba(10,14,22,.85)" />
            <rect width={0.7} height={3.6} fill={color(last.event.team_id)} />
            <text x={1.5} y={2.6} className="tag-num">{actor.number}</text>
            <text x={4.2} y={2.6} className="tag-name">{actor.short_name}</text>
            {speed && <text x={actor.short_name.length * 1.35 + 5} y={2.6} className="tag-speed">{speed.data.speed_kmh} km/h</text>}
          </g>
        </g>
      )}
    </svg>
  );
}
