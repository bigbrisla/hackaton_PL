import type { Moment, Trace } from "../types";

const ORDER = ["analyst", "tactician", "storyteller", "verifier", "localizer", "producer"];
const STATUS_CLASS: Record<string, string> = {
  ok: "ok", approved: "ok", scheduled: "ok", rejected: "bad", fallback: "warn", replaced_with_facts: "warn",
  explanation_replaced: "warn", dropped_stale: "muted",
};

interface Props {
  traces: Trace[];
  moments: Moment[];
  model: string;
}

export default function Newsroom({ traces, moments, model }: Props) {
  const byMoment = new Map<string, Trace[]>();
  for (const t of traces) byMoment.set(t.moment_id, [...(byMoment.get(t.moment_id) ?? []), t]);
  const titles = new Map(moments.map((m) => [m.moment_id, m]));
  const rows = [...byMoment.entries()].slice(-5).reverse();

  return (
    <div className="newsroom">
      <div className="panel-title">
        Agent newsroom <span className="model-pill">{model === "foundry" ? "Microsoft Foundry · gpt-5-mini" : "offline fallback"}</span>
      </div>
      {rows.length === 0 && <div className="muted small">Waiting for the first key moment…</div>}
      {rows.map(([id, ts]) => {
        const m = titles.get(id);
        const rejected = ts.find((t) => t.status === "rejected");
        return (
          <div key={id} className="nr-row">
            <div className="nr-head"><span className="nr-clock">{m?.clock}</span> {m?.title ?? id}</div>
            <div className="nr-chips">
              {ts.filter((t) => ORDER.includes(t.agent)).map((t, i) => (
                <span key={i} className={`chip ${STATUS_CLASS[t.status] ?? ""}`} title={t.detail}>
                  {t.agent}{t.status === "rejected" ? " ✗" : t.status === "fallback" ? " ↺" : ""}
                  {t.ms > 0 && <small> {(t.ms / 1000).toFixed(1)}s</small>}
                </span>
              ))}
              {ts.length < 6 && !ts.some((t) => t.agent === "producer") && <span className="chip working">working…</span>}
            </div>
            {rejected && <div className="nr-reject">Verifier sent it back: {rejected.detail}</div>}
          </div>
        );
      })}
    </div>
  );
}
