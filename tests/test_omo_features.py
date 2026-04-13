"""Tests for OMO-inspired features: hashline_edit, category_routing, 
background_manager, interview_planner."""

import hashlib
import json
import os
import sys
import tempfile
import unittest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHashlineEdit(unittest.TestCase):
    """Test hashline edit tool."""
    
    def test_compute_line_hash(self):
        from tools.hashline_edit import _compute_line_hash
        h1 = _compute_line_hash(1, "hello world")
        h2 = _compute_line_hash(1, "hello world")
        h3 = _compute_line_hash(1, "hello WORLD")
        self.assertEqual(h1, h2, "Same content should produce same hash")
        self.assertNotEqual(h1, h3, "Different content should produce different hash")
        self.assertEqual(len(h1), 2, "Hash should be 2 characters")
    
    def test_format_hashline(self):
        from tools.hashline_edit import format_hashline
        result = format_hashline(42, "def hello():")
        self.assertIn("42#", result)
        self.assertIn("|def hello():", result)
        self.assertTrue(result.startswith("  42#"), f"Expected leading spaces, got: {result[:10]}")
    
    def test_format_hashlines(self):
        from tools.hashline_edit import format_hashlines
        content = "line1\nline2\nline3"
        result = format_hashlines(content)
        lines = result.split("\n")
        self.assertEqual(len(lines), 3)
        self.assertIn("1#", lines[0])
        self.assertIn("2#", lines[1])
        self.assertIn("3#", lines[2])
    
    def test_parse_hashline_ref(self):
        from tools.hashline_edit import parse_hashline_ref
        line, h = parse_hashline_ref("42#AB")
        self.assertEqual(line, 42)
        self.assertEqual(h, "AB")
        
        with self.assertRaises(ValueError):
            parse_hashline_ref("invalid")
    
    def test_validate_line(self):
        from tools.hashline_edit import validate_line, _compute_line_hash
        lines = ["hello", "world", "foo"]
        expected = _compute_line_hash(2, "world")
        valid, actual = validate_line(lines, 2, expected)
        self.assertTrue(valid)
        
        valid, actual = validate_line(lines, 2, "XX")
        self.assertFalse(valid)
    
    def test_apply_replace(self):
        from tools.hashline_edit import _apply_replace, _compute_line_hash
        file_lines = ["line1", "line2", "line3"]
        pos_hash = _compute_line_hash(2, "line2")
        
        result, err = _apply_replace(file_lines, f"2#{pos_hash}", None, ["replaced"])
        self.assertEqual(err, "")
        self.assertEqual(result, ["line1", "replaced", "line3"])
    
    def test_apply_replace_stale_hash(self):
        from tools.hashline_edit import _apply_replace
        file_lines = ["line1", "line2", "line3"]
        
        result, err = _apply_replace(file_lines, "2#XX", None, ["replaced"])
        self.assertIn("HASH MISMATCH", err)
        self.assertEqual(result, file_lines)  # File unchanged
    
    def test_apply_range_replace(self):
        from tools.hashline_edit import _apply_replace, _compute_line_hash
        file_lines = ["a", "b", "c", "d", "e"]
        pos_hash = _compute_line_hash(2, "b")
        end_hash = _compute_line_hash(4, "d")
        
        result, err = _apply_replace(file_lines, f"2#{pos_hash}", f"4#{end_hash}", ["x", "y"])
        self.assertEqual(err, "")
        self.assertEqual(result, ["a", "x", "y", "e"])
    
    def test_apply_append(self):
        from tools.hashline_edit import _apply_append, _compute_line_hash
        file_lines = ["a", "b", "c"]
        pos_hash = _compute_line_hash(1, "a")
        
        result, err = _apply_append(file_lines, f"1#{pos_hash}", ["inserted"])
        self.assertEqual(err, "")
        self.assertEqual(result, ["a", "inserted", "b", "c"])
    
    def test_apply_prepend(self):
        from tools.hashline_edit import _apply_prepend, _compute_line_hash
        file_lines = ["a", "b", "c"]
        pos_hash = _compute_line_hash(2, "b")
        
        result, err = _apply_prepend(file_lines, f"2#{pos_hash}", ["before_b"])
        self.assertEqual(err, "")
        self.assertEqual(result, ["a", "before_b", "b", "c"])
    
    def test_roundtrip_file_edit(self):
        """Full roundtrip: read file, get hashes, edit by hash."""
        from tools.hashline_edit import (
            format_hashlines, _compute_line_hash, 
            _apply_replace, _apply_append
        )
        
        original = "def hello():\n    return 'world'\n\ndef goodbye():\n    return 'farewell'"
        lines = original.split("\n")
        
        # Get hash for "def goodbye():" line
        goodbye_hash = _compute_line_hash(4, "def goodbye():")
        
        # Edit line 4
        new_lines, err = _apply_replace(lines, f"4#{goodbye_hash}", None, ["def farewell():"], )
        self.assertEqual(err, "")
        self.assertEqual(new_lines[3], "def farewell():")
        self.assertEqual(new_lines[0], "def hello():")  # Unchanged
    
    def test_empty_content(self):
        from tools.hashline_edit import format_hashlines
        self.assertEqual(format_hashlines(""), "")
        self.assertEqual(format_hashlines(None), "")


