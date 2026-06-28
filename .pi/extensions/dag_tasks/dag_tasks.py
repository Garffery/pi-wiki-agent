"""
DAG Tasks Extension - Main implementation

A lean unified task manager with DAG dependencies for pi-coding-agent.
Ported from the TypeScript pi-dag-tasks extension.
"""
from __future__ import annotations

import os
import time
from typing import Any

from .config import load_config, save_config
from .store import DagTaskStore
from .types import (
    DagTask,
    DagTasksConfig,
    TaskManageResultDetails,
    TaskNextResultDetails,
    TaskOperation,
)

# Constants
VERIFICATION_TERMS = [
    "test", "tests", "tested", "testing",
    "verify", "verified", "verification",
    "check", "checked", "sanity check",
    "review", "reviewed",
    "lint", "linted",
    "typecheck", "type check", "tsc",
    "build", "built",
    "compile", "compiled",
    "validate", "validated",
    "smoke test",
    "manual test",
    "qa",
]


def status_icon(status: str) -> str:
    """Get icon for task status."""
    if status == "completed":
        return "✔"
    elif status == "in_progress":
        return "◼"
    else:
        return "◻"


def truncate_text(text: str, max_len: int = 600) -> str:
    """Truncate text to max length."""
    return text[:max_len - 1] + "…" if len(text) > max_len else text


def format_duration(ms: float) -> str:
    """Format duration in milliseconds."""
    seconds = max(0, int(ms / 1000))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    rem = seconds % 60
    if minutes < 60:
        return f"{minutes}m {rem}s" if rem else f"{minutes}m"
    hours = minutes // 60
    rem_min = minutes % 60
    return f"{hours}h {rem_min}m" if rem_min else f"{hours}h"


def format_reminder_duration(ms: float) -> str:
    """Format duration for reminders."""
    minutes = max(1, int(ms / 60000))
    if minutes < 60:
        return f"~{minutes}m"
    hours = minutes // 60
    rem = minutes % 60
    return f"~{hours}h {rem}m" if rem else f"~{hours}h"


def normalize_verification_text(text: str) -> str:
    """Normalize text for verification checking."""
    import re
    return re.sub(r'[_-]+', ' ', text.lower())


def task_search_text(task: DagTask) -> str:
    """Get searchable text from task."""
    import json
    parts = [
        task.title,
        task.description,
        task.context or "",
        task.active_form or "",
        json.dumps(task.metadata),
    ]
    return '\n'.join(p for p in parts if p)


def has_verification_signal(task: DagTask) -> bool:
    """Check if task has verification signal."""
    if task.metadata.get('kind') == 'verification':
        return True

    text = normalize_verification_text(task_search_text(task))
    return any(term in text for term in VERIFICATION_TERMS)


def should_nudge_verification(tasks: list[DagTask]) -> bool:
    """Check if we should nudge for verification."""
    if len(tasks) < 3:
        return False
    if not all(t.status == 'completed' for t in tasks):
        return False
    return not any(has_verification_signal(t) for t in tasks)


def summarize_tasks(
    store: DagTaskStore,
    tasks: list[DagTask] | None = None,
    include_completed: bool = True,
    include_context: bool = False
) -> str:
    """Summarize tasks as text."""
    if tasks is None:
        tasks = store.list()

    visible = tasks if include_completed else [t for t in tasks if t.status != 'completed']

    if not visible:
        return "No tasks"

    lines = []
    for task in visible:
        blockers = store.open_blockers(task)
        blocked = f" [blocked by {', '.join(f'#{id}' for id in blockers)}]" if blockers else ""
        context = f"\n  Context: {truncate_text(task.context)}" if include_context and task.context else ""
        lines.append(f"{status_icon(task.status)} #{task.id} [{task.status}] {task.title}{blocked}{context}")

    return '\n'.join(lines)


def format_archived_at(archived_at: float) -> str:
    """Format archive timestamp."""
    import datetime
    dt = datetime.datetime.fromtimestamp(archived_at)
    return dt.strftime('%b %d, %H:%M')


def archive_reason_label(reason: str) -> str:
    """Get label for archive reason."""
    return "completed sweep" if reason == "completed" else "manual archive"


