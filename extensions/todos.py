"""
Todo Management Extension for pi-coding-agent

This extension stores todo items as files under .pi/todos (or PI_TODO_PATH).
Each todo is a standalone markdown file named <id>.md with JSON frontmatter.

File format:
{
  "id": "deadbeef",
  "title": "Add tests",
  "tags": ["qa"],
  "status": "open",
  "created_at": "2026-01-25T17:00:00.000Z",
  "assigned_to_session": "session.json"
}

Notes about the work go here.

Settings are kept in .pi/todos/settings.json:
{
  "gc": true,      # delete closed todos older than gcDays
  "gcDays": 7      # age threshold for GC (days since created_at)
}
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# Constants
TODO_DIR_NAME = ".pi/todos"
TODO_PATH_ENV = "PI_TODO_PATH"
TODO_SETTINGS_NAME = "settings.json"
TODO_ID_PREFIX = "TODO-"
TODO_ID_PATTERN = re.compile(r"^[a-f0-9]{8}$", re.IGNORECASE)
DEFAULT_TODO_SETTINGS = {
    "gc": True,
    "gcDays": 7,
}
LOCK_TTL_MS = 30 * 60 * 1000  # 30 minutes


@dataclass
class TodoFrontMatter:
    """Todo metadata stored in JSON frontmatter."""
    id: str
    title: str
    tags: list[str] = field(default_factory=list)
    status: str = "open"
    created_at: str = ""
    assigned_to_session: Optional[str] = None


@dataclass
class TodoRecord(TodoFrontMatter):
    """Complete todo with body text."""
    body: str = ""


@dataclass
class TodoSettings:
    """Settings for todo storage."""
    gc: bool = True
    gcDays: int = 7


@dataclass
class LockInfo:
    """Information about a todo lock."""
    id: str
    pid: int
    session: Optional[str] = None
    created_at: str = ""


# ============================================================================
# Helper Functions
# ============================================================================

def format_todo_id(id: str) -> str:
    """Format todo ID with prefix."""
    return f"{TODO_ID_PREFIX}{id}"


def normalize_todo_id(id: str) -> str:
    """Normalize todo ID by removing prefix and #."""
    trimmed = id.strip()
    if trimmed.startswith("#"):
        trimmed = trimmed[1:]
    if trimmed.upper().startswith(TODO_ID_PREFIX):
        trimmed = trimmed[len(TODO_ID_PREFIX):]
    return trimmed.lower()


def validate_todo_id(id: str) -> dict[str, str]:
    """Validate todo ID format."""
    normalized = normalize_todo_id(id)
    if not normalized or not TODO_ID_PATTERN.match(normalized):
        return {"error": "Invalid todo id. Expected TODO-<hex>."}
    return {"id": normalized}


def display_todo_id(id: str) -> str:
    """Display formatted todo ID."""
    return format_todo_id(normalize_todo_id(id))


def is_todo_closed(status: str) -> bool:
    """Check if todo status is closed."""
    return status.lower() in ["closed", "done"]


def clear_assignment_if_closed(todo: TodoFrontMatter) -> None:
    """Clear assignment if todo is closed."""
    if is_todo_closed(todo.status):
        todo.assigned_to_session = None


def get_todos_dir(cwd: str) -> str:
    """Get the todos directory path."""
    override_path = os.environ.get(TODO_PATH_ENV, "").strip()
    if override_path:
        return os.path.abspath(os.path.join(cwd, override_path))
    return os.path.abspath(os.path.join(cwd, TODO_DIR_NAME))


def get_todo_path(todos_dir: str, id: str) -> str:
    """Get the file path for a todo."""
    return os.path.join(todos_dir, f"{id}.md")


def get_lock_path(todos_dir: str, id: str) -> str:
    """Get the lock file path for a todo."""
    return os.path.join(todos_dir, f"{id}.lock")


def get_settings_path(todos_dir: str) -> str:
    """Get the settings file path."""
    return os.path.join(todos_dir, TODO_SETTINGS_NAME)


# ============================================================================
# File I/O Functions
# ============================================================================

def find_json_object_end(content: str) -> int:
    """Find the end of a JSON object in content."""
    depth = 0
    in_string = False
    escaped = False

    for i, char in enumerate(content):
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == '{':
            depth += 1
            continue

        if char == '}':
            depth -= 1
            if depth == 0:
                return i

    return -1


def split_front_matter(content: str) -> tuple[str, str]:
    """Split content into frontmatter and body."""
    if not content.startswith("{"):
        return "", content

    end_index = find_json_object_end(content)
    if end_index == -1:
        return "", content

    front_matter = content[:end_index + 1]
    body = content[end_index + 1:].lstrip("\r\n")
    return front_matter, body


