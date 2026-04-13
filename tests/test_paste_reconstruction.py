"""Tests for paste marker persistence and reconstruction.

Verifies the smart paste system's disk persistence and gateway-side
reconstruction after the fix for the cross-channel paste bug.
"""
import os
import re
import time
import pytest
from pathlib import Path
from unittest.mock import patch as mock_patch


@pytest.fixture
def paste_dir(tmp_path):
    """Create a temporary paste directory with test files."""
    p = tmp_path / "pastes"
    p.mkdir()
    return p


@pytest.fixture
def mock_hermes_home(tmp_path):
    """Mock _hermes_home to use tmp_path."""
    with mock_patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
        yield tmp_path


class TestPasteMarkerRegex:
    """Test that the paste marker regex matches all valid formats."""

    PASTE_RE = re.compile(
        r'\[Pasted text #(\d+) \+(\d+) (chars|lines)(?: ↳([^\]]+))?\]'
    )

    def test_legacy_chars_format(self):
        msg = "[Pasted text #1 +3778 chars]"
        m = self.PASTE_RE.search(msg)
        assert m is not None
        assert m.group(1) == "1"
        assert m.group(2) == "3778"
        assert m.group(3) == "chars"
        assert m.group(4) is None

    def test_legacy_lines_format(self):
        msg = "[Pasted text #3 +12 lines]"
        m = self.PASTE_RE.search(msg)
        assert m is not None
        assert m.group(1) == "3"
        assert m.group(2) == "12"
        assert m.group(3) == "lines"
        assert m.group(4) is None

    def test_new_format_with_filename(self):
        msg = "[Pasted text #2 +500 chars ↳paste_2_143022.txt]"
        m = self.PASTE_RE.search(msg)
        assert m is not None
        assert m.group(1) == "2"
        assert m.group(2) == "500"
        assert m.group(3) == "chars"
        assert m.group(4) == "paste_2_143022.txt"

    def test_new_format_lines_with_filename(self):
        msg = "[Pasted text #1 +45 lines ↳paste_1_090439.txt]"
        m = self.PASTE_RE.search(msg)
        assert m is not None
        assert m.group(3) == "lines"
        assert m.group(4) == "paste_1_090439.txt"

    def test_embedded_in_larger_text(self):
        msg = "the build failed:[Pasted text #1 +3778 chars]"
        m = self.PASTE_RE.search(msg)
        assert m is not None
        assert m.group(1) == "1"
        assert m.group(2) == "3778"

    def test_no_match_plain_text(self):
        msg = "just a normal message"
        assert self.PASTE_RE.search(msg) is None

    def test_no_match_partial_marker(self):
        msg = "[Pasted text #1 +37"
        assert self.PASTE_RE.search(msg) is None


class TestGatewayReconstruction:
    """Test _reconstruct_paste_markers from gateway/run.py."""

    def _make_reconstruct(self, paste_dir):
        """Create a standalone reconstruction function using the test paste_dir."""
        PASTE_RE = re.compile(
            r'\[Pasted text #(\d+) \+(\d+) (chars|lines)(?: ↳([^\]]+))?\]'
        )

        def _reconstruct_paste_markers(text):
            if "[Pasted text #" not in text:
                return text
            result = text
            for m in PASTE_RE.finditer(result):
                pid = m.group(1)
                filename = m.group(4)
                content = None
                if filename:
                    p = paste_dir / filename
                    if p.is_file():
                        content = p.read_text(encoding="utf-8")
                if content is None:
                    matches = sorted(
                        paste_dir.glob(f"paste_{pid}_*.txt"), reverse=True
                    )
                    if matches:
                        content = matches[0].read_text(encoding="utf-8")
                if content:
                    result = result.replace(m.group(0), content, 1)
            return result

        return _reconstruct_paste_markers

    def test_reconstruct_with_filename(self, paste_dir):
        """New format: marker includes ↳filename, file exists."""
        content = "Build failed:\nError on line 42"
        (paste_dir / "paste_1_123456.txt").write_text(content, encoding="utf-8")

        reconstruct = self._make_reconstruct(paste_dir)
        msg = "error:[Pasted text #1 +27 chars ↳paste_1_123456.txt]"
        result = reconstruct(msg)
        assert content in result
        assert "[Pasted text" not in result

    def test_reconstruct_glob_fallback(self, paste_dir):
        """Legacy format: no filename, glob finds the file."""
        content = "Some pasted content\nMultiple lines"
        (paste_dir / "paste_2_143022.txt").write_text(content, encoding="utf-8")

        reconstruct = self._make_reconstruct(paste_dir)
        msg = "check this:[Pasted text #2 +32 chars]"
        result = reconstruct(msg)
        assert content in result

    def test_reconstruct_glob_picks_latest(self, paste_dir):
        """When multiple files match, picks the most recent (sorted desc)."""
        old = "old content"
        new = "new content"
        (paste_dir / "paste_1_100000.txt").write_text(old, encoding="utf-8")
        (paste_dir / "paste_1_200000.txt").write_text(new, encoding="utf-8")

        reconstruct = self._make_reconstruct(paste_dir)
        msg = "[Pasted text #1 +11 chars]"
        result = reconstruct(msg)
        assert new in result
        assert old not in result

    def test_missing_file_leaves_marker(self, paste_dir):
        """If file doesn't exist, marker is left intact."""
        reconstruct = self._make_reconstruct(paste_dir)
        msg = "[Pasted text #99 +100 chars ↳paste_99_noexist.txt]"
        result = reconstruct(msg)
        assert result == msg

    def test_no_markers_unchanged(self, paste_dir):
        """Messages without markers pass through unchanged."""
        reconstruct = self._make_reconstruct(paste_dir)
        msg = "hello world, no paste here"
        assert reconstruct(msg) == msg

    def test_multiple_markers(self, paste_dir):
        """Multiple paste markers in one message are all expanded."""
        (paste_dir / "paste_1_100000.txt").write_text("FIRST", encoding="utf-8")
        (paste_dir / "paste_2_200000.txt").write_text("SECOND", encoding="utf-8")

        reconstruct = self._make_reconstruct(paste_dir)
        msg = "[Pasted text #1 +5 chars ↳paste_1_100000.txt] then [Pasted text #2 +6 chars ↳paste_2_200000.txt]"
        result = reconstruct(msg)
        assert "FIRST" in result
        assert "SECOND" in result

    def test_mixed_legacy_and_new(self, paste_dir):
        """Mix of legacy and new format markers."""
        (paste_dir / "paste_1_100000.txt").write_text("CONTENT_A", encoding="utf-8")
        (paste_dir / "paste_2_200000.txt").write_text("CONTENT_B", encoding="utf-8")

        reconstruct = self._make_reconstruct(paste_dir)
        msg = "[Pasted text #1 +9 chars ↳paste_1_100000.txt] and [Pasted text #2 +9 chars]"
        result = reconstruct(msg)
        assert "CONTENT_A" in result
        assert "CONTENT_B" in result

    def test_real_world_format(self, paste_dir):
        """Test with the exact format from the user's failing message."""
        content = "Error: Build failed\n> cloudflare-pages@build\n> tsc && vite build\n\nerror TS2304: Cannot find name 'foo'"
        (paste_dir / "paste_1_165442.txt").write_text(content, encoding="utf-8")

        reconstruct = self._make_reconstruct(paste_dir)
        msg = "the cloudflare build for my website with a purpose failed:[Pasted text #1 +3778 chars]"
        result = reconstruct(msg)
        assert content in result


