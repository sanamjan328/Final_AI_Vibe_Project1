"""Unit tests for the LLM chat module."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.llm import chat as chat_module
from app.llm.chat import (
    ChatResponse,
    TradeAction,
    WatchlistAction,
    process_chat_message,
)
from app.llm.prompts import build_system_prompt


PORTFOLIO_CONTEXT = {
    "cash_balance": 9500.0,
    "total_value": 10234.50,
    "positions": [
        {
            "ticker": "AAPL",
            "quantity": 5,
            "avg_cost": 189.0,
            "current_price": 191.23,
            "unrealized_pnl": 11.15,
            "pnl_pct": 1.18,
        }
    ],
    "watchlist": [{"ticker": "AAPL", "price": 191.23}],
}


def _make_completion_response(content: str):
    """Build a minimal stand-in for the litellm completion response."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------


async def test_mock_flag_returns_canned_response():
    response = await process_chat_message(
        user_message="What should I do?",
        portfolio_context=PORTFOLIO_CONTEXT,
        conversation_history=[],
        mock=True,
    )
    assert isinstance(response, ChatResponse)
    assert "diversified" in response.message
    assert response.trades == []
    assert response.watchlist_changes == []


async def test_mock_env_var_enables_mock(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    response = await process_chat_message(
        user_message="hello",
        portfolio_context=PORTFOLIO_CONTEXT,
        conversation_history=[],
    )
    assert isinstance(response, ChatResponse)
    assert response.trades == []
    assert response.watchlist_changes == []


async def test_mock_env_var_false_does_not_enable_mock(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    valid_json = json.dumps(
        {"message": "hi", "trades": [], "watchlist_changes": []}
    )
    with patch.object(
        chat_module,
        "completion",
        return_value=_make_completion_response(valid_json),
    ) as mocked:
        response = await process_chat_message(
            user_message="hello",
            portfolio_context=PORTFOLIO_CONTEXT,
            conversation_history=[],
        )
    assert mocked.called
    assert response.message == "hi"


# ---------------------------------------------------------------------------
# JSON parsing — happy path
# ---------------------------------------------------------------------------


async def test_parses_valid_structured_output(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    valid_json = json.dumps(
        {
            "message": "Buying 2 AAPL.",
            "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 2}],
            "watchlist_changes": [{"ticker": "PYPL", "action": "add"}],
        }
    )

    with patch.object(
        chat_module,
        "completion",
        return_value=_make_completion_response(valid_json),
    ):
        response = await process_chat_message(
            user_message="Buy 2 AAPL",
            portfolio_context=PORTFOLIO_CONTEXT,
            conversation_history=[],
        )

    assert response.message == "Buying 2 AAPL."
    assert response.trades == [TradeAction(ticker="AAPL", side="buy", quantity=2.0)]
    assert response.watchlist_changes == [
        WatchlistAction(ticker="PYPL", action="add")
    ]


async def test_parses_response_with_missing_optional_arrays(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    valid_json = json.dumps({"message": "No action required."})

    with patch.object(
        chat_module,
        "completion",
        return_value=_make_completion_response(valid_json),
    ):
        response = await process_chat_message(
            user_message="Anything to do?",
            portfolio_context=PORTFOLIO_CONTEXT,
            conversation_history=[],
        )

    assert response.message == "No action required."
    assert response.trades == []
    assert response.watchlist_changes == []


# ---------------------------------------------------------------------------
# JSON parsing — failure modes
# ---------------------------------------------------------------------------


async def test_malformed_json_returns_error_response(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    with patch.object(
        chat_module,
        "completion",
        return_value=_make_completion_response("not valid json {"),
    ):
        response = await process_chat_message(
            user_message="hello",
            portfolio_context=PORTFOLIO_CONTEXT,
            conversation_history=[],
        )

    assert isinstance(response, ChatResponse)
    assert response.trades == []
    assert response.watchlist_changes == []
    assert "couldn't process" in response.message.lower()


async def test_schema_violation_returns_error_response(monkeypatch):
    """Valid JSON, but wrong shape (missing required `message`)."""
    monkeypatch.setenv("LLM_MOCK", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    bad_payload = json.dumps({"trades": [], "watchlist_changes": []})

    with patch.object(
        chat_module,
        "completion",
        return_value=_make_completion_response(bad_payload),
    ):
        response = await process_chat_message(
            user_message="hello",
            portfolio_context=PORTFOLIO_CONTEXT,
            conversation_history=[],
        )

    assert isinstance(response, ChatResponse)
    assert response.trades == []
    assert "couldn't process" in response.message.lower()


async def test_llm_call_exception_returns_error_response(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    with patch.object(chat_module, "completion", side_effect=boom):
        response = await process_chat_message(
            user_message="hello",
            portfolio_context=PORTFOLIO_CONTEXT,
            conversation_history=[],
        )

    assert isinstance(response, ChatResponse)
    assert response.trades == []
    assert "couldn't process" in response.message.lower()


async def test_empty_content_returns_error_response(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    with patch.object(
        chat_module,
        "completion",
        return_value=_make_completion_response(""),
    ):
        response = await process_chat_message(
            user_message="hello",
            portfolio_context=PORTFOLIO_CONTEXT,
            conversation_history=[],
        )

    assert isinstance(response, ChatResponse)
    assert "couldn't process" in response.message.lower()


async def test_missing_api_key_returns_error_response(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with patch.object(chat_module, "completion") as mocked:
        response = await process_chat_message(
            user_message="hello",
            portfolio_context=PORTFOLIO_CONTEXT,
            conversation_history=[],
        )

    assert not mocked.called
    assert isinstance(response, ChatResponse)
    assert "couldn't process" in response.message.lower()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def test_system_prompt_includes_portfolio_context():
    prompt = build_system_prompt(PORTFOLIO_CONTEXT)
    assert "FinAlly" in prompt
    assert "9500" in prompt
    assert "AAPL" in prompt
    assert "watchlist" in prompt.lower()


def test_system_prompt_describes_response_schema():
    prompt = build_system_prompt(PORTFOLIO_CONTEXT)
    assert '"message"' in prompt
    assert '"trades"' in prompt
    assert '"watchlist_changes"' in prompt


def test_system_prompt_handles_empty_context():
    prompt = build_system_prompt({})
    assert "FinAlly" in prompt
    assert '"message"' in prompt


# ---------------------------------------------------------------------------
# Conversation history handling
# ---------------------------------------------------------------------------


async def test_conversation_history_is_truncated(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"}
        for i in range(50)
    ]

    valid_json = json.dumps(
        {"message": "ok", "trades": [], "watchlist_changes": []}
    )

    captured: dict = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return _make_completion_response(valid_json)

    with patch.object(chat_module, "completion", side_effect=capture):
        await process_chat_message(
            user_message="latest question",
            portfolio_context=PORTFOLIO_CONTEXT,
            conversation_history=history,
        )

    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "latest question"
    # 1 system + last 20 of history + 1 current user message
    assert len(messages) == 1 + chat_module.HISTORY_LIMIT + 1
    # The earliest retained history message should be msg-30 (last 20 of 0..49)
    assert messages[1]["content"] == "msg-30"


async def test_conversation_history_filters_invalid_roles(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    history = [
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "should be dropped"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": None},  # invalid content
    ]
    valid_json = json.dumps(
        {"message": "ok", "trades": [], "watchlist_changes": []}
    )

    captured: dict = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return _make_completion_response(valid_json)

    with patch.object(chat_module, "completion", side_effect=capture):
        await process_chat_message(
            user_message="next",
            portfolio_context=PORTFOLIO_CONTEXT,
            conversation_history=history,
        )

    messages = captured["messages"]
    contents = [m["content"] for m in messages]
    assert "should be dropped" not in contents
    assert "hi" in contents
    assert "hello" in contents
