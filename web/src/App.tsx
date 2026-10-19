import { useEffect, useMemo, useRef, useState } from "react";
import { PulseAudio } from "./audio";
import Newsroom from "./components/Newsroom";
import Overlays, { isVisible, type Metric } from "./components/Overlays";
import Pitch, { type Spotlight } from "./components/Pitch";
import ScoreBug from "./components/ScoreBug";
import Seismograph from "./components/Seismograph";
import StoryCard, { textFor } from "./components/StoryCard";
import type { Persona, Story } from "./types";
import { useMatchStream } from "./useMatchStream";

const PERSONAS: { id: Persona; label: string; hint: string }[] = [
  { id: "casual", label: "Casual fan", hint: "the story, in plain words" },
  { id: "analyst", label: "Analyst", hint: "every metric, and why" },
  { id: "player", label: "Player focus", hint: "follow one player all match" },
  { id: "metric", label: "One metric", hint: "just the number you care about" },
  { id: "accessibility", label: "Eyes-free", hint: "the match as sound and voice" },
];
const LANGS = [{ id: "en", label: "EN" }, { id: "it", label: "IT" }, { id: "es", label: "ES" }, { id: "ja", label: "日本語" }];
const METRICS: { id: Metric; label: string }[] = [
  { id: "speed", label: "Top speed" }, { id: "difficulty", label: "Pass difficulty" },
  { id: "shot_speed", label: "Shot speed" }, { id: "chaos", label: "Chaos Index" },
];
const STORY_MS = { feature: 15000, brief: 9000, skip: 0 };

interface Fixture { match_id: string; home: string; away: string; venue: string }

// scenes can be reproduced exactly from the URL, e.g. ?autostart=1&from=78&speed=2&persona=analyst&lang=it
const Q = new URLSearchParams(location.search);