def summarize_history(records: list[Any], include_context: bool = False) -> str:
    """Summarize archived task history."""
    if not records:
        return "No archived tasks"

    lines = ["Archived tasks (newest first):"]
    for record in records:
        task = record.task
        context = f"\n  Context: {truncate_text(task.context)}" if include_context and task.context else ""
        lines.append(
            f"◌ #{task.id} {task.title} — archived {format_archived_at(record.archived_at)} "
            f"({archive_reason_label(record.archive_reason)}){context}"
        )

    return '\n'.join(lines)


def count_label(count: int, singular: str, plural: str | None = None) -> str:
    """Format count with label."""
    if plural is None:
        plural = f"{singular}s"
    return f"{count} {singular if count == 1 else plural}"


def task_state_prefix(active: list[DagTask], ready: list[DagTask], blocked: list[DagTask], completed: int) -> str:
    """Build task state prefix."""
    parts = []
    if active:
        parts.append(count_label(len(active), "active"))
    if ready:
        parts.append(count_label(len(ready), "ready"))
    if blocked:
        parts.append(count_label(len(blocked), "blocked"))
    if completed:
        parts.append(count_label(completed, "done"))
    return ", ".join(parts)


def build_task_manage_guidance(store: DagTaskStore) -> str:
    """Build guidance text after task_manage."""
    tasks = store.list()
    if not tasks:
        return "Next: no tasks remain."

    completed = sum(1 for t in tasks if t.status == 'completed')
    open_count = len(tasks) - completed

    if open_count == 0:
        return f"{count_label(completed, 'task')} done. Next: verify if appropriate; archive completed tasks when ready."

    active = [t for t in tasks if t.status == 'in_progress']
    ready = store.ready()
    blocked = [t for t in tasks if t.status == 'pending' and store.open_blockers(t)]

    prefix = task_state_prefix(active, ready, blocked, completed)
    state = f"{prefix}. " if prefix else ""

    if active:
        primary = active[0]
        ready_text = f" Ready after that: #{ready[0].id}." if ready else ""
        return f"{state}Next: continue active #{primary.id} {primary.title}.{ready_text}"

    if ready:
        primary = ready[0]
        return f"{state}Next: start ready #{primary.id} {primary.title}."

    blockers = list(set(id for t in blocked for id in store.open_blockers(t)))
    if blockers:
        return f"{state}Next: all open tasks are blocked. Resolve blockers: {', '.join(f'#{id}' for id in blockers)}."

    return f"{state}Next: no ready tasks. Review task dependencies."


def resolve_cwd(ctx: Any = None) -> str:
    """Resolve current working directory."""
    if ctx and hasattr(ctx, 'cwd'):
        return ctx.cwd
    return os.environ.get('PWD', os.getcwd())


def resolve_store_path(cwd: str, config: DagTasksConfig, session_id: str = "session") -> str | None:
    """Resolve the store file path."""
    env = os.environ.get('PI_DAG_TASKS', '').strip()

    if env == 'off':
        return None
    if env.startswith('/'):
        return env
    if env.startswith('.'):
        return os.path.abspath(os.path.join(cwd, env))
    if env:
        home = os.path.expanduser('~')
        return os.path.join(home, '.pi', 'dag-tasks', f'{env}.json')

    scope = config.task_scope

    if scope == 'memory':
        return None
    elif scope == 'project':
        return os.path.join(cwd, '.pi', 'dag-tasks', 'tasks.json')
    else:  # session
        return os.path.join(cwd, '.pi', 'dag-tasks', f'tasks-{session_id}.json')


