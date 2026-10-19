import type { Meta, TeamSummary } from "../types";
import Crest from "./Crest";

interface Props {
  meta: Meta;
  score: Record<string, number>;
  clock: string;
  home: TeamSummary | null;
  away: TeamSummary | null;
  favoriteClub: string | null;
}

export default function ScoreBug({ meta, score, clock, home, away, favoriteClub }: Props) {
  const side = (t: Meta["home"], s: TeamSummary | null) => (
    <div className={`sb-team ${favoriteClub === t.id ? "fav" : ""}`}>
      <Crest team={t} size={20} />
      <span className="sb-name">{t.short_name}</span>
      <span className="sb-score">{score[t.id] ?? 0}</span>
      {s && <span className="sb-sub">xG {s.xg.toFixed(2)}</span>}
    </div>
  );
  return (
    <div className="scorebug">
      {side(meta.home, home)}
      <div className="sb-clock">{clock}</div>
      {side(meta.away, away)}
      {home && away && (
        <div className="sb-poss">
          <div style={{ width: `${home.possession * 100}%`, background: meta.home.colors[0] }} />
          <div style={{ width: `${away.possession * 100}%`, background: meta.away.colors[0] }} />
        </div>
      )}
    </div>
  );
}
