"""Local tools for the Agent: shell commands, file I/O, directory listing, web search, memory.

These tools are exposed to the LLM via function-calling schemas and executed
safely within the user's workspace.
"""

import os
import subprocess
from pathlib import Path
from typing import Any

from src.agent.memory import MemoryStore
from src.agent.web_tools import execute_web_tool

# Default working directory for commands and file ops.
_WORKSPACE = Path(os.getcwd())

# Global memory store reference, set by main.py
_memory_store = None


def set_memory_store(store):
    global _memory_store
    _memory_store = store


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI-compatible function schemas)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Execute a PowerShell command on the local Windows machine and return its output. "
                "Use for: listing files, running scripts, installing packages, git operations, "
                "reading system info, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The PowerShell command to execute.",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Optional working directory.",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to write to.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content to write into the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a text file and return it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to read.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories in a given directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path. Defaults to workspace root.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web using DuckDuckGo. Returns results with titles, snippets, and URLs. "
                "Use for current events, recent information, or facts not in your training data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (be specific).",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results (1-10, default 5).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": (
                "Fetch and extract text content from a web page. "
                "Use after web_search to read a specific page in detail."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the page to fetch.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Save important information to long-term memory. Use when the user shares facts, "
                "preferences, or context worth remembering across conversations. "
                "Categories: preference, fact, context, note."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The information to remember.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["preference", "fact", "context", "note"],
                        "description": "Type of memory.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keywords for later retrieval.",
                    },
                    "importance": {
                        "type": "number",
                        "description": "Importance 0.0-1.0.",
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
                "Search long-term memory for relevant information. "
                "Use to remember past conversations, user preferences, or context."
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
                        "description": "Optional filter: preference, fact, context, note.",
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
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_path(path):
    p = Path(path)
    if p.is_absolute():
        return p
    return (_WORKSPACE / p).resolve()


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def execute_tool(name, arguments):
    if name == "run_command":
        return _run_command(
            command=arguments.get("command", ""),
            working_dir=arguments.get("working_dir", ""),
        )
    elif name == "write_file":
        return _write_file(
            path=arguments.get("path", ""),
            content=arguments.get("content", ""),
        )
    elif name == "read_file":
        return _read_file(path=arguments.get("path", ""))
    elif name == "list_files":
        return _list_files(path=arguments.get("path", ""))
    elif name in ("web_search", "web_fetch"):
        return execute_web_tool(name, arguments)
    elif name in ("save_memory", "recall_memory", "list_memories", "delete_memory"):
        return _execute_memory_tool(name, arguments)
    else:
        return f"Unknown tool: {name}"


def _execute_memory_tool(name, arguments):
    store = _memory_store
    if store is None:
        return "Error: memory store not initialized."
    if name == "save_memory":
        mid = store.save(
            content=arguments.get("content", ""),
            category=arguments.get("category", "note"),
            tags=arguments.get("tags", []),
            importance=arguments.get("importance", 0.5),
        )
        return f"Memory saved with id: {mid}"
    elif name == "recall_memory":
        results = store.recall(
            query=arguments.get("query", ""),
            top_n=arguments.get("top_n", 5),
        )
        if not results:
            return "No relevant memories found."
        lines = ["Relevant memories:", ""]
        for m in results:
            lines.append(f"  [{m['id']}] ({m['category']}) {m['content']}")
            if m.get("tags"):
                lines.append(f"       tags: {', '.join(m['tags'])}")
            lines.append(f"       created: {m['created_at'][:10]}")
            lines.append("")
        return "\n".join(lines)
    elif name == "list_memories":
        items = store.list_all(category=arguments.get("category"))
        if not items:
            return "No memories stored yet."
        lines = [f"All memories ({len(items)} total):", ""]
        for m in items[:20]:
            lines.append(f"  [{m['id']}] ({m['category']}) {m['content'][:80]}")
        if len(items) > 20:
            lines.append(f"  ... and {len(items) - 20} more")
        return "\n".join(lines)
    elif name == "delete_memory":
        ok = store.delete(arguments.get("memory_id", ""))
        return "Memory deleted." if ok else "Memory not found."
    return f"Unknown memory tool: {name}"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _run_command(command, working_dir=""):
    if not command.strip():
        return "Error: empty command."

    cwd = str(_resolve_path(working_dir)) if working_dir else str(_WORKSPACE)

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cwd,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output += "\n[stderr]\n" + result.stderr.strip()
        if not output:
            output = f"(exit code {result.returncode})"
        return output
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 60 seconds."
    except FileNotFoundError:
        return "Error: PowerShell not found."
    except Exception as exc:
        return f"Error executing command: {exc}"


def _write_file(path, content):
    if not path.strip():
        return "Error: empty path."

    target = _resolve_path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File written: {target}  ({len(content)} bytes)"
    except Exception as exc:
        return f"Error writing file: {exc}"


def _read_file(path):
    if not path.strip():
        return "Error: empty path."

    target = _resolve_path(path)
    if not target.exists():
        return f"Error: file not found: {target}"
    if not target.is_file():
        return f"Error: not a file: {target}"

    try:
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) > 8000:
            content = content[:8000] + f"\n\n... (truncated, {len(content)} total bytes)"
        return content
    except Exception as exc:
        return f"Error reading file: {exc}"


def _list_files(path=""):
    target = _resolve_path(path) if path else _WORKSPACE
    if not target.exists():
        return f"Error: directory not found: {target}"
    if not target.is_dir():
        return f"Error: not a directory: {target}"

    try:
        lines = []
        for entry in sorted(target.iterdir()):
            tag = "[DIR]" if entry.is_dir() else "[FILE]"
            size = ""
            if entry.is_file():
                try:
                    size = f"  ({entry.stat().st_size} bytes)"
                except OSError:
                    pass
            lines.append(f"  {tag}  {entry.name}{size}")
        if not lines:
            return f"Directory is empty: {target}"
        return f"Contents of {target}:\n" + "\n".join(lines)
    except Exception as exc:
        return f"Error listing directory: {exc}"
