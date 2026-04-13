"""Tests for hashline_auto plugin hooks."""

import json
import os
import tempfile
import unittest


class TestHashlineAutoHooks(unittest.TestCase):
    """Test hashline auto-trigger plugin."""
    
    def setUp(self):
        # Import plugin functions directly
        import sys
        sys.path.insert(0, os.path.expanduser("~/.hermes/plugins"))
        from hashline_auto import (
            _on_pre_tool_call, _on_post_tool_call,
            _suggest_hashline_for_patch,
            _suggest_hashline_for_write,
            _suggest_hashline_for_terminal,
            _inject_hashline_after_read,
            _is_text_file,
        )
        self._on_pre = _on_pre_tool_call
        self._on_post = _on_post_tool_call
        self._patch = _suggest_hashline_for_patch
        self._write = _suggest_hashline_for_write
        self._terminal = _suggest_hashline_for_terminal
        self._read = _inject_hashline_after_read
        self._is_text = _is_text_file
    
    # -- _is_text_file ----------------------------------------------------
    
    def test_is_text_file_py(self):
        self.assertTrue(self._is_text("foo.py"))
        self.assertTrue(self._is_text("/path/to/bar.tsx"))
        self.assertTrue(self._is_text("config.yaml"))
    
    def test_is_text_file_dockerfile(self):
        self.assertTrue(self._is_text("Dockerfile"))
        self.assertTrue(self._is_text("Makefile"))
    
    def test_is_text_file_binary(self):
        self.assertFalse(self._is_text("image.png"))
        self.assertFalse(self._is_text("archive.zip"))
        self.assertFalse(self._is_text(""))
        self.assertFalse(self._is_text(None))
    
    # -- pre_tool_call: patch ---------------------------------------------
    
    def test_patch_suggests_hashline(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def hello():\n    return 'world'\n" * 20)
            f.flush()
            path = f.name
        
        try:
            result = self._patch({
                "mode": "replace",
                "path": path,
                "old_string": "def hello():\n    return 'world'\n" * 5,
                "new_string": "def hello():\n    return 'universe'\n",
            })
            self.assertIsNotNone(result)
            self.assertIn("HASHLINE", result["context"])
            self.assertIn("hashline_edit", result["context"])
        finally:
            os.unlink(path)
    
    def test_patch_no_suggest_for_short_string(self):
        result = self._patch({
            "mode": "replace",
            "path": "/tmp/test.py",
            "old_string": "short",
            "new_string": "new",
        })
        self.assertIsNone(result)
    
    def test_patch_no_suggest_for_non_replace(self):
        result = self._patch({
            "mode": "patch",
            "path": "/tmp/test.py",
            "old_string": "anything",
        })
        self.assertIsNone(result)
    
    # -- pre_tool_call: write_file ----------------------------------------
    
    def test_write_suggests_hashline_for_existing_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# " + "x" * 300)  # Large enough file
            f.flush()
            path = f.name
        
        try:
            result = self._write({
                "path": path,
                "content": "new content",
            })
            self.assertIsNotNone(result)
            self.assertIn("HASHLINE", result["context"])
            self.assertIn("write_file", result["context"])
        finally:
            os.unlink(path)
    
    def test_write_no_suggest_for_new_file(self):
        result = self._write({
            "path": "/tmp/does_not_exist_" + os.urandom(8).hex() + ".py",
            "content": "new file content",
        })
        self.assertIsNone(result)
    
    def test_write_no_suggest_for_small_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("tiny")
            f.flush()
            path = f.name
        
        try:
            result = self._write({"path": path, "content": "new"})
            self.assertIsNone(result)  # Too small to suggest hashline
        finally:
            os.unlink(path)
    
    # -- pre_tool_call: terminal ------------------------------------------
    
    def test_terminal_detects_sed_i(self):
        result = self._terminal({"command": "sed -i 's/old/new/g' file.py"})
        self.assertIsNotNone(result)
        self.assertIn("HASHLINE", result["context"])
        self.assertIn("sed -i", result["context"])
    
    def test_terminal_detects_sed_capital_I(self):
        result = self._terminal({"command": "sed -I 's/old/new/g' file.py"})
        self.assertIsNotNone(result)
        self.assertIn("sed", result["context"])
    
    def test_terminal_no_suggest_for_grep(self):
        result = self._terminal({"command": "grep 'pattern' file.py"})
        self.assertIsNone(result)
    
    def test_terminal_no_suggest_for_cat(self):
        result = self._terminal({"command": "cat file.py"})
        self.assertIsNone(result)
    
    def test_terminal_no_suggest_for_ls(self):
        result = self._terminal({"command": "ls -la"})
        self.assertIsNone(result)
    
    # -- post_tool_call: read_file ----------------------------------------
    
    def test_read_injects_hashline_context(self):
        result_content = json.dumps({
            "content": "line1\nline2\nline3\nline4\nline5\nline6",
            "total_lines": 6,
        })
        result = self._read({"path": "/tmp/test.py"}, result_content)
        self.assertIsNotNone(result)
        self.assertIn("HASHLINE", result["context"])
        self.assertIn("hashline_read", result["context"])
    
    def test_read_no_inject_for_short_file(self):
        result_content = json.dumps({
            "content": "a\nb",
            "total_lines": 2,
        })
        result = self._read({"path": "/tmp/test.py"}, result_content)
        self.assertIsNone(result)  # Too short
    
    def test_read_no_inject_for_binary(self):
        result = self._read({"path": "/tmp/image.png"}, "binary data")
        self.assertIsNone(result)
    
    # -- pre_tool_call: routing -------------------------------------------
    
    def test_pre_tool_call_routes_patch(self):
        """The pre_tool_call hook should route patch to _suggest_hashline_for_patch."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("x" * 200)
            f.flush()
            path = f.name
        
        try:
            result = self._on_pre("patch", {
                "mode": "replace",
                "path": path,
                "old_string": "x" * 50,
                "new_string": "y" * 50,
            })
            self.assertIsNotNone(result)
            self.assertIn("HASHLINE", result["context"])
        finally:
            os.unlink(path)
    
    def test_pre_tool_call_ignores_non_relevant(self):
        """Non-file tools should return None."""
        self.assertIsNone(self._on_pre("terminal", {"command": "ls"}))
        self.assertIsNone(self._on_pre("memory", {"action": "add", "content": "test"}))
        self.assertIsNone(self._on_pre("browser_navigate", {"url": "https://example.com"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
