import type { Team } from "../types";

/** Generated club crest: a shield in the club colours with its initials (clubs are fictional). */
export default function Crest({ team, size = 22 }: { team: Team; size?: number }) {
  const initials = team.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const [main, trim] = team.colors;
  return (
    <svg width={size} height={size * 1.15} viewBox="0 0 20 23" className="crest" aria-label={team.name}>
      <path d="M10,0.8 L19,3.5 L19,11 Q19,18.5 10,22.2 Q1,18.5 1,11 L1,3.5 Z" fill={main} stroke={trim} strokeWidth={1.4} />
      <path d="M10,0.8 L19,3.5 L19,11 Q19,18.5 10,22.2 Z" fill="rgba(0,0,0,.18)" />
      <text x={10} y={14.2} textAnchor="middle" fontSize={7.6} fontWeight={900} fill={trim} fontFamily="Inter, sans-serif">{initials}</text>
    </svg>
  );
}
