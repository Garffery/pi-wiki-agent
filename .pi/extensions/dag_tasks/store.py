"""
DAG Task Store - handles persistence and CRUD operations
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .types import DagTask, StoreData, ArchivedDagTask, ArchiveReason, TaskStatus

LOCK_RETRY_MS = 40
LOCK_MAX_RETRIES = 125


def sleep_ms(ms: int) -> None:
    """Sleep for milliseconds."""
    time.sleep(ms / 1000.0)


def is_process_running(pid: int) -> bool:
    """Check if a process is running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def acquire_lock(lock_path: str) -> None:
    """Acquire a file lock."""
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    for _ in range(LOCK_MAX_RETRIES):
        try:
            # Try to create lock file exclusively
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return
        except FileExistsError:
            # Lock exists, check if process is still running
            try:
                with open(lock_path, 'r') as f:
                    pid = int(f.read().strip())
                if not is_process_running(pid):
                    # Stale lock, remove it
                    os.unlink(lock_path)
                    continue
            except (ValueError, FileNotFoundError):
                pass
            sleep_ms(LOCK_RETRY_MS)

    raise RuntimeError(f"Failed to acquire DAG task store lock: {lock_path}")


def release_lock(lock_path: str) -> None:
    """Release a file lock."""
    try:
        os.unlink(lock_path)
    except FileNotFoundError:
        pass


