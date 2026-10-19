import type { Meta, Persona, Story } from "../types";
import Crest from "./Crest";

interface Props {
  story: Story;
  persona: Persona;
  lang: string;
  meta: Meta;
}

export function textFor(story: Story, persona: Persona, lang: string) {
  const p = persona === "metric" ? "casual" : persona;
  const versions = story.texts[p] ?? story.texts["casual"] ?? Object.values(story.texts)[0];
  return versions?.[lang] ?? versions?.en;
}

export default function StoryCard({ story, persona, lang, meta }: Props) {
  const t = textFor(story, persona, lang);
  if (!t) return null;
  const team = story.team_id === meta.home.id ? meta.home : story.team_id === meta.away.id ? meta.away : null;
  return (
    <div className={`story story-${story.airtime}`} style={{ ["--team" as any]: team?.colors[0] ?? "#7df9ff" }}>
      <div className="story-top">
        {team && <Crest team={team} size={16} />}
        <span className="story-clock">{story.clock}</span>
        <span className="story-type">{story.type.replace("_", " ")}</span>
        <span className={`story-badge ${t.source}`}>{t.source === "ai" ? "AI · verified" : "Match facts"}</span>
        {lang !== "en" && !t.translated && <span className="story-badge muted">EN</span>}
      </div>
      <div className="story-headline">{t.headline}</div>
      <div className="story-timer" key={story.moment_id} style={{ animationDuration: `${story.airtime === "feature" ? 15 : 9}s` }} />
      <div className="story-body">{t.body}</div>
      {persona === "analyst" && story.explanation && (
        <div className="story-why"><b>Why it matters · {story.explanation.pattern}</b> {story.explanation.why_it_matters}</div>
      )}
    </div>
  );
}