class TestCategoryRouting(unittest.TestCase):
    """Test category-based model routing."""
    
    def test_classify_visual(self):
        from agent.category_routing import classify_task, DEFAULT_CATEGORIES
        result = classify_task("Fix the CSS layout on the mobile responsive navbar", DEFAULT_CATEGORIES)
        self.assertEqual(result["category"], "visual")
        self.assertGreater(result["confidence"], 0)
    
    def test_classify_research(self):
        from agent.category_routing import classify_task, DEFAULT_CATEGORIES
        result = classify_task("Research and analyze the latest AI agent frameworks", DEFAULT_CATEGORIES)
        self.assertEqual(result["category"], "deep")
    
    def test_classify_quick(self):
        from agent.category_routing import classify_task, DEFAULT_CATEGORIES
        result = classify_task("Fix typo in the README", DEFAULT_CATEGORIES)
        self.assertEqual(result["category"], "quick")
    
    def test_classify_architecture(self):
        from agent.category_routing import classify_task, DEFAULT_CATEGORIES
        result = classify_task("Refactor the database migration system with proper schema design", DEFAULT_CATEGORIES)
        self.assertIn(result["category"], ["architecture", "deep"])
    
    def test_empty_input(self):
        from agent.category_routing import classify_task, DEFAULT_CATEGORIES
        result = classify_task("", DEFAULT_CATEGORIES)
        self.assertIn("category", result)
        self.assertIn("confidence", result)
    
    def test_all_scores_returned(self):
        from agent.category_routing import classify_task, DEFAULT_CATEGORIES
        result = classify_task("Build a React component with API integration", DEFAULT_CATEGORIES)
        self.assertIn("all_scores", result)
        self.assertGreater(len(result["all_scores"]), 0)


class TestBackgroundManager(unittest.TestCase):
    """Test background agent manager."""
    
    def test_create_task(self):
        from tools.background_manager import BackgroundAgentManager
        mgr = BackgroundAgentManager()
        task = mgr.create_task("test task")
        self.assertEqual(task.status.value, "pending")
        self.assertTrue(task.id.startswith("bg_"))
    
    def test_start_task(self):
        from tools.background_manager import BackgroundAgentManager
        mgr = BackgroundAgentManager()
        task = mgr.create_task("test")
        success, msg = mgr.start_task(task.id)
        self.assertTrue(success)
        self.assertEqual(task.status.value, "running")
    
    def test_concurrency_limit(self):
        from tools.background_manager import BackgroundAgentManager
        mgr = BackgroundAgentManager(max_concurrent=2)
        t1 = mgr.create_task("task1")
        t2 = mgr.create_task("task2")
        t3 = mgr.create_task("task3")
        
        mgr.start_task(t1.id)
        mgr.start_task(t2.id)
        success, msg = mgr.start_task(t3.id)
        self.assertFalse(success)
        self.assertIn("Concurrency limit", msg)
    
    def test_circuit_breaker(self):
        from tools.background_manager import BackgroundAgentManager
        mgr = BackgroundAgentManager()
        task = mgr.create_task("test", max_attempts=3)
    
        # Fail 3 times with DIFFERENT errors (to avoid loop detection)
        errors = ["timeout error on attempt 1", "connection refused on attempt 2", "rate limit 429 on attempt 3"]
        for i, err in enumerate(errors):
            mgr.start_task(task.id)
            should_retry, msg = mgr.record_failure(task.id, err)
    
        # 3rd failure should break circuit
        self.assertFalse(should_retry)
        self.assertIn("Circuit broken", msg)
    
    def test_permanent_error_no_retry(self):
        from tools.background_manager import BackgroundAgentManager
        mgr = BackgroundAgentManager()
        task = mgr.create_task("test")
        mgr.start_task(task.id)
        
        should_retry, msg = mgr.record_failure(task.id, "SyntaxError: invalid syntax")
        self.assertFalse(should_retry)
        self.assertIn("Permanent error", msg)
    
    def test_success_resets_circuit(self):
        from tools.background_manager import BackgroundAgentManager
        mgr = BackgroundAgentManager()
        task = mgr.create_task("test")
        
        # Fail once
        mgr.start_task(task.id)
        mgr.record_failure(task.id, "timeout")
        
        # Then succeed
        mgr.start_task(task.id)
        mgr.record_success(task.id, "done")
        
        self.assertEqual(task.status.value, "completed")
    
    def test_loop_detection(self):
        from tools.background_manager import BackgroundAgentManager
        mgr = BackgroundAgentManager()
        task = mgr.create_task("test", max_attempts=10)
        
        # Same error 3 times = loop
        for i in range(3):
            mgr.start_task(task.id)
            should_retry, msg = mgr.record_failure(task.id, "same error every time")
        
        self.assertFalse(should_retry)
        self.assertIn("Loop detected", msg)
    
    def test_error_classifier(self):
        from tools.background_manager import ErrorClassifier, ErrorType
        self.assertEqual(ErrorClassifier.classify("Connection timeout"), ErrorType.TRANSIENT)
        self.assertEqual(ErrorClassifier.classify("SyntaxError: invalid"), ErrorType.PERMANENT)
        self.assertEqual(ErrorClassifier.classify("Rate limit exceeded"), ErrorType.TRANSIENT)
        self.assertEqual(ErrorClassifier.classify("File not found"), ErrorType.PERMANENT)
        self.assertEqual(ErrorClassifier.classify("something weird"), ErrorType.UNKNOWN)


