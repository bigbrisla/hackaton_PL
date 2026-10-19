import type { Meta, Overlay, Persona } from "../types";

export type Metric = "speed" | "difficulty" | "shot_speed" | "chaos";

interface Props {
  overlays: Overlay[];
  meta: Meta;
  persona: Persona;
  metric: Metric;
  now: number; // performance.now()
  speed: number;
}

const VISIBLE: Record<Persona, Set<string>> = {
  casual: new Set(["goal_flash", "shot_card"]),
  analyst: new Set(["goal_flash", "shot_card", "pass_quality", "distance_tag"]),
  accessibility: new Set(["goal_flash"]),
  player: new Set(["goal_flash", "shot_card", "pass_quality", "distance_tag"]),
  metric: new Set(["goal_flash"]),
};
const METRIC_TEMPLATE: Record<Metric, string> = { speed: "speed_tag", difficulty: "pass_quality", shot_speed: "shot_card", chaos: "chaos_meter" };

export function isVisible(o: Overlay, now: number, speed: number) {
  const dur = Math.min(7000, Math.max(3000, ((o.out_ts - o.in_ts) / speed) * 1000));
  return now - (o.shownAt ?? 0) < dur;
}

export default function Overlays({ overlays, meta, persona, metric, now, speed }: Props) {
  const allowed = new Set(VISIBLE[persona]);
  if (persona === "metric") allowed.add(METRIC_TEMPLATE[metric]);
  const live = overlays.filter((o) => allowed.has(o.template) && isVisible(o, now, speed));
  const byLayer = new Map<string, Overlay>();
  for (const o of live) {
    const cur = byLayer.get(o.layer);
    if (!cur || o.priority >= cur.priority) byLayer.set(o.layer, o);
  }
  const team = (id: string) => (id === meta.home.id ? meta.home : meta.away);

  return (
    <div className="overlays">
      {[...byLayer.values()].map((o) => {
        const d = o.data;
        switch (o.template) {
          case "goal_flash":
            return (
              <div key={o.overlay_id} className="ov ov-goal" style={{ ["--team" as any]: team(d.team_id).colors[0] }}>
                <div className="ov-goal-word">GOAL</div>
                <div className="ov-goal-who">{d.scorer}{d.assist ? <span> · assist {d.assist}</span> : null}</div>
                <div className="ov-goal-score">{meta.home.short_name} {d.score[meta.home.id]}–{d.score[meta.away.id]} {meta.away.short_name} · {d.clock}</div>
              </div>
            );
          case "shot_card":
            return (
              <div key={o.overlay_id} className="ov ov-card">
                <div className="ov-k">Shot · {d.player}</div>
                <div className="ov-big">{d.shot_speed_kmh}<small> km/h</small></div>
                {persona !== "casual" && <div className="ov-row"><span>xG {d.xg}</span><span>{d.distance_m} m</span><span>{d.outcome.replace("_", " ")}</span></div>}
              </div>
            );
          case "pass_quality":
            return (
              <div key={o.overlay_id} className="ov ov-card">
                <div className="ov-k">Pass · {d.player} → {d.receiver}</div>
                <div className="ov-big">{d.difficulty}<small>/100 difficulty</small></div>
                <div className="ov-row"><span>{d.length_m} m</span><span>{d.ball_speed_kmh} km/h</span><span>xT +{d.xt_added}</span></div>
                <div className="ov-meter"><div style={{ width: `${d.difficulty}%` }} /></div>
              </div>
            );
          case "speed_tag":
            return (
              <div key={o.overlay_id} className="ov ov-card">
                <div className="ov-k">Top speed · {d.player}</div>
                <div className="ov-big">{d.speed_kmh}<small> km/h</small></div>
              </div>
            );
          case "distance_tag":
            return (
              <div key={o.overlay_id} className="ov ov-chip">{d.player} passes {d.distance_km} km</div>
            );
          case "chaos_meter":
            return (
              <div key={o.overlay_id} className="ov ov-card">
                <div className="ov-k">Chaos Index</div>
                <div className="ov-big">{d.chaos}<small> /100</small></div>
              </div>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}
