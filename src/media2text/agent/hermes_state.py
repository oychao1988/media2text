"""Hermes SessionDB — SQLite sessions/messages persistence."""

from __future__ import annotations

import json
import random
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class MessageRow:
    role: str
    content: str | None = None
    id: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_calls_json: str | None = None
    thinking_text: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    message_kind: str = "normal"


@dataclass(frozen=True)
class SearchHit:
    message_id: str
    session_id: str
    display_thread_id: str
    title: str | None
    role: str
    snippet: str
    seq: int
    creator_id: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_with_retry(conn: sqlite3.Connection, fn) -> None:
    for attempt in range(5):
        try:
            fn()
            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 4:
                raise
            time.sleep(0.05 * (2**attempt) + random.random() * 0.02)


class SessionDB:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def create_session(
        self,
        *,
        display_thread_id: str,
        title: str | None = None,
        creator_id: str | None = None,
        provider_name: str | None = None,
        model: str = "auto",
        context_mode: str = "both",
        live_session_id: str | None = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        thread_id = display_thread_id
        now = _utc_now()
        binding = {
            "provider_name": provider_name,
            "model": model,
            "context_mode": context_mode,
            "session_id": live_session_id,
        }

        def _insert() -> None:
            self._conn.execute(
                """
                INSERT INTO sessions (
                  id, display_thread_id, parent_session_id, title, creator_id,
                  active_binding_json, token_estimate, created_at, updated_at
                )
                VALUES (?, ?, NULL, ?, ?, ?, 0, ?, ?)
                """,
                (
                    session_id,
                    thread_id,
                    title,
                    creator_id,
                    json.dumps(binding),
                    now,
                    now,
                ),
            )

        _write_with_retry(self._conn, _insert)
        return session_id

    def get_session_row(self, session_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

    def get_thread_by_display_id(self, display_thread_id: str) -> sqlite3.Row | None:
        row = self._conn.execute(
            """
            SELECT id FROM sessions
            WHERE display_thread_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (display_thread_id,),
        ).fetchone()
        if not row:
            return None
        return self.get_session_row(str(row["id"]))

    def list_threads(
        self,
        *,
        creator_id: str | None = None,
        live_session_id: str | None = None,
    ) -> list[sqlite3.Row]:
        rows = self._conn.execute(
            """
            SELECT s.*
            FROM sessions s
            INNER JOIN (
              SELECT display_thread_id, MAX(created_at) AS max_created
              FROM sessions
              GROUP BY display_thread_id
            ) latest
              ON s.display_thread_id = latest.display_thread_id
             AND s.created_at = latest.max_created
            ORDER BY s.updated_at DESC
            """
        ).fetchall()
        out: list[sqlite3.Row] = []
        for row in rows:
            if creator_id is not None and row["creator_id"] != creator_id:
                continue
            if live_session_id is not None:
                binding = parse_binding(row["active_binding_json"])
                if binding.get("session_id") != live_session_id:
                    continue
            out.append(row)
        return out

    def update_session(
        self,
        display_thread_id: str,
        *,
        title: str | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        context_mode: str | None = None,
        live_session_id: str | None = None,
        clear_live_session: bool = False,
    ) -> bool:
        session_id = self.get_active_session_for_thread(display_thread_id)
        row = self.get_session_row(session_id)
        if not row:
            return False
        binding = parse_binding(row["active_binding_json"])
        if title is not None:
            title_val = title
        else:
            title_val = row["title"]
        if provider_name is not None:
            binding["provider_name"] = provider_name
        if model is not None:
            binding["model"] = model
        if context_mode is not None:
            binding["context_mode"] = context_mode
        if clear_live_session:
            binding["session_id"] = None
        elif live_session_id is not None:
            binding["session_id"] = live_session_id
        now = _utc_now()

        def _update() -> None:
            self._conn.execute(
                """
                UPDATE sessions
                SET title = ?, active_binding_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (title_val, json.dumps(binding), now, session_id),
            )

        _write_with_retry(self._conn, _update)
        return True

    def activate_thread(
        self,
        display_thread_id: str,
        *,
        creator_id: str | None = None,
        live_session_id: str | None = None,
        clear_live_session: bool = False,
        session_kind: str | None = None,
        transcript_path: str | None = None,
        summary_path: str | None = None,
        context_mode: str | None = None,
        attachments: list[Any] | None = None,
    ) -> bool:
        session_id = self.get_active_session_for_thread(display_thread_id)
        row = self.get_session_row(session_id)
        if not row:
            return False
        binding = parse_binding(row["active_binding_json"])
        if context_mode is not None:
            binding["context_mode"] = context_mode
        if clear_live_session:
            binding["session_id"] = None
        elif live_session_id is not None:
            binding["session_id"] = live_session_id
        if session_kind is not None:
            binding["session_kind"] = session_kind
        if transcript_path is not None:
            binding["transcript_path"] = transcript_path
        if summary_path is not None:
            binding["summary_path"] = summary_path
        if attachments is not None:
            binding["attachments"] = attachments
            tp = next(
                (a.get("path") for a in attachments if a.get("docType") == "transcript"),
                None,
            )
            sp = next(
                (a.get("path") for a in attachments if a.get("docType") == "summary"),
                None,
            )
            binding["transcript_path"] = tp
            binding["summary_path"] = sp
        now = _utc_now()
        creator_val = row["creator_id"] if creator_id is None else creator_id

        def _update() -> None:
            self._conn.execute(
                """
                UPDATE sessions
                SET creator_id = ?, active_binding_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (creator_val, json.dumps(binding), now, session_id),
            )

        _write_with_retry(self._conn, _update)
        return True

    def delete_thread(self, display_thread_id: str) -> bool:
        session_ids = [
            r[0]
            for r in self._conn.execute(
                "SELECT id FROM sessions WHERE display_thread_id = ?",
                (display_thread_id,),
            ).fetchall()
        ]
        if not session_ids:
            return False

        def _delete() -> None:
            for sid in session_ids:
                self._conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
            self._conn.execute(
                "DELETE FROM sessions WHERE display_thread_id = ?",
                (display_thread_id,),
            )

        _write_with_retry(self._conn, _delete)
        return True

    def append_message(self, session_id: str, message: MessageRow) -> str:
        mid = message.id or str(uuid.uuid4())
        now = _utc_now()
        seq_row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        seq = int(seq_row[0])

        def _insert() -> None:
            self._conn.execute(
                """
                INSERT INTO messages (
                  id, session_id, seq, role, content, tool_call_id, tool_name,
                  tool_calls_json, thinking_text, input_tokens, output_tokens,
                  duration_ms, message_kind, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    session_id,
                    seq,
                    message.role,
                    message.content,
                    message.tool_call_id,
                    message.tool_name,
                    message.tool_calls_json,
                    message.thinking_text,
                    message.input_tokens,
                    message.output_tokens,
                    message.duration_ms,
                    message.message_kind,
                    now,
                ),
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )

        _write_with_retry(self._conn, _insert)
        return mid

    def get_message_by_id(self, message_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()

    def delete_messages_after(self, session_id: str, after_seq: int) -> None:
        def _delete() -> None:
            self._conn.execute(
                "DELETE FROM messages WHERE session_id = ? AND seq > ?",
                (session_id, after_seq),
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (_utc_now(), session_id),
            )

        _write_with_retry(self._conn, _delete)

    def get_messages(self, display_thread_id: str) -> list[sqlite3.Row]:
        session_id = self.get_active_session_for_thread(display_thread_id)
        return list(
            self._conn.execute(
                """
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY seq
                """,
                (session_id,),
            ).fetchall()
        )

    def get_messages_as_conversation(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT role, content, tool_call_id, tool_name, tool_calls_json, message_kind
            FROM messages
            WHERE session_id = ?
            ORDER BY seq
            """,
            (session_id,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            role = row["role"]
            if role == "assistant" and row["tool_calls_json"]:
                try:
                    tool_calls = json.loads(row["tool_calls_json"])
                except json.JSONDecodeError:
                    tool_calls = []
                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": row["content"],
                    "tool_calls": tool_calls,
                }
                out.append(msg)
            elif role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": row["tool_call_id"],
                        "content": row["content"] or "",
                    }
                )
            elif row["message_kind"] == "compression_summary":
                out.append(
                    {
                        "role": "assistant",
                        "content": f"[compression_summary]\n{row['content'] or ''}",
                    }
                )
            else:
                out.append({"role": role, "content": row["content"] or ""})
        return out

    def get_active_session_for_thread(self, display_thread_id: str) -> str:
        row = self._conn.execute(
            """
            SELECT id FROM sessions
            WHERE display_thread_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (display_thread_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"thread not found: {display_thread_id}")
        return str(row["id"])

    def fork_session(self, parent_id: str, *, reason: str) -> str:
        parent = self.get_session_row(parent_id)
        if parent is None:
            raise KeyError(f"parent session not found: {parent_id}")

        child_id = str(uuid.uuid4())
        now = _utc_now()

        def _insert() -> None:
            self._conn.execute(
                """
                INSERT INTO sessions (
                  id, display_thread_id, parent_session_id, title, creator_id,
                  active_binding_json, token_estimate, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    child_id,
                    parent["display_thread_id"],
                    parent_id,
                    parent["title"],
                    parent["creator_id"],
                    parent["active_binding_json"],
                    now,
                    now,
                ),
            )

        _write_with_retry(self._conn, _insert)
        return child_id

    def update_token_estimate(self, session_id: str, tokens: int) -> None:
        now = _utc_now()

        def _update() -> None:
            self._conn.execute(
                """
                UPDATE sessions SET token_estimate = ?, updated_at = ?
                WHERE id = ?
                """,
                (tokens, now, session_id),
            )

        _write_with_retry(self._conn, _update)

    def _fts_search_table(
        self,
        table: str,
        query: str,
        *,
        session_id: str | None,
        creator_id: str | None,
        limit: int,
    ) -> list[sqlite3.Row]:
        clauses = [f"{table} MATCH ?"]
        params: list[Any] = [query]
        if session_id:
            clauses.append("m.session_id = ?")
            params.append(session_id)
        if creator_id:
            clauses.append("s.creator_id = ?")
            params.append(creator_id)
        params.append(limit)
        where_sql = " AND ".join(clauses)
        return list(
            self._conn.execute(
                f"""
                SELECT
                  m.id AS message_id,
                  m.session_id,
                  s.display_thread_id,
                  s.title,
                  s.creator_id,
                  m.role,
                  m.content,
                  m.seq,
                  bm25({table}) AS rank
                FROM {table}
                JOIN messages m ON m.id = {table}.message_id
                JOIN sessions s ON s.id = m.session_id
                WHERE {where_sql}
                ORDER BY rank
                LIMIT ?
                """,
                params,
            ).fetchall()
        )

    def search_messages(
        self,
        query: str,
        *,
        session_id: str | None = None,
        creator_id: str | None = None,
        limit: int = 8,
    ) -> list[SearchHit]:
        q = query.strip()
        if not q:
            return []

        # Quote multi-token queries so FTS5 treats them as a phrase where supported.
        fts_q = q.replace('"', '""')
        if " " in fts_q or "-" in fts_q:
            fts_q = f'"{fts_q}"'
        rows: list[sqlite3.Row] = []
        for table in ("messages_fts", "messages_fts_trigram"):
            try:
                rows.extend(
                    self._fts_search_table(
                        table,
                        fts_q,
                        session_id=session_id,
                        creator_id=creator_id,
                        limit=limit,
                    )
                )
            except sqlite3.OperationalError:
                continue

        rows.sort(key=lambda r: float(r["rank"]))
        seen: set[str] = set()
        hits: list[SearchHit] = []
        for row in rows:
            mid = str(row["message_id"])
            if mid in seen:
                continue
            seen.add(mid)
            content = row["content"] or ""
            snippet = content[:240] + ("…" if len(content) > 240 else "")
            hits.append(
                SearchHit(
                    message_id=mid,
                    session_id=str(row["session_id"]),
                    display_thread_id=str(row["display_thread_id"]),
                    title=row["title"],
                    role=str(row["role"]),
                    snippet=snippet,
                    seq=int(row["seq"]),
                    creator_id=row["creator_id"],
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def update_agent_state_json(self, session_id: str, payload: str) -> None:
        now = _utc_now()

        def _update() -> None:
            self._conn.execute(
                """
                UPDATE sessions SET agent_state_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (payload, now, session_id),
            )

        _write_with_retry(self._conn, _update)

    def count_user_messages(self, session_id: str) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS n FROM messages
            WHERE session_id = ? AND role = 'user' AND message_kind = 'normal'
            """,
            (session_id,),
        ).fetchone()
        return int(row["n"]) if row else 0

    def copy_agent_state(self, parent_id: str, child_id: str) -> None:
        parent = self.get_session_row(parent_id)
        if parent is None:
            return
        raw = parent["agent_state_json"]
        if not raw:
            return
        now = _utc_now()

        def _update() -> None:
            self._conn.execute(
                """
                UPDATE sessions SET agent_state_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (raw, now, child_id),
            )

        _write_with_retry(self._conn, _update)


def parse_binding(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
