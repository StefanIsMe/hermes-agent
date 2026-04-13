"""Category-Based Model Router — Auto-route tasks to optimal models.

Inspired by Oh My OpenAgent's category system where work types map to optimal models.

Categories:
  - visual: Frontend, UI/UX, design tasks
  - deep: Autonomous research, long-horizon analysis
  - quick: Single-file changes, typos, simple fixes
  - architecture: Hard logic, system design, complex reasoning
  
Each category maps to a provider/model pair configured in ~/.hermes/config.yaml
under the `categories:` key.
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default category definitions
# ---------------------------------------------------------------------------

DEFAULT_CATEGORIES = {
    "visual": {
        "description": "Frontend, UI/UX, design, CSS, React components",
        "keywords": [
            "css", "style", "layout", "component", "react", "vue", "angular",
            "frontend", "ui", "ux", "design", "responsive", "mobile", "desktop",
            "button", "form", "modal", "dropdown", "nav", "header", "footer",
            "color", "font", "animation", "transition", "flexbox", "grid",
            "tailwind", "bootstrap", "material", "antd", "chakra",
            "pixel", "margin", "padding", "border", "shadow", "gradient",
        ],
        "default_model": None,  # Uses system default unless configured
        "priority": 3,
    },
    "deep": {
        "description": "Autonomous research, deep analysis, multi-step investigation",
        "keywords": [
            "research", "analyze", "investigate", "explore", "study",
            "comprehensive", "deep dive", "thorough", "detailed analysis",
            "compare", "evaluate", "assess", "benchmark", "survey",
            "landscape", "ecosystem", "state of the art", "overview",
            "report", "findings", "data analysis", "statistics",
        ],
        "default_model": None,
        "priority": 2,
    },
    "quick": {
        "description": "Single-file changes, typos, simple fixes, minor edits",
        "keywords": [
            "fix typo", "typo", "rename", "simple", "quick", "minor",
            "single file", "one line", "small change", "bump",
            "update version", "add comment", "remove comment",
            "whitespace", "format", "lint", "lint fix",
        ],
        "default_model": None,
        "priority": 1,  # Lowest cost — use fastest model
    },
    "architecture": {
        "description": "Hard logic, system design, complex reasoning, refactoring",
        "keywords": [
            "architect", "design", "refactor", "restructure", "reorganize",
            "pattern", "abstraction", "interface", "protocol", "schema",
            "migration", "database", "api design", "system design",
            "performance", "optimization", "scalability", "concurrency",
            "algorithm", "data structure", "complex", "multi-file",
            "integration", "workflow", "pipeline", "orchestrat",
        ],
        "default_model": None,
        "priority": 4,  # Highest quality needed
    },
}


def classify_task(message: str, categories: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Classify a task message into a category.
    
    Returns:
        {
            "category": str,          # Best matching category
            "confidence": float,      # 0.0 - 1.0
            "all_scores": dict,       # Scores for all categories
            "suggested_model": str,   # Model to use (or None for default)
        }
    """
    cats = categories or DEFAULT_CATEGORIES
    message_lower = message.lower()
    words = set(message_lower.split())
    
    scores = {}
    for cat_name, cat_config in cats.items():
        keywords = cat_config.get("keywords", [])
        if not keywords:
            scores[cat_name] = 0.0
            continue
        
        # Count keyword matches (word-boundary aware)
        matches = 0
        for kw in keywords:
            if kw in message_lower:
                matches += 1
            elif any(w.startswith(kw[:4]) for w in words if len(w) > 3):
                matches += 0.5  # Partial match
        
        # Normalize by keyword count
        scores[cat_name] = min(1.0, matches / max(len(keywords) * 0.15, 1))
    
    if not scores or max(scores.values()) == 0:
        # No match — use architecture as safe default for unknown tasks
        return {
            "category": "architecture",
            "confidence": 0.1,
            "all_scores": scores,
            "suggested_model": None,
        }
    
    # Best category
    best_cat = max(scores, key=scores.get)
    confidence = scores[best_cat]
    
    # Get suggested model from category config
    cat_config = cats.get(best_cat, {})
    suggested_model = cat_config.get("default_model")
    
    return {
        "category": best_cat,
        "confidence": round(confidence, 3),
        "all_scores": {k: round(v, 3) for k, v in sorted(scores.items(), key=lambda x: -x[1])},
        "suggested_model": suggested_model,
    }


def load_categories_from_config() -> Dict[str, Any]:
    """Load category definitions from ~/.hermes/config.yaml.
    
    Config format:
        categories:
          visual:
            default_model: "minimax/minimax-m2.7"
            keywords: ["css", "style", ...]
          deep:
            default_model: "nous/xiaomi-mimo-v2-pro"
    """
    import yaml
    from pathlib import Path
    
    config_path = Path.home() / ".hermes" / "config.yaml"
    if not config_path.exists():
        return DEFAULT_CATEGORIES
    
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        
        user_cats = config.get("categories", {})
        if not user_cats:
            return DEFAULT_CATEGORIES
        
        # Merge user categories with defaults
        merged = {}
        for cat_name, default_config in DEFAULT_CATEGORIES.items():
            merged[cat_name] = dict(default_config)
            if cat_name in user_cats:
                merged[cat_name].update(user_cats[cat_name])
        
        # Add any user-defined categories not in defaults
        for cat_name, cat_config in user_cats.items():
            if cat_name not in merged:
                merged[cat_name] = cat_config
        
        return merged
    except Exception as e:
        logger.warning(f"Failed to load categories from config: {e}")
        return DEFAULT_CATEGORIES


def route_task(message: str) -> str:
    """Route a task to its optimal category. Returns JSON result."""
    categories = load_categories_from_config()
    result = classify_task(message, categories)
    return json.dumps(result, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

CATEGORY_ROUTE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "category_route",
        "description": (
            "Classify a task into a work category (visual/deep/quick/architecture) "
            "and get the suggested model for that category. Categories are configured "
            "in ~/.hermes/config.yaml under the 'categories:' key. Use this before "
            "delegating tasks to select the optimal model."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The task description to classify."
                }
            },
            "required": ["message"]
        }
    }
}


def _handle_category_route(args, **kw):
    return route_task(args["message"])


try:
    from tools.registry import registry
    registry.register(
        name="category_route",
        toolset="agent",
        schema=CATEGORY_ROUTE_SCHEMA,
        handler=_handle_category_route,
        emoji="🎯",
        max_result_size_chars=5000,
    )
except ImportError:
    pass  # Can still be used as a module
