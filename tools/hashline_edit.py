"""Hashline Edit Tool — Content-hash anchored file edits.

Inspired by Oh My OpenAgent's Hashline system and Can Bölük's "The Harness Problem"
(https://blog.can.ac/2026/02/12/the-harness-problem/).

Every line in a file gets a content hash tag: `LINE#HASH|content`
The agent edits by referencing those tags. If the file changed since the last read,
the hash won't match and the edit is rejected BEFORE corruption occurs.

This eliminates:
- Stale-line errors (editing content that no longer exists)
- Whitespace reproduction failures
- Off-by-one edits from line number drift
"""

import hashlib
import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

from tools.registry import registry, tool_error

# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------

# 2-char hash dictionary (256 entries for xxHash32 compatibility with OMO)
# We use sha256 first byte → 2-char base36 for compact display
_HASH_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+/"

def _compute_line_hash(line_number: int, content: str) -> str:
    """Compute a 2-character hash for a line.
    
    Uses sha256 of trimmed content. Empty/whitespace-only lines use line number as salt.
    """
    stripped = content.rstrip("\r\n")
    # Python 3.11 doesn't support \p{} — use str methods instead
    significant = any(c.isalnum() for c in stripped) if stripped else False
    if not significant and stripped is not None:
        # Non-significant lines (whitespace only) use line number as seed
        seed = str(line_number).encode()
        data = stripped.encode() + seed
    else:
        data = stripped.encode()
    
    h = hashlib.sha256(data).digest()
    # Use first byte to index into our 64-char dictionary (2 chars = 64*64 = 4096 combos)
    idx1 = h[0] % 64
    idx2 = h[1] % 64
    return _HASH_CHARS[idx1] + _HASH_CHARS[idx2]


def format_hashline(line_number: int, content: str) -> str:
    """Format a single line with its hash anchor."""
    h = _compute_line_hash(line_number, content)
    return f"{line_number:4d}#{h}|{content}"


def format_hashlines(content: str) -> str:
    """Format entire file content with hash-anchored line numbers."""
    if not content:
        return ""
    lines = content.split("\n")
    return "\n".join(format_hashline(i + 1, line) for i, line in enumerate(lines))


def parse_hashline_ref(ref: str) -> Tuple[int, str]:
    """Parse a hashline reference like '42#AB' into (line_number, hash)."""
    match = re.match(r'^(\d+)#([A-Za-z0-9+/]{2})$', ref.strip())
    if not match:
        raise ValueError(f"Invalid hashline reference: {ref!r} (expected format: '42#AB')")
    return int(match.group(1)), match.group(2)


def validate_line(file_lines: List[str], line_number: int, expected_hash: str) -> Tuple[bool, str]:
    """Validate that a line's current hash matches the expected hash.
    
    Returns (is_valid, actual_hash).
    """
    if line_number < 1 or line_number > len(file_lines):
        return False, ""
    actual = _compute_line_hash(line_number, file_lines[line_number - 1])
    return actual == expected_hash, actual


# ---------------------------------------------------------------------------
# Edit operations
# ---------------------------------------------------------------------------

def _apply_replace(file_lines: List[str], pos_ref: str, end_ref: Optional[str],
                   new_lines: Optional[List[str]]) -> Tuple[List[str], str]:
    """Apply a replace operation anchored to hashline references.
    
    Returns (new_file_lines, error_message).
    """
    pos_line, pos_hash = parse_hashline_ref(pos_ref)
    
    # Validate pos anchor
    valid, actual_hash = validate_line(file_lines, pos_line, pos_hash)
    if not valid:
        return file_lines, (
            f"HASH MISMATCH at line {pos_line}: expected #{pos_hash}, "
            f"got #{actual_hash}. File changed since last read. "
            f"Re-read the file to get fresh hash anchors."
        )
    
    if end_ref:
        end_line, end_hash = parse_hashline_ref(end_ref)
        valid_end, actual_end_hash = validate_line(file_lines, end_line, end_hash)
        if not valid_end:
            return file_lines, (
                f"HASH MISMATCH at end line {end_line}: expected #{end_hash}, "
                f"got #{actual_end_hash}. File changed since last read."
            )
        
        # Replace range [pos_line, end_line] with new_lines
        if new_lines is None:
            # Delete the range
            new_content = file_lines[:pos_line - 1] + file_lines[end_line:]
        else:
            new_content = file_lines[:pos_line - 1] + new_lines + file_lines[end_line:]
    else:
        # Single line replace at pos_line
        if new_lines is None:
            # Delete single line
            new_content = file_lines[:pos_line - 1] + file_lines[pos_line:]
        elif len(new_lines) == 1:
            # Replace single line
            new_content = file_lines[:pos_line - 1] + new_lines + file_lines[pos_line:]
        else:
            # Replace single line with multiple lines
            new_content = file_lines[:pos_line - 1] + new_lines + file_lines[pos_line:]
    
    return new_content, ""


