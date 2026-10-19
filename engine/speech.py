"""Neural narration with Azure AI Speech, keyless (Microsoft Entra token on the Foundry AI Services resource).

Env: AZURE_SPEECH_REGION (e.g. swedencentral) and AZURE_SPEECH_RESOURCE_ID (the AI Services resource id).
Returns None when not configured or on failure, so the browser falls back to its built-in voice.
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from xml.sax.saxutils import escape

import httpx

VOICES = {
    "en": ("en-GB", "en-GB-RyanNeural"),
    "it": ("it-IT", "it-IT-DiegoNeural"),
    "es": ("es-ES", "es-ES-AlvaroNeural"),
    "ja": ("ja-JP", "ja-JP-KeitaNeural"),
    "fr": ("fr-FR", "fr-FR-HenriNeural"),
    "de": ("de-DE", "de-DE-ConradNeural"),
    "pt": ("pt-BR", "pt-BR-AntonioNeural"),
}
_cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()
_token: tuple[str, float] | None = None


async def _bearer() -> str:
    global _token
    if _token is None or _token[1] - time.time() < 300:
        from azure.identity.aio import DefaultAzureCredential

        async with DefaultAzureCredential() as cred:
            tok = await cred.get_token("https://cognitiveservices.azure.com/.default")
        _token = (tok.token, tok.expires_on)
    return f"aad#{os.environ['AZURE_SPEECH_RESOURCE_ID']}#{_token[0]}"


async def synthesize(text: str, lang: str) -> bytes | None:
    region = os.getenv("AZURE_SPEECH_REGION")
    if not region or not os.getenv("AZURE_SPEECH_RESOURCE_ID"):
        return None
    key = (lang, text)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    locale, voice = VOICES.get(lang, VOICES["en"])
    ssml = (f"<speak version='1.0' xml:lang='{locale}'><voice name='{voice}'>"
            f"<prosody rate='+6%'>{escape(text)}</prosody></voice></speak>")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                content=ssml.encode(),
                headers={"Authorization": f"Bearer {await _bearer()}", "Content-Type": "application/ssml+xml",
                         "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3", "User-Agent": "pulse"})
        res.raise_for_status()
    except Exception:  # noqa: BLE001 - narration is optional; the browser voice takes over
        return None
    _cache[key] = res.content
    if len(_cache) > 300:
        _cache.popitem(last=False)
    return res.content
