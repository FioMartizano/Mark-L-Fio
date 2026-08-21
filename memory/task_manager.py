import json
from datetime import datetime
from pathlib import Path
from threading import Lock

# Paths

MEMORY_DIR = Path(__file__).resolve().parent
TASKS_PATH = MEMORY_DIR / "tasks.json"

_lock = Lock()

# Internal Helpers
def _empty_tasks() -> dict:
    return {
        "tasks": []
    }


def load_tasks() -> dict:
    """Load tasks from tasks.json."""
    if not TASKS_PATH.exists():
        return _empty_tasks()

    with _lock:
        try:
            data = json.loads(TASKS_PATH.read_text(encoding="utf-8"))

            if isinstance(data, dict) and isinstance(data.get("tasks"), list):
                return data

            return _empty_tasks()

        except Exception as e:
            print(f"[Tasks] ⚠️ Failed to load tasks: {e}")
            return _empty_tasks()


def save_tasks(data: dict) -> None:
    """Save the task database."""
    TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _lock:
        TASKS_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

# Task Operations

def add_task(
    title: str,
    project: str = "",
    due: str | None = None,
) -> dict:
    """Add a new pending task."""

    title = (title or "").strip()

    if not title:
        return {
            "success": False,
            "message": "Task title cannot be empty."
        }

    data = load_tasks()

    now = datetime.now()
    task_id = f"task_{now.strftime('%Y%m%d%H%M%S%f')}"

    task = {
        "id": task_id,
        "title": title,
        "project": (project or "").strip(),
        "due": due,
        "status": "pending",
        "created": now.strftime("%Y-%m-%d"),
    }

    data["tasks"].append(task)
    save_tasks(data)

    print(f"[Tasks] ➕ Added: {title}")

    return {
        "success": True,
        "task": task,
    }


def complete_task(task_id: str) -> dict:
    """Mark a task as completed."""

    data = load_tasks()

    for task in data["tasks"]:
        if task.get("id") == task_id:
            task["status"] = "completed"
            task["completed"] = datetime.now().strftime("%Y-%m-%d")
            save_tasks(data)

            print(f"[Tasks] ✅ Completed: {task.get('title')}")

            return {
                "success": True,
                "task": task,
            }

    return {
        "success": False,
        "message": f"Task not found: {task_id}"
    }


def delete_task(task_id: str) -> dict:
    """Delete a task."""

    data = load_tasks()

    original_count = len(data["tasks"])

    data["tasks"] = [
        task for task in data["tasks"]
        if task.get("id") != task_id
    ]

    if len(data["tasks"]) == original_count:
        return {
            "success": False,
            "message": f"Task not found: {task_id}"
        }

    save_tasks(data)

    print(f"[Tasks] 🗑️ Deleted: {task_id}")

    return {
        "success": True,
        "message": f"Task deleted: {task_id}"
    }


def get_today_tasks() -> list:
    """Return pending tasks due today."""

    today = datetime.now().strftime("%Y-%m-%d")
    data = load_tasks()

    return [
        task for task in data["tasks"]
        if task.get("status") == "pending"
        and task.get("due") == today
    ]


def get_upcoming_tasks() -> list:
    """Return pending tasks with future due dates."""

    today = datetime.now().strftime("%Y-%m-%d")
    data = load_tasks()

    return [
        task for task in data["tasks"]
        if task.get("status") == "pending"
        and task.get("due")
        and task.get("due") > today
    ]


def get_all_pending_tasks() -> list:
    """Return all pending tasks."""

    data = load_tasks()

    return [
        task for task in data["tasks"]
        if task.get("status") == "pending"
    ]

def find_pending_task(query: str) -> dict | None:
    """Find the most likely pending task matching a user's description."""

    query = (query or "").strip().lower()

    if not query:
        return None

    data = load_tasks()

    pending = [
        task for task in data["tasks"]
        if task.get("status") == "pending"
    ]

    # Exact title match
    for task in pending:
        if task.get("title", "").lower() == query:
            return task

    # Simple keyword matching
    query_words = set(query.split())

    best_task = None
    best_score = 0

    for task in pending:
        title = task.get("title", "").lower()
        title_words = set(title.split())

        score = len(query_words & title_words)

        if score > best_score:
            best_score = score
            best_task = task

    return best_task
