"""Hermes-aligned AIAgent kernel — full tool loop (M1)."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from media2text.agent import pi_emit
from media2text.agent.context_compressor import maybe_post_turn_compress, maybe_preflight
from media2text.agent.hermes_state import MessageRow, SessionDB, parse_binding
from media2text.agent.iteration_budget import IterationBudget
from media2text.agent.model_tools import handle_function_call
from media2text.agent.profile_resolver import resolve_profile
from media2text.agent.prompt_builder import build_system_prompt, frozen_system_messages
from media2text.agent.runtime_provider import (
    ChatClient,
    TurnCancelled,
    build_openai_client,
    resolve_model,
    tool_result_text as format_tool_output,
)
from media2text.agent.tools.m2t_handlers import ToolContext
from media2text.agent.tools.registry import openai_tools
from media2text.agent.tools.toolsets import DEFAULT_TOOLSET, resolve_tool_names
from media2text.core.config import AppConfig


EmitFn = Callable[[dict[str, Any]], None]


class AIAgent:
    def __init__(
        self,
        db: SessionDB,
        cfg: AppConfig | None = None,
        *,
        llm: ChatClient | None = None,
        supervisor: Any | None = None,
        toolset: str = DEFAULT_TOOLSET,
    ) -> None:
        self._db = db
        self._cfg = cfg or AppConfig.load()
        self._llm = llm
        self._supervisor = supervisor
        self._toolset = toolset

    def _max_tool_output_chars(self) -> int:
        return self._cfg.desktop.agent.max_tool_output_chars

    def _emit(self, emit: EmitFn | None, event: dict[str, Any]) -> None:
        if emit:
            emit(event)

    def _truncate(self, text: str) -> str:
        limit = self._max_tool_output_chars()
        if len(text) <= limit:
            return text
        return text[: limit - 20] + "\n…[truncated]"

    def run_conversation(
        self,
        *,
        display_thread_id: str,
        user_text: str,
        turn_id: str | None = None,
        cancel_event=None,
        emit: EmitFn | None = None,
    ) -> str:
        started = time.time()
        self._emit(emit, pi_emit.turn_start())
        self._emit(emit, pi_emit.turn_phase("thinking", "思考中…"))

        thread_row = self._db.get_thread_by_display_id(display_thread_id)
        if thread_row is None:
            raise KeyError(f"thread not found: {display_thread_id}")

        session_id = self._db.get_active_session_for_thread(display_thread_id)
        binding = parse_binding(thread_row["active_binding_json"])
        creator_id = thread_row["creator_id"]

        self._db.append_message(session_id, MessageRow(role="user", content=user_text))

        profile = resolve_profile(creator_id=creator_id, cfg=self._cfg)
        parts = build_system_prompt(
            cfg=self._cfg,
            profile_ctx=profile,
            thread={
                "creator_id": creator_id,
                "model": binding.get("model"),
                "context_mode": binding.get("context_mode"),
                "binding": binding,
            },
        )
        system_msgs = frozen_system_messages(parts)
        replay = self._db.get_messages_as_conversation(session_id)
        # replay already includes new user message
        messages: list[dict[str, Any]] = system_msgs + replay
        messages = maybe_preflight(messages, self._cfg)

        tool_names = resolve_tool_names(profile)
        tools_schema = openai_tools(tool_names)
        model = resolve_model(self._cfg, binding.get("model"))
        llm = self._llm or build_openai_client(self._cfg, provider_name=binding.get("provider_name"))
        budget = IterationBudget(self._cfg.agent.max_turns)
        tool_ctx = ToolContext(
            cfg=self._cfg,
            conn=self._db.conn,
            creator_id=creator_id,
            supervisor=self._supervisor,
            session_id=session_id,
            display_thread_id=display_thread_id,
            profile=profile,
        )

        final_text = ""
        try:
            while not budget.exhausted:
                if cancel_event is not None and cancel_event.is_set():
                    raise TurnCancelled()
                budget.consume()
                completion = llm.complete(
                    messages=messages,
                    tools=tools_schema,
                    model=model,
                    cancel_event=cancel_event,
                )

                if completion.tool_calls:
                    openai_tool_calls = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in completion.tool_calls
                    ]
                    assistant_msg = {
                        "role": "assistant",
                        "content": completion.content,
                        "tool_calls": openai_tool_calls,
                    }
                    messages.append(assistant_msg)
                    self._db.append_message(
                        session_id,
                        MessageRow(
                            role="assistant",
                            content=completion.content,
                            tool_calls_json=json.dumps(openai_tool_calls),
                            thinking_text=completion.thinking_text,
                        ),
                    )

                    def _run_one(tc) -> tuple[Any, dict[str, Any], str]:
                        self._emit(
                            emit,
                            pi_emit.tool_start(tool_call_id=tc.id, name=tc.name),
                        )
                        self._emit(emit, pi_emit.turn_phase("tool", f"工具 · {tc.name}"))
                        payload = handle_function_call(tc.name, tc.arguments, tool_ctx)
                        self._emit(emit, pi_emit.tool_result_payload(payload))
                        text_out = self._truncate(format_tool_output(payload))
                        return tc, payload, text_out

                    results: list[tuple[Any, dict[str, Any], str]] = []
                    with ThreadPoolExecutor(max_workers=min(8, len(completion.tool_calls))) as pool:
                        futures = [pool.submit(_run_one, tc) for tc in completion.tool_calls]
                        for fut in as_completed(futures):
                            results.append(fut.result())

                    for tc, _payload, text_out in results:
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": text_out,
                        }
                        messages.append(tool_msg)
                        self._db.append_message(
                            session_id,
                            MessageRow(
                                role="tool",
                                content=text_out,
                                tool_call_id=tc.id,
                                tool_name=tc.name,
                            ),
                        )
                    continue

                final_text = (completion.content or "").strip()
                if final_text:
                    for i in range(0, len(final_text), 32):
                        self._emit(emit, pi_emit.assistant_delta(final_text[i : i + 32]))
                duration_ms = int((time.time() - started) * 1000)
                self._db.append_message(
                    session_id,
                    MessageRow(
                        role="assistant",
                        content=final_text,
                        thinking_text=completion.thinking_text,
                        duration_ms=duration_ms,
                    ),
                )
                self._emit(
                    emit,
                    pi_emit.message_assistant(
                        final_text,
                        duration_ms=duration_ms,
                        thinking_text=completion.thinking_text,
                    ),
                )
                break
            else:
                self._emit(
                    emit,
                    pi_emit.agent_error("iteration budget exhausted", code="MAX_TURNS"),
                )
                final_text = "抱歉，本轮对话迭代次数已达上限。"
        except TurnCancelled:
            self._emit(emit, pi_emit.agent_error("turn cancelled", code="CANCELLED"))
            raise
        except Exception as exc:  # noqa: BLE001
            self._emit(emit, pi_emit.agent_error(str(exc), code="AGENT_ERROR"))
            raise
        finally:
            session_id = maybe_post_turn_compress(
                self._db,
                display_thread_id=display_thread_id,
                session_id=session_id,
                messages=messages,
                cfg=self._cfg,
            )
            duration_ms = int((time.time() - started) * 1000)
            self._emit(emit, pi_emit.turn_end(duration_ms))

        return final_text
