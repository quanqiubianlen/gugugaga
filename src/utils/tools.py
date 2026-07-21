"""Local tools for the Agent: shell commands, file I/O, directory listing.

These tools are exposed to the LLM via function-calling schemas and executed
safely within the user's workspace.
"""

import os
import subprocess
from pathlib import Path
from typing import Any

# Default working directory for commands and file ops.
_WORKSPACE = Path(os.getcwd())


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
                "reading system info, etc. The command runs in the user's workspace directory by default."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The PowerShell command to execute (e.g. 'dir', 'git status', 'python script.py').",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Optional working directory. Defaults to the current workspace.",
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
            "description": (
                "Create or overwrite a file with the given content. "
                "The path is relative to the workspace unless an absolute path is given."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to write to (relative or absolute).",
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
                        "description": "File path to read (relative or absolute).",
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
                        "description": "Directory path. Defaults to the workspace root.",
                    },
                },
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_path(path: str) -> Path:
    """Resolve a user-supplied path relative to the workspace."""
    p = Path(path)
    if p.is_absolute():
        return p
    return (_WORKSPACE / p).resolve()


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute a named tool with the given arguments and return the result string."""
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
    else:
        return f"Unknown tool: {name}"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _run_command(command: str, working_dir: str = "") -> str:
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


def _write_file(path: str, content: str) -> str:
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


def _read_file(path: str) -> str:
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
        # Truncate if too large (max ~8000 chars)
        if len(content) > 8000:
            content = content[:8000] + f"\n\n... (truncated, {len(content)} total bytes)"
        return content
    except Exception as exc:
        return f"Error reading file: {exc}"


def _list_files(path: str = "") -> str:
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