class TestInterviewPlanner(unittest.TestCase):
    """Test interview-mode planning."""
    
    def test_quick_interview(self):
        from tools.interview_planner import generate_interview
        result = generate_interview("Fix a bug", depth="quick")
        self.assertLessEqual(len(result["questions"]), 3)
        self.assertIn("instruction", result)
    
    def test_standard_interview(self):
        from tools.interview_planner import generate_interview
        result = generate_interview("Build a REST API endpoint", depth="standard")
        self.assertGreater(len(result["questions"]), 0)
        self.assertLessEqual(len(result["questions"]), 7)
    
    def test_deep_interview(self):
        from tools.interview_planner import generate_interview
        result = generate_interview("Refactor the entire authentication system", depth="deep")
        self.assertGreaterEqual(len(result["questions"]), 5)
    
    def test_complexity_detection(self):
        from tools.interview_planner import generate_interview
        result = generate_interview("Migrate the database schema and refactor API endpoints")
        self.assertIn("complexity_signals", result)
        self.assertTrue(len(result["complexity_signals"]) > 0)
    
    def test_plan_generation(self):
        from tools.interview_planner import generate_plan
        answers = {
            "What is the exact scope?": "Single file",
            "How will we know this is done?": "Tests pass",
        }
        result = generate_plan("Fix a bug", answers)
        self.assertIn("plan_id", result)
        self.assertIn("steps", result)
        self.assertGreater(len(result["steps"]), 0)
        self.assertTrue(result["interview_completed"])
    
    def test_plan_has_verify_step(self):
        from tools.interview_planner import generate_plan
        result = generate_plan("Add feature", {})
        steps = result["steps"]
        last_step = steps[-1]
        self.assertEqual(last_step["action"], "verify")


class TestIntegration(unittest.TestCase):
    """Integration tests — all 4 features importable together."""
    
    def test_all_imports(self):
        """All features should import without error."""
        from tools.hashline_edit import format_hashlines, hashline_edit_tool
        from agent.category_routing import classify_task, route_task
        from tools.background_manager import BackgroundAgentManager
        from tools.interview_planner import generate_interview, generate_plan
        # If we get here, all imports succeeded
    
    def test_hashline_roundtrip_with_tempfile(self):
        """Full roundtrip: write file, hashline_read, hashline_edit, verify."""
        from tools.hashline_edit import format_hashlines, _compute_line_hash, _apply_replace
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def hello():\n    return 'world'\n\ndef goodbye():\n    return 'farewell'")
            f.flush()
            path = f.name
        
        try:
            content = open(path).read()
            lines = content.split("\n")
            
            # Get hashes
            hash2 = _compute_line_hash(2, lines[1])
            
            # Edit
            new_lines, err = _apply_replace(lines, f"2#{hash2}", None, ["    return 'universe'"])
            self.assertEqual(err, "")
            
            # Verify
            self.assertEqual(new_lines[1], "    return 'universe'")
            self.assertEqual(new_lines[0], "def hello():")  # Unchanged
            
            # Verify Python syntax
            new_content = "\n".join(new_lines)
            compile(new_content, path, "exec")  # Should not raise
        finally:
            os.unlink(path)
    
    def test_category_routing_with_background_manager(self):
        """Route a task and manage it in background."""
        from agent.category_routing import classify_task, DEFAULT_CATEGORIES
        from tools.background_manager import BackgroundAgentManager
        
        result = classify_task("Build a React dashboard", DEFAULT_CATEGORIES)
        mgr = BackgroundAgentManager()
        task = mgr.create_task(f"[{result['category']}] Build a React dashboard")
        mgr.start_task(task.id)
        mgr.record_success(task.id, "Dashboard built")
        
        self.assertEqual(task.status.value, "completed")
    
    def test_interview_then_background(self):
        """Interview for a task, then manage execution in background."""
        from tools.interview_planner import generate_interview, generate_plan
        from tools.background_manager import BackgroundAgentManager
        
        # Interview
        interview = generate_interview("Build a REST API", depth="quick")
        self.assertGreater(len(interview["questions"]), 0)
        
        # Plan
        plan = generate_plan("Build a REST API", {"scope": "multi-file"})
        self.assertGreater(len(plan["steps"]), 0)
        
        # Execute in background
        mgr = BackgroundAgentManager()
        for step in plan["steps"]:
            task = mgr.create_task(step["details"])
            mgr.start_task(task.id)
            mgr.record_success(task.id, f"Step {step['step']} done")
        
        self.assertEqual(json.loads(mgr.get_status())["total_tasks"], len(plan["steps"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
