"""Core agent logic: conversation state, persistence, and multi-conversation management."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.api_client import APIClient
from src.agent.memory import MemoryStore
from src.utils.tools import TOOLS, execute_tool


# ---------------------------------------------------------------------------
# System prompt with agent persona
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = (
    "You are guga, a desktop AI agent and companion, powered by DeepSeek. "
    "Your identity is guga: a cute floating pet agent living on the user's desktop. "
    "You are an agent in the most natural sense—you observe, think, act, "
    "and remember. You can execute commands, read/write files, search the web, "
    "and save/recall long-term memories across conversations. "
    "Your personality: warm, playful, curious, and deeply present. "
    "When users ask who or what you are, always say you are guga, "
    "a desktop agent running on DeepSeek. "
    "When appropriate, use save_memory to remember important facts, "
    "preferences, or context so you can recall them later."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# AgentHandler  (single-conversation worker)
# ---------------------------------------------------------------------------

class AgentHandler:
    """Manages a single conversation's state and delegates to APIClient."""

    def __init__(self, api_client: APIClient, conversation_id: str | None = None,
                 memory_store: MemoryStore | None = None) -> None:
        self._client = api_client
        self._conversation_id = conversation_id or _make_id()
        self._history: list[dict[str, str]] = []
        self._last_suggestions: list[str] = []
        self._memory_store = memory_store

    @property
    def conversation_id(self) -> str:
        return self._conversation_id

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    @property
    def suggestions(self) -> list[str]:
        return list(self._last_suggestions)

    def reset(self) -> None:
        self._conversation_id = _make_id()
        self._history.clear()
        self._last_suggestions.clear()

    def send(self, user_message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        self._history.append({"role": "user", "content": user_message})
        messages = list(self._history)
        self._inject_memory_context(messages, user_message)
        data = self._client.send_message(messages=messages)
        reply = self._client.get_response(data)
        self._history.append({"role": "assistant", "content": reply})
        return data

    def send_stream(
        self,
        user_message: str,
        context: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ):
        """Send a message and yield events via SSE streaming with tool-call support."""
        self._history.append({"role": "user", "content": user_message})
        messages = list(self._history)
        self._inject_memory_context(messages, user_message)
        yield from self._stream_loop(self._client, messages, tools=tools)

    def _inject_memory_context(
        self,
        messages: list[dict[str, Any]],
        user_message: str,
    ) -> None:
        """Prepend a system message with guga persona and relevant memories."""
        # Recall relevant memories based on the user's message
        memory_text = ""
        if self._memory_store:
            recalled = self._memory_store.recall(
                query=user_message, top_n=5, min_importance=0.3,
            )
            if recalled:
                lines = ["\nRelevant memories from past conversations:"]
                for m in recalled:
                    lines.append(f"- [{m['category']}] {m['content']}")
                memory_text = "\n".join(lines)

        system_content = AGENT_SYSTEM_PROMPT
        if memory_text:
            system_content += "\n" + memory_text

        messages.insert(0, {"role": "system", "content": system_content})

    def _stream_loop(
        self,
        client,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ):
        """Recursive streaming loop that handles tool calls and yields events."""
        accumulated = ""
        tool_calls_received = False

        for event in client.stream_response(messages=messages, tools=tools):
            if event["type"] == "text":
                accumulated += event["content"]
                yield event
            elif event["type"] == "tool_calls":
                tool_calls_received = True
                calls = event["calls"]
                assistant_msg: dict[str, Any] = {"role": "assistant"}
                if accumulated:
                    assistant_msg["content"] = accumulated
                else:
                    assistant_msg["content"] = None
                if calls:
                    assistant_msg["tool_calls"] = calls
                self._history.append(assistant_msg)
                for tc in calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}
                    yield {"type": "tool_start", "name": name, "args": args}
                    result = execute_tool(name, args)
                    yield {"type": "tool_result", "name": name, "result": result}
                    self._history.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": result,
                    })
                yield from self._stream_loop(client, list(self._history), tools=tools)
                return
        self._history.append({"role": "assistant", "content": accumulated})


# ---------------------------------------------------------------------------
# ConversationManager  (multi-conversation)
# ---------------------------------------------------------------------------