def parse_front_matter(text: str, id_fallback: str) -> TodoFrontMatter:
    """Parse JSON frontmatter into TodoFrontMatter."""
    data = TodoFrontMatter(
        id=id_fallback,
        title="",
        tags=[],
        status="open",
        created_at="",
        assigned_to_session=None,
    )

    trimmed = text.strip()
    if not trimmed:
        return data

    try:
        parsed = json.loads(trimmed)
        if not isinstance(parsed, dict):
            return data

        if isinstance(parsed.get("id"), str) and parsed["id"]:
            data.id = parsed["id"]
        if isinstance(parsed.get("title"), str):
            data.title = parsed["title"]
        if isinstance(parsed.get("status"), str) and parsed["status"]:
            data.status = parsed["status"]
        if isinstance(parsed.get("created_at"), str):
            data.created_at = parsed["created_at"]
        if isinstance(parsed.get("assigned_to_session"), str) and parsed["assigned_to_session"].strip():
            data.assigned_to_session = parsed["assigned_to_session"]
        if isinstance(parsed.get("tags"), list):
            data.tags = [tag for tag in parsed["tags"] if isinstance(tag, str)]

    except (json.JSONDecodeError, TypeError):
        pass

    return data


def parse_todo_content(content: str, id_fallback: str) -> TodoRecord:
    """Parse todo file content into TodoRecord."""
    front_matter, body = split_front_matter(content)
    parsed = parse_front_matter(front_matter, id_fallback)

    return TodoRecord(
        id=id_fallback,
        title=parsed.title,
        tags=parsed.tags,
        status=parsed.status,
        created_at=parsed.created_at,
        assigned_to_session=parsed.assigned_to_session,
        body=body,
    )


def serialize_todo(todo: TodoRecord) -> str:
    """Serialize TodoRecord to file content."""
    front_matter = json.dumps(
        {
            "id": todo.id,
            "title": todo.title,
            "tags": todo.tags,
            "status": todo.status,
            "created_at": todo.created_at,
            "assigned_to_session": todo.assigned_to_session or None,
        },
        indent=2,
    )

    body = (todo.body or "").strip()
    if not body:
        return f"{front_matter}\n"
    return f"{front_matter}\n\n{body}\n"


async def ensure_todos_dir(todos_dir: str) -> None:
    """Ensure todos directory exists."""
    os.makedirs(todos_dir, exist_ok=True)