def _apply_append(file_lines: List[str], pos_ref: str,
                  new_lines: List[str]) -> Tuple[List[str], str]:
    """Append lines after the given hashline reference."""
    pos_line, pos_hash = parse_hashline_ref(pos_ref)
    valid, actual_hash = validate_line(file_lines, pos_line, pos_hash)
    if not valid:
        return file_lines, (
            f"HASH MISMATCH at line {pos_line}: expected #{pos_hash}, "
            f"got #{actual_hash}. File changed since last read."
        )
    
    new_content = file_lines[:pos_line] + new_lines + file_lines[pos_line:]
    return new_content, ""


def _apply_prepend(file_lines: List[str], pos_ref: str,
                   new_lines: List[str]) -> Tuple[List[str], str]:
    """Prepend lines before the given hashline reference."""
    pos_line, pos_hash = parse_hashline_ref(pos_ref)
    valid, actual_hash = validate_line(file_lines, pos_line, pos_hash)
    if not valid:
        return file_lines, (
            f"HASH MISMATCH at line {pos_line}: expected #{pos_hash}, "
            f"got #{actual_hash}. File changed since last read."
        )
    
    new_content = file_lines[:pos_line - 1] + new_lines + file_lines[pos_line - 1:]
    return new_content, ""


# ---------------------------------------------------------------------------
# Diff generation
# ---------------------------------------------------------------------------

def _generate_diff(original: List[str], modified: List[str], path: str) -> str:
    """Generate a simple unified-style diff."""
    import difflib
    diff = difflib.unified_diff(
        original, modified,
        fromfile=f"a/{path}", tofile=f"b/{path}",
        lineterm=""
    )
    return "\n".join(diff)


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------

def hashline_edit_tool(path: str, edits: list, delete: bool = False,
                       rename: Optional[str] = None, task_id: str = "default") -> str:
    """Hash-anchored file edit tool.
    
    Args:
        path: Absolute path to the file to edit.
        edits: List of edit operations. Each edit has:
            - op: 'replace' | 'append' | 'prepend'
            - pos: Primary anchor in LINE#HASH format (e.g., '42#AB')
            - end: Range end anchor in LINE#HASH format (optional, for range replace)
            - lines: Replacement lines (list of strings, single string, or null for delete)
        delete: If True, delete the file instead of editing.
        rename: If set, rename the file after edits.
        task_id: Task ID for staleness tracking.
    """
    file_path = Path(path)
    
    # Handle delete
    if delete:
        if not file_path.exists():
            return tool_error(f"File not found: {path}")
        sensitive_err = _check_sensitive_path(str(path))
        if sensitive_err:
            return tool_error(sensitive_err)
        file_path.unlink()
        return json.dumps({"status": "deleted", "path": path})
    
    # Read file
    if not file_path.exists():
        return tool_error(f"File not found: {path}")
    
    sensitive_err = _check_sensitive_path(str(path))
    if sensitive_err:
        return tool_error(sensitive_err)
    
    content = file_path.read_text(encoding="utf-8", errors="replace")
    file_lines = content.split("\n")
    original_lines = list(file_lines)
    
    # Apply edits
    applied = 0
    errors = []
    
    for edit in edits:
        op = edit.get("op", "replace")
        pos = edit.get("pos")
        end = edit.get("end")
        raw_lines = edit.get("lines")
        
        # Normalize lines
        if raw_lines is None:
            new_lines = None  # Delete
        elif isinstance(raw_lines, str):
            new_lines = raw_lines.split("\n")
        elif isinstance(raw_lines, list):
            new_lines = raw_lines
        else:
            errors.append(f"Invalid 'lines' type: {type(raw_lines)}")
            continue
        
        if not pos:
            errors.append("Edit missing 'pos' anchor")
            continue
        
        if op == "replace":
            file_lines, err = _apply_replace(file_lines, pos, end, new_lines)
        elif op == "append":
            if not new_lines:
                errors.append("Append requires non-null 'lines'")
                continue
            file_lines, err = _apply_append(file_lines, pos, new_lines)
        elif op == "prepend":
            if not new_lines:
                errors.append("Prepend requires non-null 'lines'")
                continue
            file_lines, err = _apply_prepend(file_lines, pos, new_lines)
        else:
            errors.append(f"Unknown operation: {op}")
            continue
        
        if err:
            errors.append(err)
            break  # Stop on first hash mismatch — don't apply partial edits
        applied += 1
    
    if errors:
        return tool_error("; ".join(errors))
    
    # Write modified content
    new_content = "\n".join(file_lines)
    
    # Syntax check for Python files
    if path.endswith(".py"):
        try:
            compile(new_content, path, "exec")
        except SyntaxError as e:
            return tool_error(
                f"Syntax error after edit (edit rejected): {e.msg} "
                f"line {e.lineno}. Original file preserved."
            )
    
    file_path.write_text(new_content, encoding="utf-8")
    
    # Handle rename
    if rename:
        rename_path = Path(rename)
        rename_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.rename(rename_path)
        path = rename
    
    # Generate diff
    diff = _generate_diff(original_lines, file_lines, path)
    
    result = {
        "status": "ok",
        "path": path,
        "edits_applied": applied,
        "lines_before": len(original_lines),
        "lines_after": len(file_lines),
    }
    if diff:
        result["diff"] = diff[:5000]  # Truncate large diffs
    
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Hashline reader (formats file with hash anchors)
# ---------------------------------------------------------------------------

