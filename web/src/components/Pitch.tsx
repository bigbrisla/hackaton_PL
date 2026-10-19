import type { LiveEvent } from "../useMatchStream";
import type { Meta, Overlay, Player, XY } from "../types";

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
  frame: [string, number, number][] | null;
  overlays: Overlay[];
  spotlight: Spotlight | null;
  focusPlayer: string | null;
  camera: "broadcast" | "tactical";
  speed: number;
  dimmed?: boolean;
}

const ON_BALL = new Set(["pass", "carry", "shot", "tackle", "interception", "set_piece", "save"]);
// top-down shirt silhouette centred on (0,0), about 3.4m wide
const SHIRT = "M-1.7,-1.1 L-0.75,-1.65 Q0,-1.25 0.75,-1.65 L1.7,-1.1 L1.35,-0.15 L1.0,-0.35 L1.0,1.55 L-1.0,1.55 L-1.0,-0.35 L-1.35,-0.15 Z";

function Lines() {
  const s = { fill: "none", stroke: "rgba(255,255,255,.75)", strokeWidth: 0.3 };
  return (
    <g>
      <rect x={0} y={0} width={105} height={68} {...s} />
      <line x1={52.5} y1={0} x2={52.5} y2={68} {...s} />
      <circle cx={52.5} cy={34} r={9.15} {...s} />
      <circle cx={52.5} cy={34} r={0.35} fill="rgba(255,255,255,.8)" />
      {[0, 105].map((x) => {
        const d = x === 0 ? 1 : -1;
        const bx = x === 0 ? 0 : 105 - 16.5;
        return (
          <g key={x}>
            <rect x={bx} y={34 - 20.16} width={16.5} height={40.32} {...s} />
            <rect x={x === 0 ? 0 : 105 - 5.5} y={34 - 9.16} width={5.5} height={18.32} {...s} />
            <circle cx={x + d * 11} cy={34} r={0.3} fill="rgba(255,255,255,.8)" />
            <path d={x === 0 ? "M16.5,26.7 A9.15,9.15 0 0,1 16.5,41.3" : "M88.5,26.7 A9.15,9.15 0 0,0 88.5,41.3"} {...s} />
            <rect x={x === 0 ? -1.8 : 105} y={34 - 3.66} width={1.8} height={7.32} fill="rgba(255,255,255,.12)" stroke="rgba(255,255,255,.85)" strokeWidth={0.3} />
          </g>
        );
      })}
      {[[0, 0], [105, 0], [0, 68], [105, 68]].map(([cx, cy]) => (
        <path key={`${cx}${cy}`} d={`M${cx + (cx ? -1 : 1)},${cy} A1,1 0 0,${(cx === 0) === (cy === 0) ? 0 : 1} ${cx},${cy + (cy ? -1 : 1)}`} {...s} />
      ))}
    </g>
  );
}