class DagTaskStore:
    """Store for DAG tasks with file persistence."""

    def __init__(self, file_path: str | None = None):
        self.next_id = 1
        self.tasks: dict[str, DagTask] = {}
        self.file_path = file_path
        self.lock_path: str | None = None
        self.archive_path: str | None = None

        if file_path:
            self.lock_path = f"{file_path}.lock"
            self.archive_path = os.path.join(os.path.dirname(file_path), "archive.jsonl")
            self._load()

    def set_file_path(self, file_path: str | None) -> None:
        """Set the file path for persistence."""
        self.file_path = file_path
        self.lock_path = f"{file_path}.lock" if file_path else None
        self.archive_path = os.path.join(os.path.dirname(file_path), "archive.jsonl") if file_path else None
        self.next_id = 1
        self.tasks.clear()

        if file_path:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            self._load()

    def _load(self) -> None:
        """Load tasks from file."""
        if not self.file_path or not os.path.exists(self.file_path):
            return

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.next_id = data.get('nextId', 1)
            tasks_data = data.get('tasks', [])

            self.tasks = {}
            for task_dict in tasks_data:
                task = DagTask(**task_dict)
                self.tasks[task.id] = task
        except (json.JSONDecodeError, FileNotFoundError):
            self.next_id = 1
            self.tasks.clear()

    def _save(self) -> None:
        """Save tasks to file."""
        if not self.file_path:
            return

        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

        data = {
            'nextId': self.next_id,
            'tasks': [vars(task) for task in self.tasks.values()]
        }

        tmp_path = f"{self.file_path}.tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        # Atomic rename
        os.replace(tmp_path, self.file_path)

    def _with_lock(self, fn):
        """Execute function with file lock."""
        if not self.lock_path:
            return fn()

        acquire_lock(self.lock_path)
        try:
            self._load()
            result = fn()
            self._save()
            return result
        finally:
            release_lock(self.lock_path)

    def list(self) -> list[DagTask]:
        """List all tasks."""
        if self.file_path:
            self._load()
        return sorted(self.tasks.values(), key=lambda t: int(t.id))

    def get(self, id: str) -> DagTask | None:
        """Get a task by ID."""
        if self.file_path:
            self._load()
        return self.tasks.get(id)

    def create(self, input: dict[str, Any]) -> tuple[DagTask, list[str]]:
        """Create a new task."""
        def _create():
            now = time.time()
            task = DagTask(
                id=str(self.next_id),
                title=input['title'],
                description=input.get('description', ''),
                context=input.get('context'),
                status=input.get('status', 'pending'),
                active_form=input.get('activeForm'),
                owner=input.get('owner'),
                blocks=[],
                blocked_by=[],
                metadata=input.get('metadata', {}),
                created_at=now,
                started_at=now if input.get('status') == 'in_progress' else None,
                completed_at=now if input.get('status') == 'completed' else None,
                updated_at=now,
            )

            self.next_id += 1
            self.tasks[task.id] = task

            warnings = self._apply_edges(
                task.id,
                input.get('blocks', []),
                input.get('blockedBy', [])
            )

            return task, warnings

        return self._with_lock(_create)

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Update a task."""
        def _update():
            task = self.tasks.get(patch['id'])
            if not task:
                return {
                    'task': None,
                    'changed': [],
                    'warnings': [f"#{patch['id']} not found"]
                }

            changed = []

            if 'title' in patch:
                task.title = patch['title']
                changed.append('title')

            if 'description' in patch:
                task.description = patch['description']
                changed.append('description')

            if 'context' in patch:
                task.context = patch['context'] or None
                changed.append('context')

            if 'status' in patch:
                task.status = patch['status']
                if patch['status'] == 'in_progress' and task.started_at is None:
                    task.started_at = time.time()
                if patch['status'] == 'pending':
                    task.started_at = None
                    task.completed_at = None
                if patch['status'] == 'completed' and task.completed_at is None:
                    task.completed_at = time.time()
                changed.append('status')

            if 'activeForm' in patch:
                task.active_form = patch['activeForm']
                changed.append('activeForm')

            if 'owner' in patch:
                task.owner = patch['owner'] or None
                changed.append('owner')

            if 'metadata' in patch:
                for key, value in patch['metadata'].items():
                    if value is None:
                        task.metadata.pop(key, None)
                    else:
                        task.metadata[key] = value
                changed.append('metadata')

            warnings = []
            if 'addBlocks' in patch:
                warnings.extend(self._apply_edges(patch['id'], patch['addBlocks'], []))
                changed.append('blocks')

            if 'addBlockedBy' in patch:
                warnings.extend(self._apply_edges(patch['id'], [], patch['addBlockedBy']))
                changed.append('blockedBy')

            if 'removeBlocks' in patch:
                self._remove_edges(patch['id'], patch['removeBlocks'], [])
                changed.append('blocks')

            if 'removeBlockedBy' in patch:
                self._remove_edges(patch['id'], [], patch['removeBlockedBy'])
                changed.append('blockedBy')

            task.updated_at = time.time()

            return {
                'task': task,
                'changed': list(set(changed)),
                'warnings': warnings
            }

        return self._with_lock(_update)

    def archive(self, ids: list[str], reason: ArchiveReason = 'selected') -> int:
        """Archive tasks."""
        def _archive():
            archived = []
            for id in ids:
                task = self.tasks.get(id)
                if not task:
                    continue

                archived.append(ArchivedDagTask(
                    archived_at=time.time(),
                    archive_reason=reason,
                    task=task
                ))
                del self.tasks[id]

            self._append_archive(archived)
            self._remove_dangling_edges()
            return len(archived)

        return self._with_lock(_archive)

    def archive_completed(self) -> int:
        """Archive all completed tasks."""
        ids = [t.id for t in self.list() if t.status == 'completed']
        return self.archive(ids, 'completed')

    def purge(self, ids: list[str]) -> int:
        """Permanently delete tasks."""
        def _purge():
            count = 0
            for id in ids:
                if id in self.tasks:
                    del self.tasks[id]
                    count += 1
            self._remove_dangling_edges()
            return count

        return self._with_lock(_purge)

    def history(self, limit: int = 20, query: str | None = None) -> list[ArchivedDagTask]:
        """Get archived task history."""
        if not self.archive_path or not os.path.exists(self.archive_path):
            return []

        normalized_query = query.lower() if query else None
        records = []

        with open(self.archive_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                    record = ArchivedDagTask(
                        archived_at=data['archived_at'],
                        archive_reason=data['archive_reason'],
                        task=DagTask(**data['task'])
                    )

                    if normalized_query:
                        search_text = '\n'.join([
                            record.task.title,
                            record.task.description,
                            record.task.context or ''
                        ]).lower()

                        if normalized_query not in search_text:
                            continue

                    records.append(record)
                except (json.JSONDecodeError, KeyError):
                    continue

        return records[-limit:][::-1]

    def ready(self) -> list[DagTask]:
        """Get ready (unblocked pending) tasks."""
        return [t for t in self.list() if t.status == 'pending' and len(self.open_blockers(t)) == 0]

    def open_blockers(self, task: DagTask) -> list[str]:
        """Get open blockers for a task."""
        return [id for id in task.blocked_by if self.tasks.get(id) and self.tasks[id].status != 'completed']

    def delete_file_if_empty(self) -> None:
        """Delete the store file if no tasks remain."""
        if not self.file_path or len(self.tasks) > 0:
            return

        try:
            os.unlink(self.file_path)
        except FileNotFoundError:
            pass

    def _append_archive(self, records: list[ArchivedDagTask]) -> None:
        """Append records to archive file."""
        if not self.archive_path or len(records) == 0:
            return

        os.makedirs(os.path.dirname(self.archive_path), exist_ok=True)

        with open(self.archive_path, 'a', encoding='utf-8') as f:
            for record in records:
                data = {
                    'archived_at': record.archived_at,
                    'archive_reason': record.archive_reason,
                    'task': vars(record.task)
                }
                f.write(json.dumps(data) + '\n')

    def _remove_dangling_edges(self) -> None:
        """Remove edges pointing to deleted tasks."""
        valid_ids = set(self.tasks.keys())
        for task in self.tasks.values():
            task.blocks = [id for id in task.blocks if id in valid_ids]
            task.blocked_by = [id for id in task.blocked_by if id in valid_ids]

    def _apply_edges(self, id: str, blocks: list[str] | None, blocked_by: list[str] | None) -> list[str]:
        """Apply dependency edges."""
        task = self.tasks.get(id)
        if not task:
            return [f"#{id} not found"]

        warnings = []

        for target_id in blocks or []:
            target = self.tasks.get(target_id)
            if target_id == id:
                warnings.append(f"#{id} cannot block itself")
                continue
            if not target:
                warnings.append(f"dependency #{target_id} does not exist; use task IDs like '1', not task titles")
                continue
            if self._has_path(target_id, id):
                warnings.append(f"cycle between #{id} and #{target_id}")
                continue

            if target_id not in task.blocks:
                task.blocks.append(target_id)
            if id not in target.blocked_by:
                target.blocked_by.append(id)

        for blocker_id in blocked_by or []:
            blocker = self.tasks.get(blocker_id)
            if blocker_id == id:
                warnings.append(f"#{id} cannot block itself")
                continue
            if not blocker:
                warnings.append(f"dependency #{blocker_id} does not exist; use task IDs like '1', not task titles")
                continue
            if self._has_path(id, blocker_id):
                warnings.append(f"cycle between #{id} and #{blocker_id}")
                continue

            if blocker_id not in task.blocked_by:
                task.blocked_by.append(blocker_id)
            if id not in blocker.blocks:
                blocker.blocks.append(id)

        return warnings

    def _has_path(self, from_id: str, to_id: str, visited: set[str] | None = None) -> bool:
        """Check if there's a path from one task to another."""
        if from_id == to_id:
            return True

        if visited is None:
            visited = set()

        if from_id in visited:
            return False

        visited.add(from_id)

        task = self.tasks.get(from_id)
        if not task:
            return False

        return any(self._has_path(next_id, to_id, visited) for next_id in task.blocks)

    def _remove_edges(self, id: str, blocks: list[str] | None, blocked_by: list[str] | None) -> None:
        """Remove dependency edges."""
        task = self.tasks.get(id)
        if not task:
            return

        for target_id in blocks or []:
            task.blocks = [x for x in task.blocks if x != target_id]
            target = self.tasks.get(target_id)
            if target:
                target.blocked_by = [x for x in target.blocked_by if x != id]

        for blocker_id in blocked_by or []:
            task.blocked_by = [x for x in task.blocked_by if x != blocker_id]
            blocker = self.tasks.get(blocker_id)
            if blocker:
                blocker.blocks = [x for x in blocker.blocks if x != id]
