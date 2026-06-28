# pi-dag-tasks

Lean unified task manager for the Pi coding agent. Ported from TypeScript to Python.

## Overview

This extension provides a DAG (Directed Acyclic Graph) based task management system for pi-coding-agent. Tasks support dependencies, context preservation across conversation compression, and verification nudges.

## Features

- **DAG Dependencies**: Tasks can block or be blocked by other tasks
- **Durable Storage**: Tasks persist across sessions with configurable scope (memory/session/project)
- **Archive System**: Completed tasks can be archived with full history
- **Verification Tracking**: Special handling for verification/testing tasks
- **Batch Operations**: Create, update, complete multiple tasks in one call

## Tools

### `task_manage`

Single unified tool for all task operations:

**Actions:**
- `create` - Create one or more tasks
- `update` - Update task properties
- `complete` - Mark tasks as completed
- `done_archive` - Complete and archive in one step
- `archive` - Archive tasks
- `purge` - Permanently delete tasks
- `list` - List current tasks
- `history` - View archived tasks

**Example - Create tasks:**
```python
{
  "action": "create",
  "creates": [
    {
      "title": "Implement feature",
      "status": "in_progress",
      "context": "Use existing pattern from module X"
    },
    {
      "title": "Write tests",
      "blockedBy": ["1"],
      "metadata": {"kind": "verification"}
    }
  ]
}
```

**Example - Batch complete:**
```python
{
  "action": "complete",
  "ids": ["1", "2", "3"]
}
```

**Example - Search history:**
```python
{
  "action": "history",
  "limit": 20,
  "query": "verification",
  "includeContext": true
}
```

### `task_next`

Get ready (unblocked) tasks:

```python
{
  "limit": 5,
  "includeBlocked": true
}
```

## Commands

### `/tasks`

Interactive command to view current tasks.

## Configuration

Config file: `.pi/dag-tasks/dag-tasks-config.json`

```json
{
  "task_scope": "session",
  "auto_archive_completed": "on_list_complete",
  "animate_active_tasks": false
}
```

**Options:**
- `task_scope`: `"memory"` | `"session"` | `"project"`
- `auto_archive_completed`: `"never"` | `"on_list_complete"` | `"on_task_complete"`
- `animate_active_tasks`: `true` | `false`

## Storage

**Storage modes:**
- `memory` - No persistence
- `session` - `.pi/dag-tasks/tasks-<sessionId>.json` (default)
- `project` - `.pi/dag-tasks/tasks.json`

**Archive:** `.pi/dag-tasks/archive.jsonl`

## Environment Variables

**`PI_DAG_TASKS`** - Override storage location:
- `off` - Memory mode
- `name` - `~/.pi/dag-tasks/name.json`
- `/abs/path.json` - Explicit path
- `./relative.json` - Relative to cwd

## Task Structure

```python
{
  "id": "1",
  "title": "Task title",
  "description": "Optional description",
  "context": "Durable execution context",
  "status": "pending" | "in_progress" | "completed",
  "active_form": "Working on task",
  "owner": "agent-name",
  "blocks": ["2", "3"],
  "blocked_by": [],
  "metadata": {"kind": "verification"},
  "created_at": 1234567890.0,
  "started_at": 1234567890.0,
  "completed_at": 1234567890.0,
  "updated_at": 1234567890.0
}
```

## Dependencies

Tasks use task IDs (e.g., `"1"`, `"2"`) for dependencies, not titles.

**Dependency fields:**
- `blockedBy` - Tasks that must complete first
- `blocks` - Tasks waiting on this one
- `addBlockedBy` / `removeBlockedBy` - Modify blockers
- `addBlocks` / `removeBlocks` - Modify blocking

**Example:**
```python
{
  "action": "update",
  "id": "3",
  "addBlockedBy": ["1", "2"]
}
```

## Task Context

The `context` field stores durable execution instructions:
- Constraints and requirements
- Relevant findings
- Expected inputs/outputs
- Definition of done

Update context only when durable information changes how the task should be done.

## Verification Tasks

For testing/verification tasks, set `metadata.kind = "verification"`:

```python
{
  "title": "Run integration tests",
  "metadata": {"kind": "verification"}
}
```

## Task Sizing Guidelines

- **No task list**: Straightforward work, single-step, under 3 trivial steps
- **Use tasks**: 3+ steps, dependencies, checkpoints, multi-request work
- Size to active execution slice, not whole roadmap
- Avoid microscopic process tasks ("read file", "edit line")
- Keep one task `in_progress` per worker

## Installation

1. Copy the `dag_tasks` directory to your extensions folder:
   - Global: `~/.pi/agent/extensions/dag_tasks/`
   - Local: `<project>/.pi/extensions/dag_tasks/`
   - Or: `<project>/extensions/dag_tasks/`

2. The extension will be automatically loaded on next session start.

## Files

- `__init__.py` - Extension entry point
- `dag_tasks.py` - Main implementation
- `store.py` - Storage and CRUD operations
- `types.py` - Type definitions
- `config.py` - Configuration management

## Differences from TypeScript Version

This Python port maintains feature parity with the original TypeScript version:

- ✅ All task operations (create, update, complete, archive, purge)
- ✅ DAG dependencies with cycle detection
- ✅ File-based persistence with locking
- ✅ Archive system with history search
- ✅ Configuration management
- ✅ Verification task detection
- ❌ UI widgets (not applicable in Python version)
- ❌ Event-based reminders (simplified in Python version)

## Usage Example

```python
# Create tasks with dependencies
await task_manage({
    "action": "create",
    "creates": [
        {
            "title": "Design API",
            "status": "in_progress",
            "context": "RESTful design, follow existing patterns"
        },
        {
            "title": "Implement endpoints",
            "blockedBy": ["1"]
        },
        {
            "title": "Write tests",
            "blockedBy": ["2"],
            "metadata": {"kind": "verification"}
        }
    ]
})

# Check what's ready
await task_next({"limit": 5})

# Complete and archive
await task_manage({
    "action": "done_archive",
    "ids": ["1", "2", "3"]
})

# Search history
await task_manage({
    "action": "history",
    "query": "API",
    "includeContext": true
})
```

## License

MIT
