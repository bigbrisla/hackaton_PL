"""Structured contracts passed between agents (all model outputs are schema-validated)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Persona = Literal["casual", "analyst", "accessibility", "player"]
PERSONAS: tuple[Persona, ...] = ("casual", "analyst", "accessibility", "player")


class Brief(BaseModel):
    """Analyst: is this moment worth airing, from which angle, with which evidence."""

    newsworthy: Literal["skip", "brief", "feature"]
    angle: str = Field(description="One sentence: the story of this moment")
    key_points: list[str] = Field(description="2-4 factual points, numbers copied exactly from the evidence")
    focus_player: str | None = Field(default=None, description="Full name of the player the story is about")


class Explanation(BaseModel):
    """Tactician: why the moment matters."""

    pattern: Literal["control", "chaos", "pressure", "rhythm", "decision", "individual", "set_piece"]
    why_it_matters: str = Field(description="2-3 sentences explaining cause and consequence")
    confidence: Literal["low", "medium", "high"]


class PersonaText(BaseModel):
    persona: Persona
    headline: str = Field(min_length=1)
    body: str = Field(min_length=1)


class Story(BaseModel):
    """Storyteller: one text per persona, same facts."""

    texts: list[PersonaText]


class LocalizedText(BaseModel):
    persona: Persona
    lang: str
    headline: str
    body: str


class Localized(BaseModel):
    texts: list[LocalizedText]


class Verdict(BaseModel):
    ok: bool
    problems: list[str] = []
