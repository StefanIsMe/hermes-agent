"""Enhanced Background Agent Manager — Circuit breakers, error recovery, concurrency.

Inspired by Oh My OpenAgent's background-agent system with:
- Circuit breaker (stop retrying after N failures)
- Loop detector (detect agents spinning)
- Error classifier (transient vs permanent)
- Concurrency manager (configurable parallelism limits)

Wraps existing delegate_task patterns with production-grade error handling.
"""

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CIRCUIT_BROKEN = "circuit_broken"


class ErrorType(Enum):
    TRANSIENT = "transient"       # Network, timeout, rate limit — retry safe
    PERMANENT = "permanent"       # Syntax, auth, not found — no retry
    UNKNOWN = "unknown"           # Unclassified — retry with caution


@dataclass
class TaskRecord:
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    last_error: Optional[str] = None
    error_type: Optional[ErrorType] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[str] = None


@dataclass
class CircuitBreakerState:
    task_id: str
    failure_count: int = 0
    threshold: int = 3
    last_failure_time: float = 0
    is_open: bool = False  # Open = circuit broken, stop retrying
    cooldown_seconds: float = 60


class ErrorClassifier:
    """Classify errors as transient or permanent."""
    
    TRANSIENT_PATTERNS = [
        "timeout", "timed out", "connection", "network",
        "rate limit", "429", "503", "502", "500",
        "overloaded", "capacity", "retry",
        "ECONNRESET", "ECONNREFUSED", "ETIMEDOUT",
    ]
    
    PERMANENT_PATTERNS = [
        "syntax error", "syntaxerror", "indentationerror",
        "import error", "modulenotfounderror",
        "attributeerror", "typeerror", "nameerror",
        "permission denied", "file not found", "filenotfounderror",
        "401", "403", "unauthorized", "forbidden",
        "not found", "does not exist",
        "invalid", "malformed",
    ]
    
    @classmethod
    def classify(cls, error: str) -> ErrorType:
        error_lower = error.lower()
        
        for pattern in cls.PERMANENT_PATTERNS:
            if pattern.lower() in error_lower:
                return ErrorType.PERMANENT
        
        for pattern in cls.TRANSIENT_PATTERNS:
            if pattern.lower() in error_lower:
                return ErrorType.TRANSIENT
        
        return ErrorType.UNKNOWN


class ConcurrencyManager:
    """Limit parallel task execution."""
    
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self._running: Dict[str, float] = {}  # task_id -> start_time
    
    def can_start(self) -> bool:
        return len(self._running) < self.max_concurrent
    
    def start(self, task_id: str) -> bool:
        if not self.can_start():
            return False
        self._running[task_id] = time.time()
        return True
    
    def finish(self, task_id: str):
        self._running.pop(task_id, None)
    
    @property
    def running_count(self) -> int:
        return len(self._running)
    
    @property
    def available_slots(self) -> int:
        return max(0, self.max_concurrent - len(self._running))


class LoopDetector:
    """Detect agents producing identical outputs (spinning)."""
    
    def __init__(self, window: int = 3, similarity_threshold: float = 0.9):
        self.window = window
        self.threshold = similarity_threshold
        self._outputs: Dict[str, List[str]] = defaultdict(list)  # task_id -> outputs
    
    def check(self, task_id: str, output: str) -> bool:
        """Returns True if loop detected (agent is spinning)."""
        outputs = self._outputs[task_id]
        outputs.append(output)
        
        if len(outputs) < self.window:
            return False
        
        # Keep only last `window` outputs
        if len(outputs) > self.window:
            self._outputs[task_id] = outputs[-self.window:]
            outputs = self._outputs[task_id]
        
        # Check if recent outputs are too similar
        for i in range(len(outputs) - 1):
            similarity = self._string_similarity(outputs[i], outputs[-1])
            if similarity >= self.threshold:
                return True
        
        return False
    
    def reset(self, task_id: str):
        self._outputs.pop(task_id, None)
    
    @staticmethod
    def _string_similarity(a: str, b: str) -> float:
        """Simple Jaccard similarity on word sets."""
        if not a or not b:
            return 0.0
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        return intersection / union if union > 0 else 0.0


