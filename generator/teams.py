"""Fictional clubs and deterministic rosters.

Rosters are seeded by club id, so the same club always fields the same players
across matches (needed later for favourite-player modes and season memory).
"""

from __future__ import annotations

import random
import zlib
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TacticalDNA:
    possession: float  # patience: prefers short, safe circulation
    pressing: float  # intensity and height of the press
    verticality: float  # appetite for forward passes
    width: float  # how wide the shape is in possession
    tempo: float  # speed of circulation


@dataclass
class Player:
    id: str
    name: str
    short_name: str
    number: int
    position: str
    role: str  # GK, CB, FB, DM, CM, AM, W, ST
    nationality: str
    passing: int
    vision: int
    finishing: int
    pace: int
    tackling: int
    composure: int
    stamina: int
    base_x: float
    base_y: float


@dataclass
class Team:
    id: str
    name: str
    short_name: str
    colors: tuple[str, str]
    formation: str
    dna: TacticalDNA
    quality: int
    players: list[Player]

    def to_dict(self) -> dict:
        return asdict(self)


# (position, role, base_x, base_y) of the in-possession shape when the ball is at midfield
FORMATIONS: dict[str, list[tuple[str, str, float, float]]] = {
    "4-3-3": [
        ("GK", "GK", 6, 34), ("RB", "FB", 38, 9), ("RCB", "CB", 28, 23), ("LCB", "CB", 28, 45),
        ("LB", "FB", 38, 59), ("CDM", "DM", 45, 34), ("RCM", "CM", 56, 22), ("LCM", "CM", 56, 46),
        ("RW", "W", 73, 9), ("ST", "ST", 79, 34), ("LW", "W", 73, 59),
    ],
    "4-2-3-1": [
        ("GK", "GK", 6, 34), ("RB", "FB", 37, 9), ("RCB", "CB", 27, 23), ("LCB", "CB", 27, 45),
        ("LB", "FB", 37, 59), ("RDM", "DM", 44, 26), ("LDM", "DM", 44, 42), ("RAM", "W", 68, 12),
        ("CAM", "AM", 66, 34), ("LAM", "W", 68, 56), ("ST", "ST", 80, 34),
    ],
    "3-5-2": [
        ("GK", "GK", 6, 34), ("RCB", "CB", 30, 18), ("CB", "CB", 26, 34), ("LCB", "CB", 30, 50),
        ("RWB", "FB", 56, 6), ("RCM", "CM", 53, 24), ("CDM", "DM", 44, 34), ("LCM", "CM", 53, 44),
        ("LWB", "FB", 56, 62), ("RST", "ST", 78, 27), ("LST", "ST", 78, 41),
    ],
}

CLUBS = [
    dict(id="NBR", name="Northbridge Athletic", short="Northbridge", colors=("#C8102E", "#FFFFFF"),
         formation="4-3-3", quality=80, dna=TacticalDNA(0.75, 0.80, 0.45, 0.70, 0.70)),
    dict(id="HRV", name="Harbourside Rovers", short="Harbourside", colors=("#1D428A", "#F2C94C"),
         formation="4-2-3-1", quality=77, dna=TacticalDNA(0.35, 0.45, 0.80, 0.55, 0.65)),
    dict(id="KMT", name="Kingsmoor Town", short="Kingsmoor", colors=("#2E7D32", "#111111"),
         formation="3-5-2", quality=74, dna=TacticalDNA(0.50, 0.65, 0.60, 0.85, 0.55)),
    dict(id="ASV", name="Ashvale United", short="Ashvale", colors=("#6A1B9A", "#E0E0E0"),
         formation="4-2-3-1", quality=76, dna=TacticalDNA(0.65, 0.30, 0.35, 0.50, 0.40)),
    dict(id="CLW", name="Calder Wharf FC", short="Calder Wharf", colors=("#F57C00", "#0D47A1"),
         formation="4-3-3", quality=72, dna=TacticalDNA(0.40, 0.70, 0.70, 0.60, 0.80)),
    dict(id="SWC", name="Saltwick City", short="Saltwick", colors=("#00838F", "#FFFFFF"),
         formation="3-5-2", quality=75, dna=TacticalDNA(0.55, 0.55, 0.50, 0.75, 0.60)),
]

