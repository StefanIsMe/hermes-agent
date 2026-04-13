"""Tests for hashline_edit feature."""

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
        new_lines, err = _apply_replace(lines, f"4#{goodbye_hash}", None, ["def farewell():"])
        self.assertEqual(err, "")
        self.assertEqual(new_lines[3], "def farewell():")
        self.assertEqual(new_lines[0], "def hello():")  # Unchanged
    
    def test_empty_content(self):
        from tools.hashline_edit import format_hashlines
        self.assertEqual(format_hashlines(""), "")
        self.assertEqual(format_hashlines(None), "")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