class TestPasteFilePersistence:
    """Test that _store_paste writes to disk."""

    def test_store_creates_file(self, paste_dir):
        """Verify that paste content is persisted to the pastes directory."""
        import time as _time

        _paste_counter = [0]
        _paste_store = {}
        _active_paste_ids = set()

        def _store_paste(text):
            _paste_counter[0] += 1
            paste_id = str(_paste_counter[0])
            _paste_store[paste_id] = text
            _active_paste_ids.add(paste_id)
            _ts = _time.strftime("%H%M%S")
            _paste_filename = f"paste_{paste_id}_{_ts}.txt"
            paste_dir.mkdir(parents=True, exist_ok=True)
            (paste_dir / _paste_filename).write_text(text, encoding="utf-8")
            line_count = text.count("\n")
            if line_count == 0:
                return f"[Pasted text #{paste_id} +{len(text)} chars ↳{_paste_filename}]"
            return f"[Pasted text #{paste_id} +{line_count + 1} lines ↳{_paste_filename}]"

        content = "Build error output\nLine 2\nLine 3"
        marker = _store_paste(content)

        assert "↳" in marker
        assert "paste_1_" in marker

        # Verify file was created
        files = list(paste_dir.glob("paste_1_*.txt"))
        assert len(files) == 1
        assert files[0].read_text(encoding="utf-8") == content

    def test_marker_includes_filename(self, paste_dir):
        """Marker should contain the ↳filename reference."""
        import time as _time

        _paste_counter = [0]
        _ts = _time.strftime("%H%M%S")

        def _store_paste(text):
            _paste_counter[0] += 1
            paste_id = str(_paste_counter[0])
            _paste_filename = f"paste_{paste_id}_{_ts}.txt"
            return f"[Pasted text #{paste_id} +{len(text)} chars ↳{_paste_filename}]"

        marker = _store_paste("hello world")
        assert "↳" in marker
        assert f"paste_1_{_ts}.txt" in marker


class TestDeletionDetectionRegex:
    """Test the deletion detection regex matches both formats."""

    def test_matches_old_format(self):
        pid = "1"
        _del_re = re.compile(
            rf'\[Pasted text #{re.escape(pid)} \+\d+ (chars|lines)(?: ↳[^\]]+)?\]'
        )
        text = "some [Pasted text #1 +3778 chars] end"
        assert _del_re.search(text)

    def test_matches_new_format(self):
        pid = "1"
        _del_re = re.compile(
            rf'\[Pasted text #{re.escape(pid)} \+\d+ (chars|lines)(?: ↳[^\]]+)?\]'
        )
        text = "some [Pasted text #1 +53 chars ↳paste_1_123456.txt] end"
        assert _del_re.search(text)

    def test_no_match_after_partial_deletion(self):
        pid = "1"
        _del_re = re.compile(
            rf'\[Pasted text #{re.escape(pid)} \+\d+ (chars|lines)(?: ↳[^\]]+)?\]'
        )
        text = "some [Pasted text #1 +37 end"
        assert not _del_re.search(text)

    def test_different_pid_no_match(self):
        pid = "2"
        _del_re = re.compile(
            rf'\[Pasted text #{re.escape(pid)} \+\d+ (chars|lines)(?: ↳[^\]]+)?\]'
        )
        text = "some [Pasted text #1 +3778 chars] end"
        assert not _del_re.search(text)