NAMES: dict[str, tuple[list[str], list[str]]] = {
    "ENG": (["Jack", "Callum", "Reece", "Owen", "Harvey", "Mason"], ["Ashworth", "Pembrook", "Hollis", "Tranter", "Whitcombe", "Fenley"]),
    "ESP": (["Iker", "Álvaro", "Unai", "Dani", "Pablo", "Marcos"], ["Larrea", "Olmedo", "Garmendia", "Ruano", "Echeverri", "Salcedo"]),
    "BRA": (["Thiago", "Caio", "Davi", "Rafael", "Matheus", "Gustavo"], ["Albuquerque", "Moreira", "Teixeira", "Brandão", "Peixoto", "Siqueira"]),
    "FRA": (["Théo", "Malo", "Enzo", "Yanis", "Bastien", "Lucas"], ["Delacroix", "Morvan", "Ferrand", "Lemaire", "Chauvet", "Rousselot"]),
    "NGA": (["Chidi", "Emeka", "Tunde", "Ifeanyi", "Segun", "Obinna"], ["Okafor", "Adeyemi", "Nwosu", "Balogun", "Eze", "Ogunleye"]),
    "JPN": (["Haruto", "Sota", "Ren", "Daiki", "Kaito", "Yuma"], ["Takahara", "Morinaga", "Ishikawa", "Nakajo", "Fujiwara", "Kurosawa"]),
    "GER": (["Lukas", "Jonas", "Felix", "Nico", "Moritz", "Paul"], ["Brandt", "Kessler", "Hoffstedt", "Wagner", "Lindemann", "Reuter"]),
    "ITA": (["Lorenzo", "Matteo", "Davide", "Federico", "Andrea", "Giulio"], ["Ferraresi", "Bonvicini", "Castellani", "Moretti", "Sartori", "Galletti"]),
    "NED": (["Daan", "Sem", "Milan", "Thijs", "Jesse", "Bram"], ["de Vries", "van Leeuwen", "Bakker", "Hendriks", "Visser", "Jansma"]),
    "KOR": (["Min-jun", "Seo-jun", "Ji-ho", "Do-yun", "Hyun-woo", "Jae-won"], ["Park", "Seo", "Han", "Yoon", "Kang", "Jeon"]),
    "GHA": (["Kwame", "Kofi", "Yaw", "Kwabena", "Nana", "Kojo"], ["Mensah", "Asante", "Owusu", "Boateng", "Appiah", "Darko"]),
    "NOR": (["Sander", "Emil", "Magnus", "Tobias", "Henrik", "Aksel"], ["Halvorsen", "Strand", "Lunde", "Myklebust", "Berge", "Solheim"]),
}

ROLE_BOOST = {
    "GK": dict(passing=-8, finishing=-40, pace=-15, tackling=-30),
    "CB": dict(tackling=10, finishing=-15, passing=-2),
    "FB": dict(pace=8, tackling=4, finishing=-10),
    "DM": dict(tackling=8, passing=5, vision=2, finishing=-8),
    "CM": dict(passing=8, vision=6, stamina=5),
    "AM": dict(vision=10, passing=6, finishing=4, tackling=-10),
    "W": dict(pace=12, finishing=4, tackling=-12),
    "ST": dict(finishing=12, composure=5, tackling=-15, passing=-4),
}

ATTRS = ("passing", "vision", "finishing", "pace", "tackling", "composure", "stamina")


def _stat(rng: random.Random, quality: int, boost: int) -> int:
    return max(25, min(97, round(rng.gauss(quality + boost, 5))))


def build_team(club: dict) -> Team:
    rng = random.Random(zlib.crc32(club["id"].encode()))
    used: set[str] = set()
    players = []
    numbers = rng.sample(range(2, 40), 10)
    for i, (pos, role, bx, by) in enumerate(FORMATIONS[club["formation"]]):
        while True:
            nat = rng.choice(list(NAMES))
            first, last = rng.choice(NAMES[nat][0]), rng.choice(NAMES[nat][1])
            if last not in used:
                used.add(last)
                break
        boosts = ROLE_BOOST[role]
        stats = {a: _stat(rng, club["quality"], boosts.get(a, 0)) for a in ATTRS}
        players.append(Player(
            id=f"{club['id']}-{i + 1:02d}", name=f"{first} {last}", short_name=last,
            number=1 if role == "GK" else numbers[i - 1], position=pos, role=role,
            nationality=nat, base_x=bx, base_y=by, **stats,
        ))
    return Team(id=club["id"], name=club["name"], short_name=club["short"], colors=club["colors"],
                formation=club["formation"], dna=club["dna"], quality=club["quality"], players=players)


def all_teams() -> list[Team]:
    return [build_team(c) for c in CLUBS]