export default function App() {
  const { state, start, subscribe } = useMatchStream();
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [matchId, setMatchId] = useState(Q.get("match") ?? "NBR-HRV-7");
  const [startMinute, setStartMinute] = useState(Number(Q.get("from") ?? 76));
  const [speed, setSpeed] = useState(Number(Q.get("speed") ?? 2));
  const [persona, setPersona] = useState<Persona>((Q.get("persona") as Persona) ?? "casual");
  const [lang, setLang] = useState(Q.get("lang") ?? "en");
  const [favoriteClub, setFavoriteClub] = useState<string | null>(Q.get("club"));
  const [focusPlayer, setFocusPlayer] = useState<string | null>(Q.get("player"));
  const [metric, setMetric] = useState<Metric>((Q.get("metric") as Metric) ?? "speed");
  const [eyesClosed, setEyesClosed] = useState(false);
  const [camera, setCamera] = useState<"broadcast" | "tactical">((Q.get("cam") as "tactical") ?? "broadcast");
  const [now, setNow] = useState(performance.now());
  const [playerStats, setPlayerStats] = useState<Record<string, any> | null>(null);
  const audio = useRef(new PulseAudio());
  const settings = useRef({ persona, lang, eyesClosed });
  settings.current = { persona, lang, eyesClosed };

  useEffect(() => {
    fetch("/api/matches").then((r) => r.json()).then(setFixtures).catch(() => {});
    const t = setInterval(() => setNow(performance.now()), 200);
    return () => clearInterval(t);
  }, []);

  // sound and voice react to every message without re-rendering
  useEffect(() => subscribe((msg) => {
    const a = audio.current;
    if (!a.enabled) return;
    const home = state.meta?.home.id;
    if (msg.kind === "event" && msg.enriched?.home_xy && ["pass", "carry", "shot", "tackle", "interception"].includes(msg.event.type)) {
      a.tick(msg.enriched.home_xy[0], msg.event.team_id === home, msg.event.type === "shot");
    } else if (msg.kind === "state" && msg.chaos) {
      a.setChaos(msg.chaos.chaos);
    } else if (msg.kind === "moment" && msg.type === "goal") {
      a.crowd(msg.where?.home_xy ? msg.where.home_xy[0] / 52.5 - 1 : 0);
    } else if (msg.kind === "story" && msg.aired) {
      const s = settings.current;
      if (s.persona === "accessibility" || s.eyesClosed) {
        const t = textFor(msg as Story, "accessibility", s.lang);
        const pan = msg.where?.home_xy ? msg.where.home_xy[0] / 52.5 - 1 : 0;
        if (t) a.say(`${t.headline}. ${t.body}`, s.lang, pan);
      }
    }
  }), [subscribe, state.meta]);

  useEffect(() => {
    if (persona !== "player" || !focusPlayer || !state.sessionId) return setPlayerStats(null);
    const load = () => fetch(`/api/sessions/${state.sessionId}/players/${focusPlayer}`).then((r) => r.ok ? r.json() : null).then(setPlayerStats).catch(() => {});
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [persona, focusPlayer, state.sessionId]);

  const kickOff = () => {
    const langs = ["en", "it", "es", "ja"];  // fixed set: every market is ready, and cached stories always match
    start({ matchId, speed, startMinute, langs, focusPlayer });
  };

  useEffect(() => {
    if (Q.get("autostart")) kickOff();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleSound = () => (audio.current.enabled ? audio.current.disable() : audio.current.enable());
  const closeEyes = () => {
    audio.current.enable();
    setEyesClosed((v) => !v);
  };

  const meta = state.meta;
  const roster = meta ? [...meta.home.players.map((p) => ({ ...p, team: meta.home.short_name })), ...meta.away.players.map((p) => ({ ...p, team: meta.away.short_name }))] : [];

  const story = useMemo(() => {
    const relevant = (s: Story) =>
      s.aired && (persona !== "player" || !focusPlayer || s.player_id === focusPlayer || s.type === "goal" || s.type === "recap")
      && (!favoriteClub || s.airtime === "feature" || s.team_id === favoriteClub || !s.team_id);
    return [...state.stories].reverse().find((s) => relevant(s) && now - (s.receivedAt ?? 0) < STORY_MS[s.airtime]);
  }, [state.stories, now, persona, focusPlayer, favoriteClub]);

  const spotlight = useMemo<Spotlight | null>(() => {
    const m = [...state.moments].reverse().find((x) => (x.type === "missed_option" || x.type === "brave_pass") && now - (x.receivedAt ?? 0) < 6500);
    if (!m || persona === "casual" || persona === "accessibility") return null;
    const ev = state.events.find((e) => e.event.id === m.source_event);
    if (!ev?.enriched.home_xy || !ev.enriched.home_end_xy) return null;
    const best = ev.enriched.best_option;
    return {
      kind: m.type as Spotlight["kind"], from: ev.enriched.home_xy, to: ev.enriched.home_end_xy,
      best: m.type === "missed_option" && best ? { xy: best.home_xy, name: best.player } : undefined,
      options: (ev.enriched.options_home_xy ?? []).map((o) => o.home_xy),
      label: m.type === "missed_option" ? `Sliding doors · DVA ${ev.enriched.dva}` : `Brave pass · difficulty ${ev.enriched.difficulty}`,
    };
  }, [state.moments, state.events, now, persona]);

  const recap = state.stories.find((s) => s.type === "recap" && s.clock.startsWith("90"));
  const recapMoment = state.moments.find((m) => m.type === "recap" && m.title === "Full time");
  const metricValue = useMemo(() => {
    if (persona !== "metric") return null;
    if (metric === "chaos") return state.chaos ? { v: state.chaos.chaos, unit: "/100", who: state.chaos.state } : null;
    const tpl = { speed: "speed_tag", difficulty: "pass_quality", shot_speed: "shot_card" }[metric];
    const key = { speed: "speed_kmh", difficulty: "difficulty", shot_speed: "shot_speed_kmh" }[metric];
    const all = state.overlays.filter((o) => o.template === tpl);
    const last = all[all.length - 1];
    const best = all.reduce((b, o) => (!b || o.data[key] > b.data[key] ? o : b), null as (typeof all)[number] | null);
    return last ? { v: last.data[key], unit: metric === "difficulty" ? "/100" : "km/h", who: last.data.player, best: best?.data[key], bestWho: best?.data.player, fresh: isVisible(last, now, speed) } : null;
  }, [persona, metric, state.overlays, state.chaos, now, speed]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">◉</span> Pulse <span className="brand-sub">one match, a million broadcasts</span></div>
        <div className="controls">
          <select value={matchId} onChange={(e) => setMatchId(e.target.value)}>
            {(fixtures.length ? fixtures : [{ match_id: "NBR-HRV-7", home: "Northbridge Athletic", away: "Harbourside Rovers", venue: "" }]).map((f) => (
              <option key={f.match_id} value={f.match_id}>{f.home} v {f.away}</option>
            ))}
          </select>
          <label>from <input type="number" min={0} max={90} value={startMinute} onChange={(e) => setStartMinute(+e.target.value)} />'</label>
          <select value={speed} onChange={(e) => setSpeed(+e.target.value)}>
            {[1, 2, 4, 8, 20].map((s) => <option key={s} value={s}>{s}× speed</option>)}
          </select>
          <button className="primary" onClick={kickOff}>{state.status === "live" ? "Restart" : "Kick off"}</button>
          <button onClick={toggleSound} className={audio.current.enabled ? "on" : ""}>🔊 Sound</button>
        </div>
        <div className="synthetic">Synthetic match · fictional clubs</div>
      </header>

      <main className="layout">
        <section className="stage-col">
          <div className={`stage ${eyesClosed ? "eyes-closed" : ""}`}>
            {meta ? (
              <>
                <Pitch meta={meta} events={state.events} frame={state.frame} overlays={state.overlays} spotlight={spotlight}
                       focusPlayer={focusPlayer} camera={camera} speed={speed} dimmed={eyesClosed} />
                {!eyesClosed && (
                  <button className="cam-toggle" onClick={() => setCamera(camera === "broadcast" ? "tactical" : "broadcast")}>
                    {camera === "broadcast" ? "◫ Tactical view" : "🎥 Broadcast cam"}
                  </button>
                )}
                <ScoreBug meta={meta} score={state.score} clock={state.clock} home={state.home} away={state.away} favoriteClub={favoriteClub} />
                {!eyesClosed && <Overlays overlays={state.overlays} meta={meta} persona={persona} metric={metric} now={now} speed={speed} />}
                {story && !eyesClosed && <StoryCard story={story} persona={persona} lang={lang} meta={meta} />}
                {persona === "metric" && metricValue && !eyesClosed && (
                  <div className="metric-hud">
                    <div className="mh-label">{METRICS.find((m) => m.id === metric)?.label}</div>
                    <div className={`mh-value ${metricValue.fresh ? "fresh" : ""}`}>{metricValue.v}<small>{metricValue.unit}</small></div>
                    <div className="mh-who">{metricValue.who}</div>
                    {metricValue.best !== undefined && <div className="mh-best">match best {metricValue.best} · {metricValue.bestWho}</div>}
                  </div>
                )}
                {eyesClosed && (
                  <div className="eyes-layer">
                    <div className="eyes-pulse" style={{ animationDuration: `${60 / (50 + (state.chaos?.chaos ?? 50) * 0.8)}s` }} />
                    <div className="eyes-caption">{story ? textFor(story, "accessibility", lang)?.body : "Listening to the match…"}</div>
                  </div>
                )}
                {recap && !eyesClosed && recapMoment && (
                  <div className="recap">
                    <div className="recap-k">Full time · automated recap</div>
                    <div className="recap-h">{textFor(recap, persona, lang)?.headline}</div>
                    <div className="recap-b">{textFor(recap, persona, lang)?.body}</div>
                    <div className="recap-grid">
                      {(["home", "away"] as const).map((side) => {
                        const t = recapMoment.facts[side];
                        return (
                          <div key={side}>
                            <b>{t.name} {t.goals}</b>
                            <span>xG {t.xg} · shots {t.shots} · possession {Math.round(t.possession * 100)}% · passes {Math.round(t.pass_accuracy * 100)}%</span>
                          </div>
                        );
                      })}
                    </div>
                    <div className="recap-heroes">Hidden heroes: {recapMoment.facts.leaders.hidden_heroes.join(", ")}</div>
                  </div>
                )}
              </>
            ) : (
              <div className="splash">
                <div className="splash-title">Every match, made for every fan.</div>
                <div className="splash-sub">Pick a fixture and kick off. Everything you see is computed live from synthetic match events.</div>
              </div>
            )}
          </div>
          {meta && <Seismograph history={state.chaosHistory} chaos={state.chaos} moments={state.moments} meta={meta} now={state.now} />}
        </section>

        <aside className="sidebar">
          <div className="panel">
            <div className="panel-title">Make it yours</div>
            <div className="personas">
              {PERSONAS.map((p) => (
                <button key={p.id} className={`persona ${persona === p.id ? "active" : ""}`} onClick={() => { setPersona(p.id); if (p.id === "accessibility") audio.current.enable(); }}>
                  <b>{p.label}</b><span>{p.hint}</span>
                </button>
              ))}
            </div>
            <div className="row">
              {LANGS.map((l) => <button key={l.id} className={`pill ${lang === l.id ? "active" : ""}`} onClick={() => setLang(l.id)}>{l.label}</button>)}
            </div>
            {meta && (
              <div className="row">
                <select value={favoriteClub ?? ""} onChange={(e) => setFavoriteClub(e.target.value || null)}>
                  <option value="">Favourite club…</option>
                  <option value={meta.home.id}>{meta.home.name}</option>
                  <option value={meta.away.id}>{meta.away.name}</option>
                </select>
                <select value={focusPlayer ?? ""} onChange={(e) => setFocusPlayer(e.target.value || null)}>
                  <option value="">Favourite player…</option>
                  {roster.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.team}</option>)}
                </select>
              </div>
            )}
            {persona === "metric" && (
              <div className="row">
                {METRICS.map((m) => <button key={m.id} className={`pill ${metric === m.id ? "active" : ""}`} onClick={() => setMetric(m.id)}>{m.label}</button>)}
              </div>
            )}
            {persona === "accessibility" && (
              <button className={`eyes-btn ${eyesClosed ? "active" : ""}`} onClick={closeEyes}>
                {eyesClosed ? "Open your eyes" : "Close your eyes: hear the match"}
              </button>
            )}
          </div>

          {persona === "player" && playerStats && (
            <div className="panel player-card">
              <div className="panel-title">{playerStats.name} · #{playerStats.number} {playerStats.position}</div>
              <div className="pc-grid">
                {[["Touches", playerStats.touches], ["Pass acc.", `${Math.round(playerStats.pass_accuracy * 100)}%`],
                  ["Avg pass diff.", playerStats.avg_pass_difficulty], ["Threat (xT)", playerStats.xt_added],
                  ["Decisions", `${Math.round(playerStats.decision_quality * 100)}% best`], ["Shots / xG", `${playerStats.shots} / ${playerStats.xg}`],
                  ["Distance", `${playerStats.distance_km} km`], ["Top speed", `${playerStats.top_speed_kmh} km/h`]].map(([k, v]) => (
                  <div key={k as string}><span>{k}</span><b>{v}</b></div>
                ))}
              </div>
            </div>
          )}

          <div className="panel"><Newsroom traces={state.traces} moments={state.moments} model={state.model} /></div>
        </aside>
      </main>
    </div>
  );
}
