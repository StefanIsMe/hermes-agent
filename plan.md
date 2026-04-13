# Plan: OMO-Inspired Features for Hermes Agent
## Branch: feat/omo-inspiration
## Started: 2026-04-13

### Features

1. **Hashline Edit Tool** — Content-hash anchored file edits
   - Status: IN PROGRESS
   - File: `tools/hashline_edit.py`
   - Tests: `tests/test_hashline_edit.py`

2. **Category-Based Model Routing** — Auto-route to optimal model
   - Status: PENDING
   - Files: `agent/category_routing.py`, config integration

3. **Enhanced Background Agent Manager** — Circuit breakers, error recovery
   - Status: PENDING
   - Files: `tools/background_manager.py`

4. **Interview-Mode Planning** — Prometheus-style planning
   - Status: PENDING
   - Files: `tools/interview_planner.py`

### Decisions
- Using `hashlib.sha256` (Python stdlib) instead of Bun-specific APIs
- Category routing config in `~/.hermes/config.yaml` under `categories:` key
- Background manager wraps existing `delegate_tool.py` patterns
- Interview planner is a standalone tool, not a hook

### Verification
- Each feature gets py_compile check + test file
- Integration test: all 4 features importable together