def hashline_read_tool(path: str, offset: int = 1, limit: int = 500,
                       task_id: str = "default") -> str:
    """Read a file with hash-anchored line numbers for editing.
    
    Returns content formatted as:
        LINE#HASH|content
    
    Use the hash anchors (e.g., '42#AB') as pos/end references in hashline_edit.
    """
    file_path = Path(path)
    if not file_path.exists():
        return tool_error(f"File not found: {path}")
    
    sensitive_err = _check_sensitive_path(str(path))
    if sensitive_err:
        return tool_error(sensitive_err)
    
    content = file_path.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")
    total_lines = len(lines)
    
    # Apply offset/limit (1-indexed)
    start = max(0, offset - 1)
    end = min(total_lines, start + limit)
    
    formatted = "\n".join(
        format_hashline(i + 1, lines[i]) for i in range(start, end)
    )
    
    result = {
        "content": formatted,
        "total_lines": total_lines,
        "shown_from": offset,
        "shown_to": end,
        "note": "Use LINE#HASH anchors (e.g., '42#AB') as pos/end in hashline_edit tool."
    }
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Sensitive path check (import from file_tools if available)
# ---------------------------------------------------------------------------

def _check_sensitive_path(path: str) -> Optional[str]:
    """Check if path is sensitive. Returns error message if blocked."""
    try:
        from tools.file_tools import _check_sensitive_path as _csp
        return _csp(path)
    except ImportError:
        pass
    
    # Fallback: basic checks
    sensitive_patterns = [
        "/.env", "/.ssh/", "/.gnupg/", "/.aws/", "/.gcloud/",
        "id_rsa", "id_ed25519", "*.pem", "*.key",
    ]
    for pattern in sensitive_patterns:
        if pattern in path:
            return f"Sensitive path blocked: {path} (matches pattern: {pattern})"
    return None


# ---------------------------------------------------------------------------
# Register with tool registry
# ---------------------------------------------------------------------------

HASHLINE_EDIT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hashline_edit",
        "description": (
            "Hash-anchored file editing. Every line has a content hash (LINE#HASH). "
            "Edit by referencing those anchors instead of reproducing content. "
            "If the file changed since read, hash mismatch rejects the edit before corruption. "
            "Eliminates stale-line errors and whitespace reproduction failures.\n\n"
            "Workflow: 1) hashline_read to get anchored content, 2) hashline_edit "
            "with pos='LINE#HASH' references from the read output."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit."
                },
                "edits": {
                    "type": "array",
                    "description": "Array of edit operations. Each: {op, pos, end?, lines}.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["replace", "append", "prepend"],
                                "description": "Edit operation mode."
                            },
                            "pos": {
                                "type": "string",
                                "description": "Primary anchor in LINE#HASH format (e.g., '42#AB')."
                            },
                            "end": {
                                "type": "string",
                                "description": "Range end anchor in LINE#HASH format (optional)."
                            },
                            "lines": {
                                "type": ["array", "string", "null"],
                                "description": "Replacement lines. null deletes. String auto-splits on newline.",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["op", "pos", "lines"]
                    }
                },
                "delete": {
                    "type": "boolean",
                    "description": "Delete the file instead of editing."
                },
                "rename": {
                    "type": "string",
                    "description": "Rename file to this path after edits."
                }
            },
            "required": ["path", "edits"]
        }
    }
}

HASHLINE_READ_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hashline_read",
        "description": (
            "Read a file with hash-anchored line numbers. Each line is formatted as "
            "'LINE#HASH|content'. Use the LINE#HASH anchors as references in hashline_edit "
            "to make precise edits that reject on stale content."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to read."
                },
                "offset": {
                    "type": "integer",
                    "description": "Starting line number (1-indexed).",
                    "default": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum lines to return.",
                    "default": 500
                }
            },
            "required": ["path"]
        }
    }
}


def _handle_hashline_edit(args, **kw):
    return hashline_edit_tool(
        path=args["path"],
        edits=args.get("edits", []),
        delete=args.get("delete", False),
        rename=args.get("rename"),
        task_id=kw.get("task_id", "default"),
    )


def _handle_hashline_read(args, **kw):
    return hashline_read_tool(
        path=args["path"],
        offset=args.get("offset", 1),
        limit=args.get("limit", 500),
        task_id=kw.get("task_id", "default"),
    )


registry.register(
    name="hashline_edit",
    toolset="file",
    schema=HASHLINE_EDIT_SCHEMA,
    handler=_handle_hashline_edit,
    emoji="⚓",
    max_result_size_chars=100_000,
)

registry.register(
    name="hashline_read",
    toolset="file",
    schema=HASHLINE_READ_SCHEMA,
    handler=_handle_hashline_read,
    emoji="🔗",
    max_result_size_chars=100_000,
)
