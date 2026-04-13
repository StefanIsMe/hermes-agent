"""Interview-Mode Planning Tool — Prometheus-style task clarification.

Inspired by Oh My OpenAgent's Prometheus planner that interviews the user
before generating a plan. Asks clarifying questions, identifies scope and
ambiguities, builds a verified plan before any code is touched.

Reduces wasted work from misunderstood requirements.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interview templates
# ---------------------------------------------------------------------------

INTERVIEW_QUESTIONS = {
    "scope": [
        "What is the exact scope of this task? (single file, multi-file, full system)",
        "What should NOT be changed as part of this task?",
        "Are there any existing files/functions/components that are directly relevant?",
    ],
    "constraints": [
        "Are there any performance constraints? (latency, memory, bundle size)",
        "Are there compatibility requirements? (browser support, Python version, API version)",
        "Are there security considerations? (authentication, input validation, data privacy)",
    ],
    "success_criteria": [
        "How will we know this task is complete? What does 'done' look like?",
        "Are there specific tests that must pass?",
        "Are there acceptance criteria from a spec or ticket?",
    ],
    "edge_cases": [
        "What happens on error / failure?",
        "Are there edge cases to handle? (empty input, very large input, concurrent access)",
        "What about backwards compatibility?",
    ],
    "dependencies": [
        "Does this depend on other work in progress?",
        "Are there external APIs or services involved?",
        "What libraries/frameworks are needed?",
    ],
}


def generate_interview(task_description: str, depth: str = "standard") -> Dict[str, Any]:
    """Generate interview questions for a task.
    
    Args:
        task_description: The task to plan.
        depth: "quick" (2-3 questions), "standard" (5-7), "deep" (10+)
    
    Returns:
        {
            "task": str,
            "depth": str,
            "questions": [{"category": str, "question": str}],
            "estimated_questions": int,
            "instruction": str,
        }
    """
    # Detect task complexity
    complexity_signals = {
        "multi-file": any(k in task_description.lower() for k in [
            "multi-file", "multiple files", "across files", "refactor",
            "system", "architecture", "redesign", "migrate",
        ]),
        "api_work": any(k in task_description.lower() for k in [
            "api", "endpoint", "rest", "graphql", "webhook",
            "integration", "external", "third-party",
        ]),
        "database": any(k in task_description.lower() for k in [
            "database", "sql", "migration", "schema", "model",
            "query", "index", "table",
        ]),
        "ui": any(k in task_description.lower() for k in [
            "ui", "component", "page", "screen", "frontend",
            "react", "vue", "css", "layout",
        ]),
        "security": any(k in task_description.lower() for k in [
            "auth", "security", "permission", "encrypt",
            "token", "password", "credential",
        ]),
    }
    
    # Select questions based on depth and complexity
    if depth == "quick":
        num_questions = 3
    elif depth == "deep":
        num_questions = 10
    else:
        num_questions = 7
    
    selected = []
    
    # Always include scope and success criteria
    selected.append({"category": "scope", "question": INTERVIEW_QUESTIONS["scope"][0]})
    selected.append({"category": "success_criteria", "question": INTERVIEW_QUESTIONS["success_criteria"][0]})
    
    # Add based on detected complexity
    if complexity_signals["multi-file"]:
        selected.append({"category": "scope", "question": INTERVIEW_QUESTIONS["scope"][1]})
        selected.append({"category": "edge_cases", "question": INTERVIEW_QUESTIONS["edge_cases"][0]})
    
    if complexity_signals["api_work"]:
        selected.append({"category": "dependencies", "question": INTERVIEW_QUESTIONS["dependencies"][2]})
        selected.append({"category": "constraints", "question": INTERVIEW_QUESTIONS["constraints"][2]})
    
    if complexity_signals["database"]:
        selected.append({"category": "edge_cases", "question": INTERVIEW_QUESTIONS["edge_cases"][1]})
        selected.append({"category": "constraints", "question": INTERVIEW_QUESTIONS["constraints"][0]})
    
    if complexity_signals["ui"]:
        selected.append({"category": "constraints", "question": INTERVIEW_QUESTIONS["constraints"][1]})
        selected.append({"category": "edge_cases", "question": INTERVIEW_QUESTIONS["edge_cases"][2]})
    
    if complexity_signals["security"]:
        selected.append({"category": "constraints", "question": INTERVIEW_QUESTIONS["constraints"][2]})
        selected.append({"category": "edge_cases", "question": INTERVIEW_QUESTIONS["edge_cases"][0]})
    
    # Fill remaining slots from general pool
    all_questions = []
    for cat, qs in INTERVIEW_QUESTIONS.items():
        for q in qs:
            all_questions.append({"category": cat, "question": q})
    
    existing_questions = {s["question"] for s in selected}
    for q in all_questions:
        if len(selected) >= num_questions:
            break
        if q["question"] not in existing_questions:
            selected.append(q)
            existing_questions.add(q["question"])
    
    return {
        "task": task_description,
        "depth": depth,
        "questions": selected[:num_questions],
        "estimated_questions": len(selected[:num_questions]),
        "instruction": (
            "Answer each question before proceeding. If a question is not applicable, "
            "say so explicitly. The plan will not be generated until all questions are addressed."
        ),
        "complexity_signals": {k: v for k, v in complexity_signals.items() if v},
    }


def generate_plan(task_description: str, interview_answers: Dict[str, str],
                  constraints: List[str] = None) -> Dict[str, Any]:
    """Generate a structured plan from interview answers.
    
    Args:
        task_description: Original task.
        interview_answers: {question: answer} from the interview.
        constraints: Additional constraints from user.
    
    Returns:
        {
            "plan_id": str,
            "task": str,
            "scope": str,
            "files_to_modify": [str],
            "steps": [{"step": int, "action": str, "file": str, "details": str}],
            "success_criteria": [str],
            "edge_cases": [str],
            "risks": [str],
            "estimated_complexity": str,
        }
    """
    import hashlib
    plan_id = hashlib.md5(task_description.encode()).hexdigest()[:8]
    
    # Extract scope from answers
    scope = "unknown"
    for q, a in interview_answers.items():
        if "scope" in q.lower():
            scope = a
            break
    
    # Extract success criteria
    success_criteria = []
    for q, a in interview_answers.items():
        if "done" in q.lower() or "complete" in q.lower() or "success" in q.lower():
            success_criteria.append(a)
    
    # Extract constraints
    all_constraints = list(constraints or [])
    for q, a in interview_answers.items():
        if "constraint" in q.lower() or "requirement" in q.lower():
            all_constraints.append(a)
    
    # Generate steps based on task analysis
    steps = []
    
    # Step 1: Always read/understand first
    steps.append({
        "step": 1,
        "action": "read",
        "file": "relevant files",
        "details": "Read and understand current state before making changes."
    })
    
    # Add implementation steps based on complexity
    has_multi_file = any(k in task_description.lower() for k in ["multi", "refactor", "system"])
    has_test = any(k in str(interview_answers).lower() for k in ["test", "spec", "verify"])
    
    steps.append({
        "step": 2,
        "action": "implement",
        "file": "target files",
        "details": f"Implement: {task_description}"
    })
    
    if has_multi_file:
        steps.append({
            "step": 3,
            "action": "verify_integration",
            "file": "all modified files",
            "details": "Verify all modified files work together correctly."
        })
    
    if has_test:
        steps.append({
            "step": len(steps) + 1,
            "action": "test",
            "file": "test files",
            "details": "Run existing tests and verify new functionality."
        })
    
    # Final step: always verify
    steps.append({
        "step": len(steps) + 1,
        "action": "verify",
        "file": "all",
        "details": "Final verification: syntax check, no regressions, meets success criteria."
    })
    
    # Estimate complexity
    complexity = "low"
    if len(steps) > 4 or has_multi_file:
        complexity = "high"
    elif len(steps) > 2:
        complexity = "medium"
    
    return {
        "plan_id": plan_id,
        "task": task_description,
        "scope": scope,
        "steps": steps,
        "success_criteria": success_criteria,
        "constraints": all_constraints,
        "estimated_complexity": complexity,
        "interview_completed": True,
    }


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

INTERVIEW_PLAN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "interview_plan",
        "description": (
            "Interview-mode task planning. Generates clarifying questions BEFORE "
            "creating a plan. Use this for any non-trivial task to ensure requirements "
            "are understood before implementation begins.\n\n"
            "Workflow: 1) Call with action='interview' to get questions, "
            "2) Answer each question, 3) Call with action='plan' and the answers "
            "to generate a structured plan."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["interview", "plan"],
                    "description": "'interview' to get questions, 'plan' to generate plan."
                },
                "task": {
                    "type": "string",
                    "description": "The task description to plan."
                },
                "depth": {
                    "type": "string",
                    "enum": ["quick", "standard", "deep"],
                    "description": "Interview depth. Default: standard.",
                    "default": "standard"
                },
                "answers": {
                    "type": "object",
                    "description": "Question-answer pairs from the interview (required for action='plan').",
                    "additionalProperties": {"type": "string"}
                },
                "constraints": {
                    "type": "array",
                    "description": "Additional constraints.",
                    "items": {"type": "string"}
                }
            },
            "required": ["action", "task"]
        }
    }
}


def _handle_interview_plan(args, **kw):
    action = args["action"]
    task = args["task"]
    
    if action == "interview":
        result = generate_interview(task, args.get("depth", "standard"))
    elif action == "plan":
        answers = args.get("answers", {})
        constraints = args.get("constraints", [])
        result = generate_plan(task, answers, constraints)
    else:
        return json.dumps({"error": f"Unknown action: {action}"})
    
    return json.dumps(result, indent=2, ensure_ascii=False)


try:
    from tools.registry import registry
    registry.register(
        name="interview_plan",
        toolset="agent",
        schema=INTERVIEW_PLAN_SCHEMA,
        handler=_handle_interview_plan,
        emoji="📋",
        max_result_size_chars=10000,
    )
except ImportError:
    pass