def extension_factory(api: Any) -> None:
    """Extension factory function."""

    # State
    config = DagTasksConfig()
    store = DagTaskStore()
    store_ready = False

    def ensure_store(ctx: Any = None) -> None:
        """Ensure store is initialized."""
        nonlocal store_ready, config, store

        if store_ready:
            return

        cwd = resolve_cwd(ctx)
        config = load_config(cwd)

        session_id = "session"
        if ctx and hasattr(ctx, 'session_id'):
            session_id = ctx.session_id

        store_path = resolve_store_path(cwd, config, session_id)
        store.set_file_path(store_path)
        store_ready = True

    # Register session_start event
    def on_session_start(event: Any, ctx: Any) -> None:
        nonlocal store_ready
        store_ready = False
        ensure_store(ctx)

    api.on('session_start', on_session_start)

    # Register task_manage tool
    async def execute_task_manage(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
        """Execute task_manage tool."""
        ensure_store(ctx)

        action = params['action']
        lines = []
        operations = []
        details = TaskManageResultDetails(action=action, operations=operations)

        # Track blocked tasks before operation
        blocked_before = {
            t.id for t in store.list()
            if t.status == 'pending' and store.open_blockers(t)
        }

        if action == 'create':
            inputs = params.get('creates', [])
            if 'create' in params:
                inputs.append(params['create'])

            if not inputs:
                raise ValueError("create or creates is required")

            for input_data in inputs:
                task, warnings = store.create(input_data)
                kind = 'started' if task.status == 'in_progress' else ('completed' if task.status == 'completed' else 'created')
                operations.append(TaskOperation(
                    kind=kind,
                    id=task.id,
                    title=task.title,
                    warnings=warnings
                ))
                status_text = f" [{task.status}]" if task.status != 'pending' else ""
                warning_text = f" (warning: {'; '.join(warnings)})" if warnings else ""
                lines.append(f"Created #{task.id}: {task.title}{status_text}{warning_text}")

        elif action == 'update':
            updates = params.get('updates', [])
            if 'update' in params:
                updates.append(params['update'])

            if not updates:
                raise ValueError("update or updates is required")

            for patch in updates:
                result = store.update(patch)
                if result['task']:
                    task = result['task']
                    kind = 'started' if patch.get('status') == 'in_progress' else (
                        'completed' if patch.get('status') == 'completed' else 'updated'
                    )
                    operations.append(TaskOperation(
                        kind=kind,
                        id=task.id,
                        title=task.title,
                        changed=result['changed'],
                        warnings=result['warnings']
                    ))
                    changed_text = ', '.join(result['changed']) if result['changed'] else 'no fields'
                    warning_text = f" (warning: {'; '.join(result['warnings'])})" if result['warnings'] else ""
                    lines.append(f"Updated #{patch['id']}: {changed_text}{warning_text}")
                else:
                    operations.append(TaskOperation(kind='skipped', id=patch['id'], warnings=result['warnings']))
                    lines.append(f"Skipped #{patch['id']}: {'; '.join(result['warnings'])}")

        elif action == 'complete':
            ids = params.get('ids', [])
            if 'id' in params:
                ids.append(params['id'])

            if not ids:
                raise ValueError("id or ids is required")

            for id in ids:
                result = store.update({'id': id, 'status': 'completed'})
                if result['task']:
                    operations.append(TaskOperation(kind='completed', id=id, title=result['task'].title, changed=['status']))
                    lines.append(f"Completed #{id}")
                else:
                    operations.append(TaskOperation(kind='skipped', id=id, warnings=['not found']))
                    lines.append(f"Skipped #{id}: not found")

        elif action == 'done_archive':
            ids = params.get('ids', [])
            if 'id' in params:
                ids.append(params['id'])

            if not ids:
                raise ValueError("id or ids is required")

            for id in ids:
                result = store.update({'id': id, 'status': 'completed'})
                if result['task']:
                    title = result['task'].title
                    store.archive([id])
                    operations.append(TaskOperation(kind='done_archived', id=id, title=title, changed=['status']))
                    lines.append(f"Completed and archived #{id}")
                else:
                    operations.append(TaskOperation(kind='skipped', id=id, warnings=['not found']))
                    lines.append(f"Skipped #{id}: not found")

        elif action == 'archive':
            ids = params.get('ids', [])
            if 'id' in params:
                ids.append(params['id'])

            if ids:
                before = {id: store.get(id) for id in ids}
                count = store.archive(ids)
                for id in ids:
                    task = before.get(id)
                    if task:
                        operations.append(TaskOperation(kind='archived', id=id, title=task.title))
                    else:
                        operations.append(TaskOperation(kind='skipped', id=id, warnings=['not found']))
                lines.append(f"Archived {count} task(s)")
            else:
                completed = [t for t in store.list() if t.status == 'completed']
                count = store.archive_completed()
                for task in completed:
                    operations.append(TaskOperation(kind='archived', id=task.id, title=task.title))
                lines.append(f"Archived {count} task(s)")

        elif action == 'purge':
            ids = params.get('ids', [])
            if 'id' in params:
                ids.append(params['id'])

            if not ids:
                raise ValueError("id or ids is required")

            before = {id: store.get(id) for id in ids}
            count = store.purge(ids)
            for id in ids:
                task = before.get(id)
                if task:
                    operations.append(TaskOperation(kind='purged', id=id, title=task.title))
                else:
                    operations.append(TaskOperation(kind='skipped', id=id, warnings=['not found']))
            lines.append(f"Purged {count}/{len(ids)} task(s)")

        elif action == 'list':
            lines.append(summarize_tasks(
                store,
                store.list(),
                params.get('includeCompleted', True),
                params.get('includeContext', False)
            ))

        elif action == 'history':
            history = store.history(
                params.get('limit', 20),
                params.get('query')
            )
            lines.append(summarize_history(history, params.get('includeContext', False)))
            details.history = history

        # Check for unblocked tasks
        if action not in ['list', 'history']:
            tasks_after = store.list()
            for task in tasks_after:
                if (task.id in blocked_before and
                    task.status == 'pending' and
                    not store.open_blockers(task)):
                    operations.append(TaskOperation(kind='unblocked', id=task.id, title=task.title))
                    lines.append(f"Unblocked #{task.id}: {task.title}")

        # Add guidance
        if action not in ['list', 'history']:
            guidance = build_task_manage_guidance(store)
            details.guidance = guidance
            lines.append("")
            lines.append(guidance)

        store.delete_file_if_empty()
        details.tasks = store.list()

        return {
            'success': True,
            'content': [{'type': 'text', 'text': '\n'.join(lines)}],
            'details': vars(details)
        }

    api.register_tool(
        name='task_manage',
        label='Task Manage',
        description="Manage Pi's task list: the durable todo/progress tracker for non-trivial work. Create/update it early, keep statuses current, and archive completed tasks when ready. Use action:'create' for single or batch creation via create/creates; dependencies use task IDs like '1', not titles.",
        parameters={
            'type': 'object',
            'properties': {
                'action': {
                    'type': 'string',
                    'enum': ['create', 'update', 'complete', 'done_archive', 'archive', 'purge', 'list', 'history'],
                    'description': 'The action to perform'
                },
                'create': {
                    'type': 'object',
                    'description': 'Single task to create'
                },
                'creates': {
                    'type': 'array',
                    'description': 'Multiple tasks to create'
                },
                'update': {
                    'type': 'object',
                    'description': 'Single task to update'
                },
                'updates': {
                    'type': 'array',
                    'description': 'Multiple tasks to update'
                },
                'id': {
                    'type': 'string',
                    'description': 'Single task ID'
                },
                'ids': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Multiple task IDs'
                },
                'archive': {
                    'type': 'string',
                    'enum': ['completed'],
                    'description': 'Archive filter'
                },
                'limit': {
                    'type': 'number',
                    'minimum': 1,
                    'maximum': 100,
                    'description': 'History limit'
                },
                'query': {
                    'type': 'string',
                    'description': 'Search query for history'
                },
                'includeCompleted': {
                    'type': 'boolean',
                    'default': True,
                    'description': 'Include completed tasks in list'
                },
                'includeContext': {
                    'type': 'boolean',
                    'default': False,
                    'description': 'Include context in output'
                }
            },
            'required': ['action']
        },
        execute=execute_task_manage,
        prompt_snippet='Manage task list',
        prompt_guidelines=[
            "This is Pi's single task/todo tracker. When tracking is appropriate, use task_manage instead of writing informal todo lists in prose.",
            "Use tasks for durable state, not ceremony: multi-step implementation, ambiguity, checkpoints, dependencies, verification, multiple user requests, discovered follow-up work, or work likely to span turns/context.",
            "Skip task_manage for trivial single-step edits, direct factual answers, or pure conversation.",
            "Create the smallest useful task set for the current execution slice; do not clone a whole roadmap, charter plan, or speculative future work into tasks.",
            "Right-size tasks as meaningful outcomes that can be started, blocked, completed, or verified; avoid both giant catch-all tasks and microscopic process tasks.",
            "Use action:'create' for both create and creates; there is no action:'creates'.",
            "Dependency fields blockedBy/blocks/addBlockedBy/addBlocks must contain task IDs like '1', not task titles; create first, then update dependencies if you need generated IDs.",
            "Use dependencies only when they change what can start next; blocked work is represented with blockedBy/blocks dependencies, not a separate blocked status.",
            "Normally keep one task in_progress per active worker. Multiple in_progress tasks are valid only for genuine parallel work or distinct owners/subagents.",
            "Task context is durable setup, not a running journal. Add it up front with constraints, relevant findings, expected inputs, and definition of done; update it only when durable new information changes how the task should be done or the original context is wrong/incomplete.",
            "Keep tasks outcome-oriented and verifiable, not microscopic. For tests, builds, lint, typecheck, manual review, or output inspection tasks, set metadata.kind = 'verification'.",
            "Do not create standalone tasks for tiny process/meta instructions like compress context, reply concisely, run final check, or summarize changes unless they are a real multi-step workflow phase; include them in the relevant task context/definition of done instead.",
            "Complete tasks as soon as their work is fully done; avoid batching status updates at the end.",
            "Only mark completed work that is actually finished; if verification is appropriate, complete after running it or record why it was skipped.",
            "Use action:'done_archive' when a finished task can be marked complete and archived in one operation; use separate complete/archive only when review should remain visible first.",
            "Archive completed tasks once they are ready to leave the active review surface.",
            "Use task_next for ready/unblocked work; prefer ready tasks in ID order and don't start blocked tasks.",
        ]
    )

    # Register task_next tool
    async def execute_task_next(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
        """Execute task_next tool."""
        ensure_store(ctx)

        limit = params.get('limit', 5)
        tasks = store.list()
        ready = store.ready()[:limit]
        active = [t for t in tasks if t.status == 'in_progress']
        blocked = [t for t in tasks if t.status == 'pending' and store.open_blockers(t)]
        completed = [t for t in tasks if t.status == 'completed']

        lines = [
            f"Summary: {len(tasks)} total, {len(ready)} ready, {len(active)} active, {len(blocked)} blocked, {len(completed)} completed."
        ]

        if active:
            lines.append(f"Active:\n{summarize_tasks(store, active, True, True)}")

        lines.append(
            f"Ready:\n{summarize_tasks(store, ready, True, True)}" if ready else "Ready: none"
        )

        if params.get('includeBlocked', True):
            lines.append(
                f"Blocked:\n{summarize_tasks(store, blocked, True)}" if blocked else "Blocked: none"
            )

        details = TaskNextResultDetails(
            ready=ready,
            active=active,
            blocked=blocked,
            completed_count=len(completed),
            total_count=len(tasks)
        )

        return {
            'success': True,
            'content': [{'type': 'text', 'text': '\n\n'.join(lines)}],
            'details': vars(details)
        }

    api.register_tool(
        name='task_next',
        label='Task Next',
        description="Return ready/unblocked tasks from Pi's task list and a compact summary.",
        parameters={
            'type': 'object',
            'properties': {
                'limit': {
                    'type': 'number',
                    'minimum': 1,
                    'maximum': 20,
                    'default': 5,
                    'description': 'Max ready tasks to return'
                },
                'includeBlocked': {
                    'type': 'boolean',
                    'default': True,
                    'description': 'Include blocked tasks'
                },
                'includeCompleted': {
                    'type': 'boolean',
                    'default': True,
                    'description': 'Include completed count'
                }
            }
        },
        execute=execute_task_next,
        prompt_snippet='Next ready tasks',
        prompt_guidelines=[
            "Use after completing work or when resuming; prefer ready tasks in ID order and don't start blocked tasks."
        ]
    )

    # Register /tasks command
    async def tasks_command(args: str, ctx: Any = None) -> None:
        """Handle /tasks command."""
        ensure_store(ctx)

        tasks = store.list()
        print(f"\n=== DAG Tasks ({len(tasks)} total) ===\n")
        print(summarize_tasks(store, tasks, True, False))

        completed_count = sum(1 for t in tasks if t.status == 'completed')
        if completed_count:
            print(f"\n{completed_count} completed task(s) ready to archive.")

    api.register_command(
        name='tasks',
        description='View DAG tasks',
        handler=tasks_command
    )
