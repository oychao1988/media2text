"""Hermes-aligned AIAgent kernel — full tool loop (M1) + self-evolution hooks (M7a)."""

from __future__ import annotations

import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from media2text.agent import pi_emit
from media2text.agent.agent_errors import user_facing_agent_error
from media2text.agent.agent_state import (
    hydrate_turns_since_memory,
    save_agent_state,
)
from media2text.agent.agent_turn_hooks import (
    apply_review_resets,
    compute_review_flags,
    maybe_spawn_background_review,
    review_allowed_tool_names,
)
from media2text.agent.approval import ApprovalGate
from media2text.agent.context_compressor import maybe_post_turn_compress, maybe_preflight
from media2text.agent.hermes_state import MessageRow, SessionDB, parse_binding
from media2text.agent.iteration_budget import IterationBudget
from media2text.agent.model_tools import handle_function_call
from media2text.agent.profile_resolver import resolve_profile
from media2text.agent.prompt_builder import SystemPromptParts, build_system_prompt, frozen_system_messages
from media2text.agent.runtime_provider import (
    ChatClient,
    TurnCancelled,
    build_openai_client,
    resolve_agent_provider,
    resolve_model,
    tool_result_text as format_tool_output,
)
from media2text.agent.thread_title import maybe_auto_title_thread
from media2text.agent.tools.m2t_handlers import ToolContext
from media2text.agent.tools.registry import ALL_TOOLS, openai_tools
from media2text.agent.tools.toolsets import (
    DEFAULT_TOOLSET,
    REVIEW_TOOLSET,
    resolve_tool_names,
    tool_names_for_set,
)
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
        quiet: bool = False,
    ) -> None:
        self._db = db
        self._cfg = cfg or AppConfig.load()
        self._llm = llm
        self._supervisor = supervisor
        self._toolset = toolset
        self._quiet = quiet

    def _max_tool_output_chars(self) -> int:
        return self._cfg.desktop.agent.max_tool_output_chars

    def _emit(self, emit: EmitFn | None, event: dict[str, Any]) -> None:
        if self._quiet:
            return
        if emit:
            emit(event)

    def _truncate(self, text: str) -> str:
        limit = self._max_tool_output_chars()
        if len(text) <= limit:
            return text
        return text[: limit - 20] + "\n…[truncated]"

    def _resolve_tool_names(self, profile) -> list[str]:
        if self._toolset == REVIEW_TOOLSET:
            return [n for n in tool_names_for_set(REVIEW_TOOLSET) if n in ALL_TOOLS]
        return resolve_tool_names(profile, self._cfg)

    def _prompt_cache_key(
        self,
        *,
        creator_id: str | None,
        binding: dict[str, Any],
        profile_id: str,
    ) -> str:
        return "|".join(
            [
                str(creator_id or ""),
                str(binding.get("model") or ""),
                str(binding.get("context_mode") or ""),
                profile_id,
            ]
        )

    def _build_system_messages(
        self,
        *,
        profile,
        creator_id: str | None,
        binding: dict[str, Any],
        agent_state=None,
    ) -> list[dict[str, str]]:
        cache_key = self._prompt_cache_key(
            creator_id=creator_id,
            binding=binding,
            profile_id=profile.profile_id,
        )
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
        if (
            agent_state is not None
            and agent_state.prompt_cache_key == cache_key
            and agent_state.cached_system_prompt
        ):
            parts = SystemPromptParts(
                stable=parts.stable,
                context=parts.context,
                volatile=agent_state.cached_system_prompt,
            )
        elif agent_state is not None:
            agent_state.cached_system_prompt = parts.volatile
            agent_state.prompt_cache_key = cache_key
        return frozen_system_messages(parts)

    def run_review_conversation(
        self,
        *,
        display_thread_id: str,
        session_id: str,
        user_text: str,
        conversation_history: list[dict[str, Any]],
        binding: dict[str, Any],
        creator_id: str | None,
        provider_name: str,
        model: str,
        cached_volatile: str | None = None,
        cancel_event=None,
        max_iterations: int | None = None,
    ) -> str:
        from media2text.agent.agent_state import AgentState

        profile = resolve_profile(creator_id=creator_id, cfg=self._cfg)
        agent_state = AgentState(cached_system_prompt=cached_volatile)
        if cached_volatile:
            agent_state.prompt_cache_key = self._prompt_cache_key(
                creator_id=creator_id,
                binding=binding,
                profile_id=profile.profile_id,
            )

        system_msgs = self._build_system_messages(
            profile=profile,
            creator_id=creator_id,
            binding=binding,
            agent_state=agent_state,
        )
        history = [m for m in conversation_history if m.get("role") != "system"]
        messages: list[dict[str, Any]] = system_msgs + history + [
            {"role": "user", "content": user_text}
        ]
        messages = maybe_preflight(messages, self._cfg)

        tool_names = self._resolve_tool_names(profile)
        allowed = review_allowed_tool_names(set(tool_names))
        tools_schema = openai_tools(list(allowed))
        llm = self._llm or build_openai_client(self._cfg, provider_name=provider_name)
        budget = IterationBudget(max_iterations or self._cfg.agent.review_max_iterations)
        tool_ctx = ToolContext(
            cfg=self._cfg,
            conn=self._db.conn,
            creator_id=creator_id,
            supervisor=self._supervisor,
            session_id=session_id,
            display_thread_id=display_thread_id,
            profile=profile,
            allowed_tools=allowed,
        )

        final_text = ""
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
                messages.append(
                    {
                        "role": "assistant",
                        "content": completion.content,
                        "tool_calls": openai_tool_calls,
                    }
                )

                for tc in completion.tool_calls:
                    payload = handle_function_call(tc.name, tc.arguments, tool_ctx)
                    text_out = self._truncate(format_tool_output(payload))
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": text_out,
                        }
                    )
                continue

            final_text = (completion.content or "").strip()
            break

        return final_text

    def run_conversation(
        self,
        *,
        display_thread_id: str,
        user_text: str,
        turn_id: str | None = None,
        retry_after_message_id: str | None = None,
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

        agent_state = hydrate_turns_since_memory(
            self._db,
            session_id,
            nudge_interval=self._cfg.memory.nudge_interval,
        )
        is_retry = bool(retry_after_message_id)

        if retry_after_message_id:
            retry_row = self._db.get_message_by_id(retry_after_message_id)
            if retry_row is None or retry_row["role"] != "user":
                raise ValueError("retry target must be a user message")
            if retry_row["session_id"] != session_id:
                raise ValueError("retry target belongs to another session")
            self._db.delete_messages_after(session_id, int(retry_row["seq"]))
            user_text = (retry_row["content"] or user_text).strip()
        else:
            self._db.append_message(session_id, MessageRow(role="user", content=user_text))
            agent_state.turns_since_memory += 1

        agent_state.iters_since_skill = 0

        profile = resolve_profile(creator_id=creator_id, cfg=self._cfg)
        system_msgs = self._build_system_messages(
            profile=profile,
            creator_id=creator_id,
            binding=binding,
            agent_state=agent_state,
        )
        replay = self._db.get_messages_as_conversation(session_id)
        messages: list[dict[str, Any]] = system_msgs + replay
        messages = maybe_preflight(messages, self._cfg)

        tool_names = self._resolve_tool_names(profile)
        valid_tool_names = set(tool_names)
        tools_schema = openai_tools(tool_names)
        model = resolve_model(self._cfg, binding.get("model"))
        provider_name = resolve_agent_provider(
            self._cfg,
            model=model,
            provider_name=binding.get("provider_name"),
        )
        llm = self._llm or build_openai_client(self._cfg, provider_name=provider_name)
        budget = IterationBudget(self._cfg.agent.max_turns)
        approval_gate = ApprovalGate(self._cfg, emit=emit if not self._quiet else None)
        tool_ctx = ToolContext(
            cfg=self._cfg,
            conn=self._db.conn,
            creator_id=creator_id,
            supervisor=self._supervisor,
            session_id=session_id,
            display_thread_id=display_thread_id,
            profile=profile,
            approval_gate=approval_gate,
        )

        final_text = ""
        cancelled = False
        messages_snapshot: list[dict[str, Any]] = []
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
                    agent_state.iters_since_skill += 1
                    if any(tc.name == "skill_manage" for tc in completion.tool_calls):
                        agent_state.iters_since_skill = 0

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
                        self._emit(emit, pi_emit.tool_result_payload(payload, name=tc.name))
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
                messages.append({"role": "assistant", "content": final_text})
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
                final_text = "抱歉，本轮对话迭代次数已达上限。"
                duration_ms = int((time.time() - started) * 1000)
                self._db.append_message(
                    session_id,
                    MessageRow(role="assistant", content=final_text, duration_ms=duration_ms),
                )
                self._emit(
                    emit,
                    pi_emit.agent_error("iteration budget exhausted", code="MAX_TURNS"),
                )

            messages_snapshot = copy.deepcopy(messages)
        except TurnCancelled:
            cancelled = True
            self._emit(emit, pi_emit.agent_error("turn cancelled", code="CANCELLED"))
            raise
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.time() - started) * 1000)
            final_text = user_facing_agent_error(exc)
            self._db.append_message(
                session_id,
                MessageRow(role="assistant", content=final_text, duration_ms=duration_ms),
            )
            self._emit(emit, pi_emit.agent_error(final_text, code="AGENT_ERROR"))
        finally:
            review_flags = compute_review_flags(
                self._cfg,
                turns_since_memory=agent_state.turns_since_memory,
                iters_since_skill=agent_state.iters_since_skill,
                valid_tool_names=valid_tool_names,
            )
            apply_review_resets(agent_state, review_flags)
            save_agent_state(self._db, session_id, agent_state)

            session_id = maybe_post_turn_compress(
                self._db,
                display_thread_id=display_thread_id,
                session_id=session_id,
                messages=messages,
                cfg=self._cfg,
            )
            if final_text.strip() and user_text.strip():
                new_title = maybe_auto_title_thread(
                    self._db,
                    self._cfg,
                    display_thread_id,
                    user_text=user_text,
                    assistant_text=final_text,
                )
                if new_title:
                    self._emit(
                        emit,
                        pi_emit.thread_title(display_thread_id, new_title),
                    )
            duration_ms = int((time.time() - started) * 1000)
            self._emit(emit, pi_emit.turn_end(duration_ms))

            from media2text.agent.curator import touch_agent_activity

            touch_agent_activity(self._cfg)

            if messages_snapshot and not is_retry:
                maybe_spawn_background_review(
                    self,
                    self._cfg,
                    session_id=session_id,
                    db=self._db,
                    messages_snapshot=messages_snapshot,
                    flags=review_flags,
                    agent_state=agent_state,
                    cancelled=cancelled,
                    has_final_text=bool(final_text.strip()),
                    binding=binding,
                    creator_id=creator_id,
                    display_thread_id=display_thread_id,
                    provider_name=provider_name,
                    model=model,
                )

        return final_text
