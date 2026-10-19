import type { ChaosReading, Meta, Moment } from "../types";

interface Props {
  history: { ts: number; chaos: number }[];
  chaos: ChaosReading | null;
  moments: Moment[];
  meta: Meta;
  now: number;
}

const W = 1000, H = 120, TREMOR = 88;
const FACTOR: Record<string, string> = {
  turnovers: "turnovers", completion: "loose passing", pressures: "pressing", ball_swing: "end-to-end play",
  balance: "contested ball", shots: "shots",
};

export default function Seismograph({ history, chaos, moments, meta, now }: Props) {
  const span = Math.max(97 * 60, now + 60);
  const x = (ts: number) => (ts / span) * W;
  const y = (c: number) => H - (c / 100) * H;
  const pts = history.map((h) => `${x(h.ts).toFixed(1)},${y(h.chaos).toFixed(1)}`);
  const line = pts.length ? `M${pts.join(" L")}` : "";
  const area = pts.length ? `${line} L${x(history[history.length - 1].ts)},${H} L${x(history[0].ts)},${H} Z` : "";
  const marks = moments.filter((m) => m.type === "goal" || m.type === "tremor");
  const state = chaos?.state ?? "contested";
  const controlTeam = chaos ? (chaos.control_side === "home" ? meta.home : meta.away) : null;

  return (
    <div className={`seismo state-${state}`}>
      <div className="seismo-head">
        <div className="seismo-title">
          <span className="dot" /> Chaos Index
        </div>
        <div className="seismo-value">{chaos?.chaos ?? "–"}</div>
        <div className="seismo-state">
          {state === "chaos" ? "Chaos" : state === "control" ? `${controlTeam?.short_name} in control` : "Contested"}
          {chaos && (
            <span className="seismo-drivers">
              {chaos.drivers.filter((d) => Math.abs(d.z) > 0.6).slice(0, 2)
                .map((d) => `${d.z > 0 ? "↑" : "↓"} ${FACTOR[d.factor] ?? d.factor}`).join(" · ")}
            </span>
          )}
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="seismo-chart">
        <defs>
          <linearGradient id="chaosfill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ff4d6d" stopOpacity={0.55} />
            <stop offset="55%" stopColor="#ffb703" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#2ec4b6" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        {[45 * 60, 90 * 60].map((t) => <line key={t} x1={x(t)} x2={x(t)} y1={0} y2={H} className="seismo-grid" />)}
        <line x1={0} x2={W} y1={y(TREMOR)} y2={y(TREMOR)} className="seismo-threshold" />
        <path d={area} fill="url(#chaosfill)" />
        <path d={line} className="seismo-line" />
        {marks.map((m) => (
          <g key={m.moment_id} transform={`translate(${x(m.ts)},0)`}>
            <line y1={0} y2={H} className={m.type === "goal" ? "mark-goal" : "mark-tremor"} />
            {m.type === "goal" && <circle cy={8} r={6} className="mark-goal-dot" />}
          </g>
        ))}
        {history.length > 0 && <circle cx={x(history[history.length - 1].ts)} cy={y(history[history.length - 1].chaos)} r={5} className="seismo-head-dot" />}
      </svg>
      <div className="seismo-axis"><span>0'</span><span>45'</span><span>90'</span></div>
    </div>
  );
}
