"""
Tests for python3/chatgpt/tools.py

Tests the tool execution framework including all 17 tools, security validation,
and the tool execution dispatcher.
"""

import pytest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock, call
import subprocess

# Import the module under test
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3"))

from chatgpt.tools import get_tool_definitions, validate_file_path, execute_tool


class TestGetToolDefinitions:
    """Test get_tool_definitions() function"""

    def test_returns_list_of_tools(self):
        """Should return a list of tool definitions"""
        tools = get_tool_definitions()
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_all_tools_have_required_fields(self):
        """Each tool should have name, description, and parameters"""
        tools = get_tool_definitions()
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert isinstance(tool["name"], str)
            assert isinstance(tool["description"], str)
            assert isinstance(tool["parameters"], dict)

    def test_tool_count(self):
        """Should have exactly 17 tools defined"""
        tools = get_tool_definitions()
        assert len(tools) >= 17

    def test_tool_names(self):
        """Should include all expected tool names"""
        tools = get_tool_definitions()
        tool_names = [t["name"] for t in tools]

        expected_tools = [
            "get_working_directory",
            "list_directory",
            "find_in_file",
            "find_file_in_project",
            "read_file",
            "create_file",
            "open_file",
            "edit_file",
            "edit_file_lines",
            "git_status",
            "git_diff",
            "git_log",
            "git_show",
            "git_branch",
            "git_add",
            "git_reset",
            "git_commit",
        ]

        for expected in expected_tools:
            assert expected in tool_names

    def test_parameters_have_json_schema_structure(self):
        """Each tool's parameters should follow JSON schema format"""
        tools = get_tool_definitions()
        for tool in tools:
            params = tool["parameters"]
            assert "type" in params
            assert params["type"] == "object"
            assert "properties" in params
            assert "required" in params
            assert isinstance(params["properties"], dict)
            assert isinstance(params["required"], list)


class TestValidateFilePath:
    """Test validate_file_path() security function"""

    def test_path_within_project_allowed(self, tmp_path):
        """Paths within project directory should be allowed"""
        with patch("os.getcwd", return_value=str(tmp_path)):
            file_path = os.path.join(tmp_path, "test.txt")
            is_valid, error_msg = validate_file_path(file_path)
            assert is_valid is True
            assert error_msg is None

    def test_relative_path_within_project_allowed(self, tmp_path):
        """Relative paths within project should be allowed"""
        with patch("os.getcwd", return_value=str(tmp_path)):
            is_valid, error_msg = validate_file_path("./test.txt")
            assert is_valid is True
            assert error_msg is None

    @patch("chatgpt.tools.vim")
    def test_system_paths_blocked(self, mock_vim, tmp_path):
        """System paths should always be blocked"""
        # Mock vim.eval to prevent confirmation dialog issues
        mock_vim.eval.return_value = "2"  # User denies

        with patch("os.getcwd", return_value=str(tmp_path)):
            # Test paths that should be blocked - using real paths that exist on macOS
            # On macOS, /etc is a symlink to /private/etc, so we need to test the real path
            blocked_paths = [
                "/private/etc/passwd",  # Real path on macOS
                "/bin/bash",
                "/usr/bin/python",
                "/usr/sbin/sshd",
            ]

            for path in blocked_paths:
                is_valid, error_msg = validate_file_path(path)
                assert is_valid is False, f"Expected path {path} to be blocked"
                # The error could be either "Cannot modify system path" or "denied by user" depending on the check
                assert (
                    "denied" in error_msg.lower()
                ), f"Expected 'denied' in error message for {path}, got: {error_msg}"

    def test_path_traversal_blocked(self, tmp_path):
        """Path traversal attempts should be blocked"""
        with patch("os.getcwd", return_value=str(tmp_path)):
            is_valid, error_msg = validate_file_path("../../../etc/passwd")
            assert is_valid is False
            assert "Security" in error_msg
            assert ".." in error_msg

    @patch("chatgpt.tools.vim")
    def test_path_outside_project_requires_permission(self, mock_vim, tmp_path):
        """Paths outside project should prompt for user permission"""
        with patch("os.getcwd", return_value=str(tmp_path)):
            outside_path = "/tmp/outside.txt"

            # User approves
            mock_vim.eval.return_value = "1"
            is_valid, error_msg = validate_file_path(outside_path)
            assert is_valid is True
            assert error_msg is None
            assert mock_vim.eval.called

    @patch("chatgpt.tools.vim")
    def test_path_outside_project_user_denies(self, mock_vim, tmp_path):
        """User can deny operations outside project"""
        with patch("os.getcwd", return_value=str(tmp_path)):
            outside_path = "/tmp/outside.txt"

            # User denies
            mock_vim.eval.return_value = "2"
            is_valid, error_msg = validate_file_path(outside_path)
            assert is_valid is False
            assert "denied by user" in error_msg