class BackgroundAgentManager:
    """Enhanced background agent manager with circuit breakers and error recovery."""
    
    def __init__(self, max_concurrent: int = 5, default_max_attempts: int = 3):
        self.concurrency = ConcurrencyManager(max_concurrent)
        self.loop_detector = LoopDetector()
        self.default_max_attempts = default_max_attempts
        
        self._tasks: Dict[str, TaskRecord] = {}
        self._circuit_breakers: Dict[str, CircuitBreakerState] = {}
        self._counter = 0
    
    def _next_id(self) -> str:
        self._counter += 1
        return f"bg_{self._counter:04d}"
    
    def create_task(self, description: str, max_attempts: int = None) -> TaskRecord:
        """Register a new background task."""
        task = TaskRecord(
            id=self._next_id(),
            description=description,
            max_attempts=max_attempts or self.default_max_attempts,
        )
        self._tasks[task.id] = task
        self._circuit_breakers[task.id] = CircuitBreakerState(
            task_id=task.id,
            threshold=task.max_attempts,
        )
        return task
    
    def start_task(self, task_id: str) -> Tuple[bool, str]:
        """Try to start a task. Returns (success, message)."""
        task = self._tasks.get(task_id)
        if not task:
            return False, f"Task {task_id} not found"
        
        # Check circuit breaker
        cb = self._circuit_breakers.get(task_id)
        if cb and cb.is_open:
            elapsed = time.time() - cb.last_failure_time
            if elapsed < cb.cooldown_seconds:
                task.status = TaskStatus.CIRCUIT_BROKEN
                return False, (
                    f"Circuit broken for {task_id}: {cb.failure_count} failures. "
                    f"Cooling down ({elapsed:.0f}s/{cb.cooldown_seconds:.0f}s)."
                )
            else:
                # Cooldown passed, reset circuit
                cb.is_open = False
                cb.failure_count = 0
        
        # Check concurrency
        if not self.concurrency.can_start():
            return False, f"Concurrency limit reached ({self.concurrency.running_count} running)"
        
        # Start
        self.concurrency.start(task_id)
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        task.attempts += 1
        return True, "Started"
    
    def record_success(self, task_id: str, result: str = "") -> bool:
        """Record successful task completion."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()
        task.result = result
        self.concurrency.finish(task_id)
        self.loop_detector.reset(task_id)
        
        # Reset circuit breaker on success
        cb = self._circuit_breakers.get(task_id)
        if cb:
            cb.failure_count = 0
            cb.is_open = False
        
        return True
    
    def record_failure(self, task_id: str, error: str) -> Tuple[bool, str]:
        """Record task failure. Returns (should_retry, message)."""
        task = self._tasks.get(task_id)
        if not task:
            return False, f"Task {task_id} not found"
        
        error_type = ErrorClassifier.classify(error)
        task.last_error = error
        task.error_type = error_type
        self.concurrency.finish(task_id)
        
        # Check loop detection
        if self.loop_detector.check(task_id, error):
            task.status = TaskStatus.FAILED
            return False, f"Loop detected: agent producing identical errors. Stopping."
        
        # Update circuit breaker
        cb = self._circuit_breakers.get(task_id)
        if cb:
            cb.failure_count += 1
            cb.last_failure_time = time.time()
            
            if cb.failure_count >= cb.threshold:
                cb.is_open = True
                task.status = TaskStatus.CIRCUIT_BROKEN
                return False, (
                    f"Circuit broken after {cb.failure_count} failures. "
                    f"Error type: {error_type.value}. Last error: {error[:200]}"
                )
        
        # Permanent errors — don't retry
        if error_type == ErrorType.PERMANENT:
            task.status = TaskStatus.FAILED
            return False, f"Permanent error (no retry): {error[:200]}"
        
        # Check attempts
        if task.attempts >= task.max_attempts:
            task.status = TaskStatus.FAILED
            return False, f"Max attempts ({task.max_attempts}) reached. Last error: {error[:200]}"
        
        return True, f"Retry {task.attempts}/{task.max_attempts} (error type: {error_type.value})"
    
    def get_status(self, task_id: str = None) -> str:
        """Get status of one or all tasks."""
        if task_id:
            task = self._tasks.get(task_id)
            if not task:
                return json.dumps({"error": f"Task {task_id} not found"})
            return json.dumps(asdict(task), default=str, indent=2)
        
        summary = {
            "total_tasks": len(self._tasks),
            "running": self.concurrency.running_count,
            "available_slots": self.concurrency.available_slots,
            "by_status": {},
            "tasks": [],
        }
        
        for status in TaskStatus:
            summary["by_status"][status.value] = sum(
                1 for t in self._tasks.values() if t.status == status
            )
        
        for task in self._tasks.values():
            summary["tasks"].append({
                "id": task.id,
                "status": task.status.value,
                "attempts": task.attempts,
                "description": task.description[:80],
            })
        
        return json.dumps(summary, indent=2)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

BG_MANAGER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "background_manager",
        "description": (
            "Manage background tasks with circuit breakers and error recovery. "
            "Actions: create (register task), start (begin execution), "
            "success (mark complete), failure (record error + retry decision), "
            "status (check state). Prevents infinite retries and detects loops."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "start", "success", "failure", "status"],
                    "description": "Action to perform."
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID (required for start/success/failure/status)."
                },
                "description": {
                    "type": "string",
                    "description": "Task description (required for create)."
                },
                "error": {
                    "type": "string",
                    "description": "Error message (required for failure)."
                },
                "result": {
                    "type": "string",
                    "description": "Success result (optional for success)."
                },
                "max_attempts": {
                    "type": "integer",
                    "description": "Max retry attempts (default 3).",
                    "default": 3
                }
            },
            "required": ["action"]
        }
    }
}

# Global manager instance
_manager = BackgroundAgentManager()


def _handle_background_manager(args, **kw):
    action = args["action"]
    
    if action == "create":
        task = _manager.create_task(
            description=args.get("description", "unnamed"),
            max_attempts=args.get("max_attempts"),
        )
        return json.dumps({"task_id": task.id, "status": task.status.value})
    
    elif action == "start":
        success, msg = _manager.start_task(args["task_id"])
        return json.dumps({"success": success, "message": msg})
    
    elif action == "success":
        _manager.record_success(args["task_id"], args.get("result", ""))
        return json.dumps({"status": "completed"})
    
    elif action == "failure":
        should_retry, msg = _manager.record_failure(args["task_id"], args.get("error", ""))
        return json.dumps({"should_retry": should_retry, "message": msg})
    
    elif action == "status":
        return _manager.get_status(args.get("task_id"))
    
    return json.dumps({"error": f"Unknown action: {action}"})


try:
    from tools.registry import registry
    registry.register(
        name="background_manager",
        toolset="agent",
        schema=BG_MANAGER_SCHEMA,
        handler=_handle_background_manager,
        emoji="🔄",
        max_result_size_chars=10000,
    )
except ImportError:
    pass