async def read_todo_file(file_path: str, id_fallback: str) -> TodoRecord:
    """Read a todo file."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return parse_todo_content(content, id_fallback)


async def write_todo_file(file_path: str, todo: TodoRecord) -> None:
    """Write a todo file."""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(serialize_todo(todo))
    os.chmod(file_path, 0o600)


async def generate_todo_id(todos_dir: str) -> str:
    """Generate a unique todo ID."""
    for _ in range(10):
        id = secrets.token_hex(4)
        todo_path = get_todo_path(todos_dir, id)
        if not os.path.exists(todo_path):
            return id
    raise Exception("Failed to generate unique todo id")


# ============================================================================
# Settings Functions
# ============================================================================

async def read_todo_settings(todos_dir: str) -> TodoSettings:
    """Read todo settings from file."""
    settings_path = get_settings_path(todos_dir)
    data = {}

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    gc = data.get("gc", DEFAULT_TODO_SETTINGS["gc"])
    gc_days = data.get("gcDays", DEFAULT_TODO_SETTINGS["gcDays"])

    return TodoSettings(
        gc=bool(gc),
        gcDays=max(0, int(gc_days)) if isinstance(gc_days, (int, float)) else DEFAULT_TODO_SETTINGS["gcDays"],
    )


# ============================================================================
# Garbage Collection
# ============================================================================

async def garbage_collect_todos(todos_dir: str, settings: TodoSettings) -> None:
    """Delete old closed todos based on settings."""
    if not settings.gc:
        return

    try:
        entries = os.listdir(todos_dir)
    except FileNotFoundError:
        return

    cutoff = datetime.now() - timedelta(days=settings.gcDays)

    for entry in entries:
        if not entry.endswith(".md"):
            continue

        id = entry[:-3]
        file_path = os.path.join(todos_dir, entry)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            front_matter, _ = split_front_matter(content)
            parsed = parse_front_matter(front_matter, id)

            if not is_todo_closed(parsed.status):
                continue

            try:
                created_at = datetime.fromisoformat(parsed.created_at.replace("Z", "+00:00"))
                if created_at < cutoff:
                    os.unlink(file_path)
            except (ValueError, AttributeError):
                continue

        except Exception:
            continue


# ============================================================================
# Lock Management
# ============================================================================

async def read_lock_info(lock_path: str) -> Optional[LockInfo]:
    """Read lock information from file."""
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return LockInfo(
            id=data.get("id", ""),
            pid=data.get("pid", 0),
            session=data.get("session"),
            created_at=data.get("created_at", ""),
        )
    except Exception:
        return None


# ============================================================================
# Todo Operations
# ============================================================================

async def list_todos(todos_dir: str) -> list[TodoFrontMatter]:
    """List all todos in directory."""
    try:
        entries = os.listdir(todos_dir)
    except FileNotFoundError:
        return []

    todos: list[TodoFrontMatter] = []

    for entry in entries:
        if not entry.endswith(".md"):
            continue

        id = entry[:-3]
        file_path = os.path.join(todos_dir, entry)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            front_matter, _ = split_front_matter(content)
            parsed = parse_front_matter(front_matter, id)

            todos.append(TodoFrontMatter(
                id=id,
                title=parsed.title,
                tags=parsed.tags,
                status=parsed.status,
                created_at=parsed.created_at,
                assigned_to_session=parsed.assigned_to_session,
            ))
        except Exception:
            continue

    # Sort: open assigned first, then open unassigned, then closed
    def sort_key(todo: TodoFrontMatter) -> tuple:
        closed = is_todo_closed(todo.status)
        assigned = bool(todo.assigned_to_session) and not closed
        return (closed, not assigned, todo.created_at or "")

    return sorted(todos, key=sort_key)


def split_todos_by_assignment(todos: list[TodoFrontMatter]) -> dict[str, list[TodoFrontMatter]]:
    """Split todos into assigned, open, and closed categories."""
    assigned_todos = []
    open_todos = []
    closed_todos = []

    for todo in todos:
        if is_todo_closed(todo.status):
            closed_todos.append(todo)
        elif todo.assigned_to_session:
            assigned_todos.append(todo)
        else:
            open_todos.append(todo)

    return {
        "assigned": assigned_todos,
        "open": open_todos,
        "closed": closed_todos,
    }


def serialize_todo_for_agent(todo: TodoRecord) -> str:
    """Serialize todo for agent response."""
    payload = {
        "id": format_todo_id(todo.id),
        "title": todo.title,
        "tags": todo.tags,
        "status": todo.status,
        "created_at": todo.created_at,
        "assigned_to_session": todo.assigned_to_session,
        "body": todo.body,
    }
    return json.dumps(payload, indent=2)


def serialize_todo_list_for_agent(todos: list[TodoFrontMatter]) -> str:
    """Serialize todo list for agent response."""
    split = split_todos_by_assignment(todos)

    def map_todo(todo: TodoFrontMatter) -> dict:
        return {
            "id": format_todo_id(todo.id),
            "title": todo.title,
            "tags": todo.tags,
            "status": todo.status,
            "created_at": todo.created_at,
            "assigned_to_session": todo.assigned_to_session,
        }

    return json.dumps(
        {
            "assigned": [map_todo(t) for t in split["assigned"]],
            "open": [map_todo(t) for t in split["open"]],
            "closed": [map_todo(t) for t in split["closed"]],
        },
        indent=2,
    )


# ============================================================================
# Extension Factory
# ============================================================================

def extension_factory(pi):
    """Main entry point for the todos extension."""

    # Register session_start handler for initialization
    async def on_session_start(event, ctx):
        """Initialize todos directory and run GC on session start."""
        todos_dir = get_todos_dir(ctx.cwd)
        await ensure_todos_dir(todos_dir)
        settings = await read_todo_settings(todos_dir)
        await garbage_collect_todos(todos_dir, settings)

    pi.on("session_start", on_session_start)

    # Register the todo tool
    async def execute_todo(args: dict[str, Any]) -> dict[str, Any]:
        """Execute todo tool actions."""
        # Note: ctx would be passed from the tool execution context
        # For now, using current directory
        cwd = os.getcwd()
        todos_dir = get_todos_dir(cwd)
        action = args.get("action", "")

        try:
            if action == "list":
                todos = await list_todos(todos_dir)
                split = split_todos_by_assignment(todos)
                listed_todos = split["assigned"] + split["open"]
                return {
                    "success": True,
                    "content": serialize_todo_list_for_agent(listed_todos),
                    "details": {"action": "list", "todos": listed_todos},
                }

            elif action == "list-all":
                todos = await list_todos(todos_dir)
                return {
                    "success": True,
                    "content": serialize_todo_list_for_agent(todos),
                    "details": {"action": "list-all", "todos": todos},
                }

            elif action == "get":
                id = args.get("id")
                if not id:
                    return {"error": "id required"}

                validated = validate_todo_id(id)
                if "error" in validated:
                    return {"error": validated["error"]}

                normalized_id = validated["id"]
                file_path = get_todo_path(todos_dir, normalized_id)

                if not os.path.exists(file_path):
                    return {"error": f"Todo {display_todo_id(id)} not found"}

                todo = await read_todo_file(file_path, normalized_id)
                return {
                    "success": True,
                    "content": serialize_todo_for_agent(todo),
                    "details": {"action": "get", "todo": todo},
                }

            elif action == "create":
                title = args.get("title")
                if not title:
                    return {"error": "title required"}

                await ensure_todos_dir(todos_dir)
                id = await generate_todo_id(todos_dir)
                file_path = get_todo_path(todos_dir, id)

                todo = TodoRecord(
                    id=id,
                    title=title,
                    tags=args.get("tags", []),
                    status=args.get("status", "open"),
                    created_at=datetime.utcnow().isoformat() + "Z",
                    body=args.get("body", ""),
                )

                await write_todo_file(file_path, todo)
                return {
                    "success": True,
                    "content": serialize_todo_for_agent(todo),
                    "details": {"action": "create", "todo": todo},
                }

            elif action == "update":
                id = args.get("id")
                if not id:
                    return {"error": "id required"}

                validated = validate_todo_id(id)
                if "error" in validated:
                    return {"error": validated["error"]}

                normalized_id = validated["id"]
                file_path = get_todo_path(todos_dir, normalized_id)

                if not os.path.exists(file_path):
                    return {"error": f"Todo {display_todo_id(id)} not found"}

                todo = await read_todo_file(file_path, normalized_id)

                if "title" in args:
                    todo.title = args["title"]
                if "status" in args:
                    todo.status = args["status"]
                if "tags" in args:
                    todo.tags = args["tags"]
                if "body" in args:
                    todo.body = args["body"]

                clear_assignment_if_closed(todo)
                await write_todo_file(file_path, todo)

                return {
                    "success": True,
                    "content": serialize_todo_for_agent(todo),
                    "details": {"action": "update", "todo": todo},
                }

            elif action == "delete":
                id = args.get("id")
                if not id:
                    return {"error": "id required"}

                validated = validate_todo_id(id)
                if "error" in validated:
                    return {"error": validated["error"]}

                normalized_id = validated["id"]
                file_path = get_todo_path(todos_dir, normalized_id)

                if not os.path.exists(file_path):
                    return {"error": f"Todo {display_todo_id(id)} not found"}

                todo = await read_todo_file(file_path, normalized_id)
                os.unlink(file_path)

                return {
                    "success": True,
                    "content": serialize_todo_for_agent(todo),
                    "details": {"action": "delete", "todo": todo},
                }

            else:
                return {"error": f"Unknown action: {action}"}

        except Exception as e:
            return {"error": str(e)}

    pi.register_tool(
        name="todo",
        description=(
            "Manage file-based todos in .pi/todos (list, list-all, get, create, update, delete). "
            "Title is the short summary; body is long-form markdown notes. "
            "Todo ids are shown as TODO-<hex>; id parameters accept TODO-<hex> or the raw hex filename."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "list-all", "get", "create", "update", "delete"],
                    "description": "Action to perform",
                },
                "id": {
                    "type": "string",
                    "description": "Todo id (TODO-<hex> or raw hex filename)",
                },
                "title": {
                    "type": "string",
                    "description": "Short summary shown in lists",
                },
                "status": {
                    "type": "string",
                    "description": "Todo status (open, closed, done, etc.)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Todo tags",
                },
                "body": {
                    "type": "string",
                    "description": "Long-form details (markdown)",
                },
            },
            "required": ["action"],
        },
        execute=execute_todo,
    )

    # Register /todos command
    async def todos_command_handler(args: str) -> None:
        """Handle /todos command."""
        cwd = os.getcwd()
        todos_dir = get_todos_dir(cwd)
        todos = await list_todos(todos_dir)

        if not todos:
            print("No todos found.")
            return

        split = split_todos_by_assignment(todos)

        def format_section(label: str, items: list[TodoFrontMatter]) -> None:
            print(f"\n{label} ({len(items)}):")
            if not items:
                print("  none")
                return
            for todo in items:
                tags = f" [{', '.join(todo.tags)}]" if todo.tags else ""
                assignment = f" (assigned: {todo.assigned_to_session})" if todo.assigned_to_session else ""
                print(f"  {format_todo_id(todo.id)} {todo.title}{tags}{assignment}")

        format_section("Assigned todos", split["assigned"])
        format_section("Open todos", split["open"])
        format_section("Closed todos", split["closed"])

    pi.register_command(
        name="todos",
        description="List todos from .pi/todos",
        handler=todos_command_handler,
    )
