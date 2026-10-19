export type XY = [number, number];

export interface Player {
  id: string;
  name: string;
  short_name: string;
  number: number;
  position: string;
  role: string;
  nationality: string;
}

export interface Team {
  id: string;
  name: string;
  short_name: string;
  colors: [string, string];
  formation: string;
  players: Player[];
}

export interface Meta {
  match_id: string;
  venue: string;
  referee: string;
  weather: string;
  home: Team;
  away: Team;
}

export interface MatchEvent {
  id: string;
  ts: number;
  minute: number;
  added_minute: number;
  type: string;
  team_id: string | null;
  player_id: string | null;
  outcome: string | null;
  attrs: Record<string, any>;
}

export interface Enriched {
  home_xy: XY | null;
  home_end_xy: XY | null;
  difficulty?: number;
  xt_added?: number;
  dva?: number;
  xg?: number;
  best_option?: { player_id: string; player: string; home_xy: XY; expected_value: number; success_prob: number };
  options_home_xy?: { player_id: string; home_xy: XY }[];
}

export interface Overlay {
  overlay_id: string;
  layer: string;
  template: string;
  in_ts: number;
  out_ts: number;
  priority: number;
  data: Record<string, any>;
  shownAt?: number;
}

export interface ChaosReading {
  chaos: number;
  state: "chaos" | "contested" | "control";
  control_side: "home" | "away";
  control_share: number;
  drivers: { factor: string; z: number; value: number }[];
}

export interface TeamSummary {
  team_id: string;
  name: string;
  goals: number;
  shots: number;
  shots_on_target: number;
  xg: number;
  possession: number;
  passes: number;
  pass_accuracy: number;
  pressures: number;
  xt: number;
}

export interface Moment {
  moment_id: string;
  type: string;
  priority: number;
  ts: number;
  clock: string;
  source_event: string;
  team_id: string | null;
  player_id: string | null;
  player: string | null;
  title: string;
  facts: Record<string, any>;
  where: { zone: string; home_xy: XY } | null;
  receivedAt?: number;
}

export type Persona = "casual" | "analyst" | "accessibility" | "player" | "metric";

export interface StoryText {
  headline: string;
  body: string;
  source: "ai" | "facts";
  translated: boolean;
}

export interface Story {
  moment_id: string;
  type: string;
  clock: string;
  ts: number;
  team_id: string | null;
  player_id: string | null;
  where: { zone: string; home_xy: XY } | null;
  aired: boolean;
  airtime: "skip" | "brief" | "feature";
  angle: string;
  explanation: { pattern: string; why_it_matters: string; confidence: string } | null;
  texts: Record<string, Record<string, StoryText>>;
  overlay: { layer: string; template: string; in_ts: number; out_ts: number; priority: number };
  cached?: boolean;
  receivedAt?: number;
}

export interface Trace {
  moment_id: string;
  agent: string;
  status: string;
  ms: number;
  detail: string;
}
