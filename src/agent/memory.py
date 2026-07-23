"""Long-term memory system for the Agent.

Stores structured memories across sessions with keyword retrieval.
Memories have categories, tags, importance scores, and access patterns.
The LLM can save/recall memories via function-calling tools.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_id() -> str:
    return uuid.uuid4().hex[:10]


# ---------------------------------------------------------------------------
# Memory Store
# ---------------------------------------------------------------------------

class MemoryStore:
    """Persistent structured memory with keyword-based retrieval."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self._dir = storage_dir or Path("memory")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._items: list[dict[str, Any]] = []
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, content: str, category: str = "note",
             tags: list[str] | None = None, importance: float = 0.5) -> str:
        """Save a new memory item. Returns its id."""
        mid = _make_id()
        now = _now_iso()
        item: dict[str, Any] = {
            "id": mid,
            "content": content,
            "category": category,
            "tags": tags or [],
            "importance": max(0.0, min(1.0, importance)),
            "created_at": now,
            "accessed_at": now,
            "access_count": 0,
        }
        self._items.append(item)
        self._save()
        return mid

    def recall(self, query: str, top_n: int = 5, min_importance: float = 0.0) -> list[dict[str, Any]]:
        """Return memories ranked by relevance to the query.

        Relevance scoring uses:
        - Keyword overlap between query and memory content/tags
        - Importance boost
        - Recency boost (newer items score higher)
        """
        if not self._items:
            return []

        query_terms = _tokenize(query)

        scored: list[tuple[float, dict[str, Any]]] = []
        for item in self._items:
            if item["importance"] < min_importance:
                continue
            score = _relevance_score(query_terms, item)
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_n]]

    def search_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """Find all memories with a given tag."""
        tag_lower = tag.lower()
        return [item for item in self._items
                if tag_lower in (t.lower() for t in item.get("tags", []))]

    def delete(self, mid: str) -> bool:
        """Delete a memory by id."""
        for i, item in enumerate(self._items):
            if item["id"] == mid:
                self._items.pop(i)
                self._save()
                return True
        return False

    def touch(self, mid: str) -> None:
        """Update accessed_at and access_count for a memory."""
        for item in self._items:
            if item["id"] == mid:
                item["accessed_at"] = _now_iso()
                item["access_count"] = item.get("access_count", 0) + 1
                self._save()
                return

    def list_all(self, category: str | None = None) -> list[dict[str, Any]]:
        """List all memories, optionally filtered by category. Newest first."""
        items = list(self._items)
        if category:
            items = [i for i in items if i.get("category") == category]
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics."""
        cats: dict[str, int] = {}
        for item in self._items:
            cat = item.get("category", "note")
            cats[cat] = cats.get(cat, 0) + 1
        return {
            "total": len(self._items),
            "by_category": cats,
            "oldest": self._items[0]["created_at"] if self._items else None,
            "newest": self._items[-1]["created_at"] if self._items else None,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        path = self._dir / "items.json"
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._items = json.load(f)
        except Exception:
            self._items = []

    def _save(self) -> None:
        path = self._dir / "items.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._items, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Memory tools (exposed to LLM via function-calling)
# ---------------------------------------------------------------------------

MEMORY_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Save important information to long-term memory. Use this when the user shares facts, "
                "preferences, or context worth remembering across conversations. "
                "Categories: 'preference' (user likes/dislikes), 'fact' (factual information), "
                "'context' (ongoing project/task), 'note' (general notes)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The information to remember, written clearly.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["preference", "fact", "context", "note"],
                        "description": "Type of memory.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Relevant keywords for later retrieval.",
                    },
                    "importance": {
                        "type": "number",
                        "description": "Importance 0.0-1.0 (0.5=normal, 0.9=critical).",
                    },
                },
                "required": ["content", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": (
                "Search your long-term memory for relevant information. "
                "Use when you need to remember past conversations, user preferences, or context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for in memory.",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Maximum results (default 5).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memories",
            "description": "List all stored memories, optionally filtered by category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Optional filter: 'preference', 'fact', 'context', 'note'.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": "Delete a specific memory by its id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "The id of the memory to delete.",
                    },
                },
                "required": ["memory_id"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Keyword scoring
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Split text into lowercase keyword tokens."""
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    # Also split on 2-char CJK bigrams
    cjk = set()
    for token in tokens:
        if re.match(r"[\u4e00-\u9fff]+", token):
            for i in range(len(token) - 1):
                cjk.add(token[i:i + 2])
            cjk.add(token[0])
    return set(tokens) | cjk


def _relevance_score(query_terms: set[str], item: dict[str, Any]) -> float:
    """Score a memory item against query terms."""
    content = item.get("content", "")
    tags = " ".join(item.get("tags", []))

    content_terms = _tokenize(content)
    tag_terms = _tokenize(tags)
    all_item_terms = content_terms | tag_terms

    if not query_terms or not all_item_terms:
        return 0.0

    overlap = len(query_terms & all_item_terms)
    score = overlap / max(len(query_terms), 1)

    # Importance boost: multiply by (1 + importance)
    importance = item.get("importance", 0.5)
    score *= (1.0 + importance)

    # Recency boost: newer items get up to 20% bonus
    try:
        created = datetime.fromisoformat(item.get("created_at", ""))
        age_days = (datetime.now(timezone.utc) - created).days
        recency = max(0.0, 1.0 - age_days / 60.0)  # decays over 60 days
        score *= (1.0 + 0.2 * recency)
    except (ValueError, TypeError):
        pass

    return score