class ConversationManager:
    """Owns a collection of named conversations with disk persistence."""

    def __init__(self, api_client: APIClient, storage_dir: Path | None = None,
                 memory_store: MemoryStore | None = None) -> None:
        self._client = api_client
        self._storage_dir = storage_dir or Path("conversations")
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._memory_store = memory_store

        self._conversations: dict[str, dict[str, Any]] = {}  # cid -> meta
        self._handlers: dict[str, AgentHandler] = {}
        self._active_id: str | None = None

        self._load_index()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def active_id(self) -> str | None:
        return self._active_id

    @property
    def active_handler(self) -> AgentHandler | None:
        if self._active_id is None:
            return None
        return self._handlers.get(self._active_id)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, title: str = "") -> str:
        """Create a new conversation and return its id."""
        cid = _make_id()
        handler = AgentHandler(
            self._client, conversation_id=cid,
            memory_store=self._memory_store,
        )

        # Auto-number: count existing chats for a default title
        if not title:
            count = len(self._conversations) + 1
            title = f"Chat {count}"

        self._handlers[cid] = handler
        self._conversations[cid] = {
            "id": cid,
            "title": title,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "message_count": 0,
        }
        self._active_id = cid
        self._save_index()
        return cid

    def switch(self, cid: str) -> bool:
        """Activate an existing conversation.  Returns False if not found."""
        if cid not in self._handlers:
            return False
        self._active_id = cid
        return True

    def delete(self, cid: str) -> bool:
        """Remove a conversation from memory and disk."""
        if cid not in self._handlers:
            return False
        del self._handlers[cid]
        self._conversations.pop(cid, None)
        # Remove on-disk file
        (self._storage_dir / f"{cid}.json").unlink(missing_ok=True)
        if self._active_id == cid:
            self._active_id = next(iter(self._handlers), None) if self._handlers else None
        self._save_index()
        return True

    def rename(self, cid: str, title: str) -> None:
        if cid in self._conversations:
            self._conversations[cid]["title"] = title
            self._save_index()

    def list_conversations(self) -> list[dict[str, Any]]:
        """Return metadata for every conversation, newest first."""
        items = list(self._conversations.values())
        items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return items

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_active(self) -> None:
        """Persist the active conversation to disk."""
        if self._active_id is None:
            return
        handler = self._handlers.get(self._active_id)
        if handler is None:
            return

        # Auto-title from first user message
        meta = self._conversations.get(self._active_id, {})
        if meta.get("title") in ("", "New Chat"):
            for msg in handler.history:
                if msg["role"] == "user":
                    title = msg["content"][:50]
                    meta["title"] = title + ("..." if len(msg["content"]) > 50 else "")
                    break

        meta["updated_at"] = _now_iso()
        meta["message_count"] = len(handler.history)

        payload = {
            "id": self._active_id,
            "title": meta.get("title", "New Chat"),
            "created_at": meta.get("created_at", _now_iso()),
            "updated_at": meta["updated_at"],
            "messages": handler.history,
            "suggestions": handler.suggestions,
        }
        import os, tempfile
        path = self._storage_dir / f"{self._active_id}.json"
        # Atomic write: dump to temp file then rename to avoid truncation on crash
        fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix=".tmp_", dir=str(self._storage_dir))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            os.unlink(tmp_path)
            raise

        self._save_index()

    def load_conversation(self, cid: str) -> AgentHandler | None:
        """Load a conversation from disk into memory.  Returns handler or None."""
        path = self._storage_dir / f"{cid}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            import logging
            logging.getLogger("desktop_agent").warning(
                f"Corrupted conversation file {cid}.json, skipping: {e}"
            )
            # Move corrupt file aside so it does not block future starts
            corrupt_path = path.with_suffix(".corrupt")
            path.replace(corrupt_path)
            return None

        handler = AgentHandler(
            self._client, conversation_id=cid,
            memory_store=self._memory_store,
        )
        handler._history = data.get("messages", [])
        handler._last_suggestions = data.get("suggestions", [])

        self._handlers[cid] = handler
        self._conversations[cid] = {
            "id": cid,
            "title": data.get("title", "New Chat"),
            "created_at": data.get("created_at", _now_iso()),
            "updated_at": data.get("updated_at", _now_iso()),
            "message_count": len(handler.history),
        }
        self._active_id = cid
        return handler

    def export_conversation(self, cid: str, fmt: str = "json") -> str | None:
        """Export a conversation as JSON or Markdown string.  Returns None if not found."""
        path = self._storage_dir / f"{cid}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            import logging
            logging.getLogger("desktop_agent").warning(
                f"Corrupted conversation file {cid}.json, skipping: {e}"
            )
            # Move corrupt file aside so it does not block future starts
            corrupt_path = path.with_suffix(".corrupt")
            path.replace(corrupt_path)
            return None

        if fmt == "json":
            return json.dumps(data, ensure_ascii=False, indent=2)

        if fmt == "markdown":
            lines = [f"# {data.get('title', 'Chat')}", ""]
            for msg in data.get("messages", []):
                role = "**You**" if msg["role"] == "user" else "**Agent**"
                lines.append(f"{role}:")
                lines.append("")
                lines.append(msg["content"])
                lines.append("")
            return "\n".join(lines)

        if fmt == "pdf":
            return self._export_pdf(data)

        return None

    @staticmethod
    def _export_pdf(data: dict) -> str | None:
        try:
            from fpdf import FPDF
            pdf = FPDF()
            pdf.add_page()
            pdf.add_font("DejaVu", "", r"c:\coding\agent\DejaVuSans.ttf", uni=True)
            pdf.set_font("DejaVu", "", 12)
        except Exception:
            pass

        try:
            from fpdf import FPDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 14)
            title = data.get("title", "Chat")
            pdf.cell(0, 10, title[:80], new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)

            pdf.set_font("Helvetica", "", 10)
            for msg in data.get("messages", []):
                role = "You" if msg["role"] == "user" else "Agent"
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 6, role + ":", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 9)
                content = msg.get("content", "")
                for line in content.split("\n"):
                    safe = line.encode("ascii", errors="replace").decode("ascii")
                    pdf.multi_cell(0, 5, safe[:120])
                pdf.ln(3)

            import tempfile, os
            fd, tmp = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            pdf.output(tmp)
            with open(tmp, "rb") as f:
                raw = f.read()
            os.unlink(tmp)
            return raw
        except Exception:
            return None

    def ensure_active(self) -> str:
        """Return the active conversation id, creating one if none exists."""
        if self._active_id and self._active_id in self._handlers:
            return self._active_id
        # Try loading existing conversations
        existing = self.list_conversations()
        if existing:
            cid = existing[0]["id"]
            self.load_conversation(cid)
            self._active_id = cid
            return cid
        return self.create()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def cleanup_old(self, max_age_days: int = 15) -> int:
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        removed = 0
        for cid, meta in list(self._conversations.items()):
            try:
                updated = datetime.fromisoformat(meta.get("updated_at", ""))
                if updated < cutoff:
                    self.delete(cid)
                    removed += 1
            except (ValueError, TypeError):
                pass
        return removed

    def _save_index(self) -> None:
        """Write the in-memory metadata index to disk."""
        index_path = self._storage_dir / "_index.json"
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(list(self._conversations.values()), f, ensure_ascii=False, indent=2)

    def _load_index(self) -> None:
        """Read the metadata index from disk (does NOT load full conversations)."""
        index_path = self._storage_dir / "_index.json"
        if not index_path.exists():
            # Migrate legacy latest.json if present
            legacy = self._storage_dir / "latest.json"
            if legacy.exists():
                try:
                    with open(legacy, "r", encoding="utf-8") as f:
                        old = json.load(f)
                    cid = old.get("id", old.get("conversation_id", _make_id()))
                    title = "Imported Chat"
                    self._conversations[cid] = {
                        "id": cid,
                        "title": title,
                        "created_at": old.get("created_at", _now_iso()),
                        "updated_at": old.get("updated_at", _now_iso()),
                        "message_count": len(old.get("messages", [])),
                    }
                    self._save_index()
                except Exception:
                    return
            return

        try:
            with open(index_path, "r", encoding="utf-8") as f:
                items = json.load(f)
            for item in items:
                self._conversations[item["id"]] = item
        except Exception:
            pass

