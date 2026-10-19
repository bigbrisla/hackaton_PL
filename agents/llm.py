"""Chat client factory.

Order of preference:
1. Microsoft Foundry project (FOUNDRY_PROJECT_ENDPOINT + FOUNDRY_MODEL), keyless auth via
   DefaultAzureCredential (Azure CLI locally, managed identity on Azure Container Apps), calling the
   deployment through the project's OpenAI-compatible chat completions endpoint.
2. Offline deterministic client: each agent answers with its rule-based fallback. Used by tests,
   by `PULSE_OFFLINE=1`, and whenever no Foundry project is configured.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from agent_framework import BaseChatClient, ChatResponse, Message
from dotenv import load_dotenv

load_dotenv()

OfflineResponder = Callable[[dict], dict]


class OfflineChatClient(BaseChatClient):
    """Answers with a rule-based responder applied to the JSON payload of the last user message."""

    def __init__(self, responder: OfflineResponder):
        super().__init__()
        self.responder = responder

    async def _inner_get_response(self, *, messages, stream, options, **kwargs) -> ChatResponse:
        payload = json.loads(messages[-1].text)
        return ChatResponse(messages=[Message(role="assistant", contents=[json.dumps(self.responder(payload))])],
                            model="offline")


def online() -> bool:
    return bool(os.getenv("FOUNDRY_PROJECT_ENDPOINT")) and os.getenv("PULSE_OFFLINE") != "1"


_shared: Any = None


def make_client(offline_responder: OfflineResponder) -> Any:
    """A Foundry chat client shared by all agents, or an offline client for this agent."""
    global _shared
    if not online():
        return OfflineChatClient(offline_responder)
    if _shared is None:
        from agent_framework.openai import OpenAIChatCompletionClient
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import DefaultAzureCredential

        # the project's OpenAI-compatible client: chat completions on the Foundry deployment
        project = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=DefaultAzureCredential())
        _shared = OpenAIChatCompletionClient(model=os.environ.get("FOUNDRY_MODEL", "gpt-5-mini"),
                                             async_client=project.get_openai_client())
    return _shared
