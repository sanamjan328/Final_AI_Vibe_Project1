"""LLM chat integration for FinAlly.

Uses LiteLLM → OpenRouter with Cerebras as the inference provider, with
structured outputs to drive trade and watchlist actions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from litellm import completion
from pydantic import BaseModel, Field, ValidationError

from app.llm.prompts import build_system_prompt


logger = logging.getLogger(__name__)


_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
HISTORY_LIMIT = 20
MAX_TOKENS = 1024


class TradeAction(BaseModel):
    ticker: str
    side: str  # "buy" | "sell"
    quantity: float


class WatchlistAction(BaseModel):
    ticker: str
    action: str  # "add" | "remove"


class ChatResponse(BaseModel):
    message: str
    trades: list[TradeAction] = Field(default_factory=list)
    watchlist_changes: list[WatchlistAction] = Field(default_factory=list)


_MOCK_RESPONSE = ChatResponse(
    message=(
        "I've analyzed your portfolio. You have a well-diversified position. "
        "Consider adding some NVDA exposure for AI sector growth."
    ),
    trades=[],
    watchlist_changes=[],
)


def _is_mock_enabled(mock_flag: bool) -> bool:
    if mock_flag:
        return True
    return os.getenv("LLM_MOCK", "").strip().lower() == "true"


def _build_messages(
    user_message: str,
    portfolio_context: dict[str, Any],
    conversation_history: list[dict[str, str]],
) -> list[dict[str, str]]:
    system_prompt = build_system_prompt(portfolio_context)
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history[-HISTORY_LIMIT:]:
        role = msg.get("role")
        content = msg.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _parse_response(content: str) -> ChatResponse:
    """Parse the LLM's JSON content into a ChatResponse."""
    data = json.loads(content)
    return ChatResponse.model_validate(data)


def _error_response(detail: str) -> ChatResponse:
    return ChatResponse(
        message=(
            "Sorry, I couldn't process that just now. "
            f"Please try again in a moment. ({detail})"
        ),
        trades=[],
        watchlist_changes=[],
    )


async def process_chat_message(
    user_message: str,
    portfolio_context: dict[str, Any],
    conversation_history: list[dict[str, str]],
    mock: bool = False,
) -> ChatResponse:
    """Process a chat message and return the structured response.

    On mock mode, returns a deterministic canned response. On LLM/network/parse
    failure, returns a ChatResponse with a user-facing error message instead of
    raising, so the API layer can continue without special-casing.
    """
    if _is_mock_enabled(mock):
        return _MOCK_RESPONSE.model_copy(deep=True)

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return _error_response("LLM is not configured")

    messages = _build_messages(user_message, portfolio_context, conversation_history)

    try:
        response = await asyncio.to_thread(
            completion,
            model=MODEL,
            messages=messages,
            response_format=ChatResponse,
            reasoning_effort="low",
            extra_body=EXTRA_BODY,
            max_tokens=MAX_TOKENS,
            api_key=api_key,
        )
    except Exception as exc:
        logger.exception("LLM completion call failed")
        return _error_response(f"LLM call failed: {exc.__class__.__name__}")

    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError) as exc:
        logger.exception("Unexpected LLM response shape")
        return _error_response(f"unexpected response shape: {exc.__class__.__name__}")

    if not content:
        return _error_response("empty response from model")

    try:
        return _parse_response(content)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Failed to parse LLM JSON: %s", exc)
        return _error_response("malformed model response")
