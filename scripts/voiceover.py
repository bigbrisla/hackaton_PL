"""Generate the demo video voice-over with Azure AI Speech (keyless, same resource as the app).

    uv run python -m scripts.voiceover [--voice en-GB-RyanNeural] [--out video]

Writes one mp3 per scene plus voiceover.mp3, a single track with every line placed at its scene start
(docs/VIDEO_SCRIPT.md), and prints each line's duration against its slot.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

import httpx
from dotenv import load_dotenv

from engine.speech import _bearer

# (start s, end s, text); keep in sync with docs/VIDEO_SCRIPT.md
SCENES = [
    (0.5, 14, "This fan can't see the match. Every touch is placed in stereo where it happens, "
              "the heartbeat is the game's chaos, and the goal is described as it happens. This is Pulse."),
    (14, 32, "Pulse turns a live feed of synthetic match events into explainable intelligence. "
             "Our Chaos Index measures control versus chaos every few seconds. "
             "Here it hit 96, a tremor, two minutes before the goal."),
    (32, 50, "Every pass is scored against every option the passer had. "
             "Decision Value Added shows the road not taken: the pass to Asante was worth ten times more."),
    (50, 72, "Same facts, genuinely different experiences: a casual fan, an analyst, someone following one player, "
             "someone who only cares about one number. In any language."),
    (72, 96, "Behind every card, six agents on Microsoft Foundry, orchestrated with Microsoft Agent Framework. "
             "The analyst gathers evidence through our MCP server; the verifier traces every number and name "
             "back to the engine and sends drafts back when they don't match. In this match it caught twelve. "
             "Live stories take about twenty seconds; this demo replays them from cache."),
    (96, 115, "At full time, the recap writes itself. One match, a million broadcasts: "
              "every match, made for every fan."),
]


async def speak(client: httpx.AsyncClient, text: str, voice: str, rate: str) -> bytes:
    lang = "-".join(voice.split("-")[:2])
    ssml = (f"<speak version='1.0' xml:lang='{lang}'><voice name='{voice}'>"
            f"<prosody rate='{rate}'>{escape(text)}</prosody></voice></speak>")
    res = await client.post(
        f"https://{os.environ['AZURE_SPEECH_REGION']}.tts.speech.microsoft.com/cognitiveservices/v1",
        content=ssml.encode(),
        headers={"Authorization": f"Bearer {await _bearer()}", "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "audio-48khz-192kbitrate-mono-mp3", "User-Agent": "pulse"})
    res.raise_for_status()
    return res.content


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout)


async def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="en-GB-RyanNeural")
    ap.add_argument("--rate", default="+0%")
    ap.add_argument("--out", default="video")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(exist_ok=True)

    async with httpx.AsyncClient(timeout=30) as client:
        clips = await asyncio.gather(*(speak(client, text, args.voice, args.rate) for _, _, text in SCENES))
    paths = []
    for i, ((start, end, _), audio) in enumerate(zip(SCENES, clips), 1):
        path = out / f"scene{i}.mp3"
        path.write_bytes(audio)
        paths.append(path)
        d = duration(path)
        print(f"scene {i}: {d:5.1f}s in a {end - start:4.1f}s slot {'OK' if d <= end - start else 'TOO LONG'}")

    inputs = [a for p in paths for a in ("-i", str(p))]
    delays = "".join(f"[{i}]adelay={int(s * 1000)}:all=1[a{i}];" for i, (s, _, _) in enumerate(SCENES))
    mix = "".join(f"[a{i}]" for i in range(len(SCENES)))
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex",
                    f"{delays}{mix}amix=inputs={len(SCENES)}:normalize=0,apad=whole_dur={SCENES[-1][1]}",
                    "-ar", "48000", "-b:a", "192k", str(out / "voiceover.mp3")], check=True)
    print(f"{out / 'voiceover.mp3'}: {duration(out / 'voiceover.mp3'):.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