export default function Pitch({ meta, events, frame, overlays, spotlight, focusPlayer, camera, speed, dimmed }: Props) {
  const roster = new Map<string, Player & { home: boolean }>([
    ...meta.home.players.map((p) => [p.id, { ...p, home: true }] as const),
    ...meta.away.players.map((p) => [p.id, { ...p, home: false }] as const),
  ]);
  const kit = (home: boolean) => (home ? meta.home.colors : meta.away.colors);
  const teamColor = (team: string | null) => (team === meta.home.id ? meta.home.colors[0] : team === meta.away.id ? meta.away.colors[0] : "#fff");
  const onBall = events.filter((e) => ON_BALL.has(e.event.type) && e.enriched.home_xy);
  const trail = onBall.slice(-7);
  const last = onBall[onBall.length - 1];
  const ball: XY | null = last ? (last.enriched.home_end_xy && last.event.outcome === "complete" ? last.enriched.home_end_xy : last.enriched.home_xy) : null;
  const carrierId = last?.event.player_id ?? null;
  const now = performance.now();
  const speedTag = overlays.find((o) => o.template === "speed_tag" && now - (o.shownAt ?? 0) < 3500);
  const move = `transform ${Math.max(250, 1100 / Math.sqrt(speed))}ms cubic-bezier(.45,.05,.35,1)`;

  const tag = (pid: string, x: number, y: number, extra?: string, color = "rgba(8,12,20,.9)") => {
    const p = roster.get(pid);
    if (!p) return null;
    const w = p.short_name.length * 1.3 + 5.2 + (extra ? extra.length * 1.05 + 1 : 0);
    return (
      <g key={`tag-${pid}`} className="ptag" style={{ transform: `translate(${x - w / 2}px, ${y - 6.4}px)`, transition: move }}>
        <rect width={w} height={3.4} rx={0.7} fill={color} />
        <rect width={0.8} height={3.4} rx={0.3} fill={kit(p.home)[0]} />
        <text x={1.6} y={2.45} className="tag-num">{p.number}</text>
        <text x={4.3} y={2.45} className="tag-name">{p.short_name}</text>
        {extra && <text x={p.short_name.length * 1.3 + 5.4} y={2.45} className="tag-speed">{extra}</text>}
      </g>
    );
  };

  return (
    <div className={`pitch-wrap cam-${camera} ${dimmed ? "dimmed" : ""}`}>
      <svg className="pitch" viewBox="-4 -4 113 76" preserveAspectRatio="xMidYMid meet">
        <defs>
          <pattern id="mow" width={10.5} height={68} patternUnits="userSpaceOnUse">
            <rect width={5.25} height={68} fill="#2a7a3f" />
            <rect x={5.25} width={5.25} height={68} fill="#2f8445" />
          </pattern>
          <radialGradient id="vignette" cx="50%" cy="45%" r="70%">
            <stop offset="55%" stopColor="#000" stopOpacity={0} />
            <stop offset="100%" stopColor="#000" stopOpacity={0.45} />
          </radialGradient>
          <filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="2.2" numOctaves={2} seed={3} /><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .07 0" /></filter>
          <filter id="glow"><feGaussianBlur stdDeviation={0.7} result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
          <filter id="soft"><feGaussianBlur stdDeviation={0.35} /></filter>
          <marker id="arrow" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={4} markerHeight={4} orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#fff" /></marker>
          <marker id="arrow-gold" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={4} markerHeight={4} orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#ffd34d" /></marker>
        </defs>

        <rect x={-4} y={-4} width={113} height={76} fill="#236b36" />
        <rect x={0} y={0} width={105} height={68} fill="url(#mow)" />
        <rect x={-4} y={-4} width={113} height={76} filter="url(#grain)" />
        <Lines />
        <rect x={-4} y={-4} width={113} height={76} fill="url(#vignette)" pointerEvents="none" />
        <text x={1.5} y={66.6} className="pitch-dir">{meta.home.short_name} attack →</text>

        {trail.map((e, i) => {
          const a = e.enriched.home_xy!, b = e.enriched.home_end_xy;
          if (!b) return null;
          return <line key={e.event.id} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={teamColor(e.event.team_id)} strokeWidth={0.35}
                       strokeDasharray={e.event.type === "carry" ? "0.9 0.7" : undefined} opacity={0.12 + (0.55 * (i + 1)) / trail.length} strokeLinecap="round" />;
        })}

        {spotlight && (
          <g className="spotlight">
            {spotlight.options.map((o, i) => <circle key={i} cx={o[0]} cy={o[1]} r={2.4} fill="rgba(255,255,255,.08)" stroke="rgba(255,255,255,.55)" strokeWidth={0.25} />)}
            <line x1={spotlight.from[0]} y1={spotlight.from[1]} x2={spotlight.to[0]} y2={spotlight.to[1]}
                  stroke={spotlight.kind === "brave_pass" ? "#ffd34d" : "#fff"} strokeWidth={0.6}
                  markerEnd={`url(#${spotlight.kind === "brave_pass" ? "arrow-gold" : "arrow"})`} filter="url(#glow)" />
            {spotlight.best && (
              <g>
                <line x1={spotlight.from[0]} y1={spotlight.from[1]} x2={spotlight.best.xy[0]} y2={spotlight.best.xy[1]}
                      stroke="#ffd34d" strokeWidth={0.65} strokeDasharray="1.6 1" markerEnd="url(#arrow-gold)" filter="url(#glow)" className="ghost" />
                <circle cx={spotlight.best.xy[0]} cy={spotlight.best.xy[1]} r={2.6} fill="none" stroke="#ffd34d" strokeWidth={0.35} className="pulse-ring" />
                <text x={Math.min(88, Math.max(17, spotlight.best.xy[0]))} y={Math.max(4, spotlight.best.xy[1] - 4)} className="ghost-label">better option: {spotlight.best.name}</text>
              </g>
            )}
          </g>
        )}

        {frame?.map(([pid, x, y]) => {
          const p = roster.get(pid);
          if (!p) return null;
          const [main, trim] = kit(p.home);
          const gk = p.role === "GK";
          const isCarrier = pid === carrierId, isFocus = pid === focusPlayer;
          return (
            <g key={pid} className={`player ${isCarrier ? "carrier" : ""}`} style={{ transform: `translate(${x}px, ${y}px)`, transition: move }}>
              <ellipse cx={0.5} cy={1.9} rx={1.9} ry={0.7} fill="rgba(0,0,0,.35)" filter="url(#soft)" />
              {(isCarrier || isFocus) && <circle r={2.7} fill="none" stroke={isFocus ? "#7df9ff" : "#fff"} strokeWidth={0.28} className={isFocus ? "focus-ring" : "carrier-ring"} />}
              <g transform={p.home ? "" : "rotate(180)"}>
                <path d={SHIRT} fill={gk ? (p.home ? "#c6f432" : "#ff8fd3") : main} stroke={gk ? "#111" : trim} strokeWidth={0.22} strokeLinejoin="round" />
              </g>
              <text y={0.75} className="shirt-num" fill={gk ? "#111" : trim}>{p.number}</text>
            </g>
          );
        })}

        {ball && (
          <g style={{ transform: `translate(${ball[0]}px, ${ball[1]}px)`, transition: move }}>
            <ellipse cx={0.45} cy={0.9} rx={0.9} ry={0.4} fill="rgba(0,0,0,.4)" filter="url(#soft)" />
            <circle r={0.85} fill="#fff" stroke="#222" strokeWidth={0.15} filter="url(#glow)" />
            <path d="M-0.3,-0.25 L0.05,-0.45 L0.35,-0.2 L0.2,0.15 L-0.2,0.15 Z" fill="#333" />
          </g>
        )}

        {frame && carrierId && (() => {
          const f = frame.find(([pid]) => pid === carrierId);
          return f ? tag(carrierId, f[1], f[2], speedTag?.data.player_id === carrierId ? `${speedTag.data.speed_kmh} km/h` : undefined) : null;
        })()}
        {frame && focusPlayer && focusPlayer !== carrierId && (() => {
          const f = frame.find(([pid]) => pid === focusPlayer);
          return f ? tag(focusPlayer, f[1], f[2], undefined, "rgba(10,60,70,.92)") : null;
        })()}
        {spotlight && <text x={spotlight.from[0]} y={spotlight.from[1] - 7.5} className="spot-label">{spotlight.label}</text>}
      </svg>
    </div>
  );
}