class TestExecuteTool:
    """Test execute_tool() dispatcher and individual tool implementations"""

    @pytest.fixture(autouse=True)
    def disable_tool_approval(self):
        """Disable tool approval for all tests in this class"""
        with patch("chatgpt.tools.get_config") as mock_config:
            # Return "0" for require_tool_approval to disable approval
            def config_side_effect(key, default=None):
                if key == "require_tool_approval":
                    return "0"
                return default

            mock_config.side_effect = config_side_effect
            yield mock_config

    def test_get_working_directory(self):
        """get_working_directory should return current directory"""
        result = execute_tool("get_working_directory", {})
        assert "Current working directory:" in result
        assert os.getcwd() in result

    def test_list_directory(self, tmp_path):
        """list_directory should list files and directories"""
        # Create test structure
        (tmp_path / "dir1").mkdir()
        (tmp_path / "file1.txt").write_text("test")
        (tmp_path / ".hidden").write_text("hidden")

        with patch("os.getcwd", return_value=str(tmp_path)):
            # List without hidden files
            result = execute_tool(
                "list_directory", {"path": str(tmp_path), "show_hidden": False}
            )
            assert "dir1/" in result
            assert "file1.txt" in result
            assert ".hidden" not in result

            # List with hidden files
            result = execute_tool(
                "list_directory", {"path": str(tmp_path), "show_hidden": True}
            )
            assert ".hidden" in result

    def test_list_directory_not_found(self):
        """list_directory should handle non-existent directory"""
        result = execute_tool("list_directory", {"path": "/nonexistent/path"})
        assert "not found" in result.lower()

    def test_read_file(self, tmp_path):
        """read_file should read file contents"""
        test_file = tmp_path / "test.txt"
        test_content = "Line 1\nLine 2\nLine 3"
        test_file.write_text(test_content)

        result = execute_tool("read_file", {"file_path": str(test_file)})
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result

    def test_read_file_max_lines(self, tmp_path):
        """read_file should respect max_lines parameter"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("\n".join([f"Line {i}" for i in range(1, 101)]))

        result = execute_tool(
            "read_file", {"file_path": str(test_file), "max_lines": 10}
        )
        assert "Line 1" in result
        assert "Line 10" in result
        assert "truncated" in result

    def test_read_file_not_found(self):
        """read_file should handle non-existent file"""
        result = execute_tool("read_file", {"file_path": "/nonexistent/file.txt"})
        assert "not found" in result.lower()

    @patch("chatgpt.tools.validate_file_path")
    def test_create_file(self, mock_validate, tmp_path):
        """create_file should create new file with content"""
        mock_validate.return_value = (True, None)

        test_file = tmp_path / "new_file.txt"
        content = "Test content"

        result = execute_tool(
            "create_file", {"file_path": str(test_file), "content": content}
        )

        assert "Successfully created" in result
        assert test_file.exists()
        assert test_file.read_text() == content

    @patch("chatgpt.tools.validate_file_path")
    def test_create_file_overwrite(self, mock_validate, tmp_path):
        """create_file with overwrite=true should replace existing file"""
        mock_validate.return_value = (True, None)

        test_file = tmp_path / "existing.txt"
        test_file.write_text("Old content")

        new_content = "New content"
        result = execute_tool(
            "create_file",
            {"file_path": str(test_file), "content": new_content, "overwrite": True},
        )

        assert "Successfully created" in result
        assert test_file.read_text() == new_content

    @patch("chatgpt.tools.validate_file_path")
    def test_create_file_no_overwrite(self, mock_validate, tmp_path):
        """create_file should not overwrite without overwrite=true"""
        mock_validate.return_value = (True, None)

        test_file = tmp_path / "existing.txt"
        test_file.write_text("Old content")

        result = execute_tool(
            "create_file",
            {"file_path": str(test_file), "content": "New content", "overwrite": False},
        )

        assert "already exists" in result
        assert test_file.read_text() == "Old content"

    @patch("chatgpt.tools.validate_file_path")
    def test_create_file_creates_directory(self, mock_validate, tmp_path):
        """create_file should create parent directories"""
        mock_validate.return_value = (True, None)

        test_file = tmp_path / "new_dir" / "new_file.txt"

        result = execute_tool(
            "create_file", {"file_path": str(test_file), "content": "Test"}
        )

        assert "Successfully created" in result
        assert test_file.exists()

    @patch("chatgpt.tools.vim.command")
    @patch("chatgpt.tools.vim")
    def test_open_file(self, mock_vim, mock_command, tmp_path):
        """open_file should open file in Vim"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Mock Vim responses
        mock_vim.eval.side_effect = ["-1", "gpt-persistent-session", ""]

        result = execute_tool("open_file", {"file_path": str(test_file)})

        assert "Opened file" in result
        assert mock_command.called

    @patch("chatgpt.tools.vim.command")
    @patch("chatgpt.tools.vim")
    def test_open_file_with_line_number(self, mock_vim, mock_command, tmp_path):
        """open_file should jump to specified line number"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3")

        mock_vim.eval.side_effect = ["-1", "gpt-persistent-session", ""]

        result = execute_tool(
            "open_file", {"file_path": str(test_file), "line_number": 2}
        )

        assert "line 2" in result
        # Check that cursor command was called
        cursor_calls = [c for c in mock_command.call_args_list if "cursor" in str(c)]
        assert len(cursor_calls) > 0

    @patch("chatgpt.tools.validate_file_path")
    def test_edit_file(self, mock_validate, tmp_path):
        """edit_file should replace content"""
        mock_validate.return_value = (True, None)

        test_file = tmp_path / "test.txt"
        original = "Hello world\nGoodbye world"
        test_file.write_text(original)

        result = execute_tool(
            "edit_file",
            {
                "file_path": str(test_file),
                "old_content": "Goodbye",
                "new_content": "Hello again",
            },
        )

        assert "Successfully edited" in result
        assert "Hello again" in test_file.read_text()
        assert "Goodbye" not in test_file.read_text()

    @patch("chatgpt.tools.validate_file_path")
    def test_edit_file_content_not_found(self, mock_validate, tmp_path):
        """edit_file should fail if content not found"""
        mock_validate.return_value = (True, None)

        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world")

        result = execute_tool(
            "edit_file",
            {
                "file_path": str(test_file),
                "old_content": "Nonexistent",
                "new_content": "New",
            },
        )

        assert "not found" in result

    @patch("chatgpt.tools.validate_file_path")
    def test_edit_file_multiple_occurrences(self, mock_validate, tmp_path):
        """edit_file should fail if content appears multiple times"""
        mock_validate.return_value = (True, None)

        test_file = tmp_path / "test.txt"
        test_file.write_text("hello\nhello\nhello")

        result = execute_tool(
            "edit_file",
            {
                "file_path": str(test_file),
                "old_content": "hello",
                "new_content": "goodbye",
            },
        )

        assert "occurrences" in result.lower()

    @patch("chatgpt.tools.validate_file_path")
    def test_edit_file_lines(self, mock_validate, tmp_path):
        """edit_file_lines should replace line range"""
        mock_validate.return_value = (True, None)

        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\n")

        result = execute_tool(
            "edit_file_lines",
            {
                "file_path": str(test_file),
                "start_line": 2,
                "end_line": 3,
                "new_content": "New Line 2\nNew Line 3",
            },
        )

        assert "Successfully edited" in result
        content = test_file.read_text()
        assert "Line 1" in content
        assert "New Line 2" in content
        assert "New Line 3" in content
        assert "Line 4" in content

    @patch("chatgpt.tools.validate_file_path")
    def test_edit_file_lines_single_line(self, mock_validate, tmp_path):
        """edit_file_lines should handle single line replacement"""
        mock_validate.return_value = (True, None)

        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        result = execute_tool(
            "edit_file_lines",
            {
                "file_path": str(test_file),
                "start_line": 2,
                "end_line": 2,
                "new_content": "Replaced Line 2",
            },
        )

        assert "Successfully edited" in result
        content = test_file.read_text()
        assert "Replaced Line 2" in content

    @patch("chatgpt.tools.validate_file_path")
    def test_edit_file_lines_invalid_range(self, mock_validate, tmp_path):
        """edit_file_lines should validate line numbers"""
        mock_validate.return_value = (True, None)

        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\n")

        # start_line > end_line
        result = execute_tool(
            "edit_file_lines",
            {
                "file_path": str(test_file),
                "start_line": 3,
                "end_line": 2,
                "new_content": "New",
            },
        )
        assert "Invalid" in result

    @patch("subprocess.run")
    def test_find_in_file(self, mock_run, tmp_path):
        """find_in_file should search for pattern in file"""
        mock_run.return_value = Mock(
            returncode=0, stdout="10:found line\n20:another match\n", stderr=""
        )

        result = execute_tool(
            "find_in_file", {"file_path": "/tmp/test.txt", "pattern": "search"}
        )

        assert "found line" in result
        assert mock_run.called

    @patch("subprocess.run")
    def test_find_in_file_no_matches(self, mock_run):
        """find_in_file should handle no matches"""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="")

        result = execute_tool(
            "find_in_file", {"file_path": "/tmp/test.txt", "pattern": "notfound"}
        )

        assert "No matches" in result

    @patch("subprocess.run")
    def test_find_file_in_project(self, mock_run):
        """find_file_in_project should find files by pattern"""
        mock_run.return_value = Mock(
            returncode=0, stdout="./file1.py\n./dir/file2.py\n", stderr=""
        )

        result = execute_tool("find_file_in_project", {"pattern": "*.py"})

        assert "file1.py" in result
        assert "file2.py" in result

    @patch("subprocess.run")
    def test_git_status(self, mock_run):
        """git_status should return status and recent commits"""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="On branch main\nnothing to commit", stderr=""),
            Mock(returncode=0, stdout="abc123 Latest commit\n", stderr=""),
        ]

        result = execute_tool("git_status", {})

        assert "Git Status" in result
        assert "On branch main" in result

    @patch("subprocess.run")
    def test_git_diff_unstaged(self, mock_run):
        """git_diff should show unstaged changes"""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="M file.txt", stderr=""),
            Mock(returncode=0, stdout="diff --git a/file.txt...", stderr=""),
        ]

        result = execute_tool("git_diff", {"staged": False})

        assert "Unstaged Changes" in result

    @patch("subprocess.run")
    def test_git_diff_staged(self, mock_run):
        """git_diff with staged=true should show staged changes"""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="M file.txt", stderr=""),
            Mock(returncode=0, stdout="diff --git a/file.txt...", stderr=""),
        ]

        result = execute_tool("git_diff", {"staged": True})

        assert "Staged Changes" in result

    @patch("subprocess.run")
    def test_git_log(self, mock_run):
        """git_log should show commit history"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="abc123 First commit\ndef456 Second commit\n",
            stderr="",
        )

        result = execute_tool("git_log", {"max_count": 2})

        assert "abc123" in result
        assert "First commit" in result

    @patch("subprocess.run")
    def test_git_show(self, mock_run):
        """git_show should show commit details"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="commit abc123\nAuthor: Test\n\ndiff --git...",
            stderr="",
        )

        result = execute_tool("git_show", {"commit": "HEAD"})

        assert "commit abc123" in result

    @patch("subprocess.run")
    def test_git_branch(self, mock_run):
        """git_branch should show current branch"""
        mock_run.return_value = Mock(returncode=0, stdout="main", stderr="")

        result = execute_tool("git_branch", {"list_all": False})

        assert "main" in result

    @patch("subprocess.run")
    def test_git_add(self, mock_run):
        """git_add should stage files"""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=0, stdout="M file.txt", stderr=""),
        ]

        result = execute_tool("git_add", {"files": ["file.txt"]})

        assert "Successfully staged" in result

    @patch("subprocess.run")
    def test_git_reset(self, mock_run):
        """git_reset should unstage files"""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        result = execute_tool("git_reset", {"files": ["file.txt"]})

        assert "Successfully unstaged" in result

    @patch("subprocess.run")
    def test_git_commit(self, mock_run):
        """git_commit should create commit"""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="On branch main", stderr=""),
            Mock(returncode=0, stdout="diff content", stderr=""),
            Mock(returncode=0, stdout="abc123 Recent commit", stderr=""),
            Mock(returncode=0, stdout="[main abc123] Test commit", stderr=""),
        ]

        result = execute_tool("git_commit", {"message": "Test commit"})

        assert "Commit successful" in result

    @patch("subprocess.run")
    def test_git_commit_no_changes(self, mock_run):
        """git_commit should handle no staged changes"""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="On branch main", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=1, stdout="", stderr="nothing to commit"),
        ]

        result = execute_tool("git_commit", {"message": "Test"})

        assert "No changes staged" in result

    def test_unknown_tool(self):
        """execute_tool should handle unknown tool names"""
        result = execute_tool("nonexistent_tool", {})
        assert "Unknown tool" in result

    @patch("subprocess.run")
    def test_tool_timeout(self, mock_run):
        """execute_tool should handle subprocess timeouts"""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 5)

        result = execute_tool("find_file_in_project", {"pattern": "*.py"})

        assert "timed out" in result.lower()
