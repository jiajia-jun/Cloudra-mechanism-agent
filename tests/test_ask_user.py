"""Exact refusal tokens must preserve the human's entire reason."""

import pytest

from cloudra.tools.Interactool.ask_user import AskUser, AskUser_input_schema, use_input_handler


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["拒绝", "Reject", "REJECT"])
@pytest.mark.parametrize("separator", [":", "："])
async def test_multiline_refusal_is_rejected(prefix, separator, mock_session):
    async def answer(_prompt):
        return f"{prefix} {separator} first reason\nsecond reason： details: more"

    with use_input_handler(answer):
        result = await AskUser().tool_call(AskUser_input_schema(question="Proceed?"), mock_session)

    assert result.rejected is True
    assert result.is_success is False
    assert result.reason == "first reason\nsecond reason： details: more"
    assert result.answer == result.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["rejection: details", "拒绝不了：说明", "yes: reject", "rejecting"])
async def test_refusal_requires_exact_token(text, mock_session):
    async def answer(_prompt):
        return text

    with use_input_handler(answer):
        result = await AskUser().tool_call(AskUser_input_schema(question="Proceed?"), mock_session)

    assert result.is_success is True
    assert result.rejected is False
    assert result.answer == text


@pytest.mark.asyncio
async def test_refusal_can_be_disabled(mock_session):
    async def answer(_prompt):
        return "reject: reason\nmore"

    with use_input_handler(answer):
        result = await AskUser().tool_call(
            AskUser_input_schema(question="Describe", allow_reject=False), mock_session,
        )

    assert result.is_success is True
    assert result.rejected is False
    assert result.answer == "reject: reason\nmore"


@pytest.mark.asyncio
async def test_empty_refusal_reason_is_requested(mock_session):
    answers = iter(["reject：", "explanation"])

    async def answer(_prompt):
        return next(answers)

    with use_input_handler(answer):
        result = await AskUser().tool_call(AskUser_input_schema(question="Proceed?"), mock_session)

    assert result.rejected is True
    assert result.reason == "explanation"
