"""
Tests for python3/chatgpt/utils.py

Tests utility functions including logging, formatting, and history management.
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, MagicMock, patch, mock_open
from datetime import datetime

# Import the module under test
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3"))

from chatgpt.utils import (
    debug_log,
    save_to_history,
    save_plan,
    load_plan,
    get_config,
    get_project_dir,
    format_box,
    format_separator,
    format_tool_call,
    format_tool_result,
    format_plan_display,
)


class TestDebugLog:
    """Tests for debug_log function"""

    @patch("chatgpt.utils.vim")
    def test_debug_log_disabled(self, mock_vim):
        """Test that debug_log does nothing when logging is disabled"""
        mock_vim.eval.return_value = "0"

        with patch("builtins.open", mock_open()) as mock_file:
            debug_log("Test message")
            mock_file.assert_not_called()

    @patch("chatgpt.utils.vim")
    @patch("chatgpt.utils.get_config")
    def test_debug_log_enabled(self, mock_get_config, mock_vim):
        """Test that debug_log writes when enabled"""
        import tempfile
        import os

        mock_vim.eval.return_value = "2"  # Set log level to 2
        mock_get_config.return_value = "2"  # Log level 2

        # Mock get_project_dir to raise an exception, forcing fallback to temp
        with patch(
            "chatgpt.utils.get_project_dir", side_effect=Exception("No project dir")
        ):
            with patch("builtins.open", mock_open()) as mock_file:
                debug_log("WARNING: Test message")

                # Check that open was called with the temp log file
                expected_path = os.path.join(
                    tempfile.gettempdir(), "vim-llm-agent-debug.log"
                )
                mock_file.assert_called_once_with(
                    expected_path, "a", encoding="utf-8"
                )
                # Get the file handle from the context manager
                handle = mock_file()
                # Verify write was called
                handle.write.assert_called()
                # Check the content
                written_content = "".join(
                    call.args[0] for call in handle.write.call_args_list
                )
                assert "WARNING" in written_content
                assert "Test message" in written_content

    @patch("chatgpt.utils.vim")
    def test_debug_log_with_exception(self, mock_vim):
        """Test that debug_log handles exceptions gracefully"""
        mock_vim.eval.side_effect = Exception("Vim error")

        # Should not raise exception
        debug_log("Test message")


class TestSaveToHistory:
    """Tests for save_to_history function"""

    @patch("chatgpt.utils.vim")
    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("os.getcwd")
    @patch("builtins.open", new_callable=mock_open)
    def test_save_to_history_enabled(
        self, mock_file, mock_getcwd, mock_makedirs, mock_exists, mock_vim
    ):
        """Test saving to history when enabled"""
        mock_vim.eval.return_value = "1"
        mock_getcwd.return_value = "/test/dir"
        mock_exists.return_value = True  # Directory exists

        save_to_history("Test content")

        mock_file.assert_called_once()

    @patch("chatgpt.utils.vim")
    def test_save_to_history_disabled(self, mock_vim):
        """Test save_to_history does nothing when disabled"""
        mock_vim.eval.return_value = "0"

        with patch("builtins.open", mock_open()) as mock_file:
            save_to_history("Test content")
            mock_file.assert_not_called()


class TestFormatBox:
    """Tests for format_box function"""

    def test_format_box_with_title_only(self):
        """Test formatting box with title only"""
        result = format_box("Test Title", width=40)
        assert "Test Title" in result
        assert "╔" in result
        assert "╚" in result

    def test_format_box_with_title_and_content(self):
        """Test formatting box with title and content"""
        result = format_box("Title", "Content here", width=40)
        assert "Title" in result
        assert "Content here" in result

    def test_format_box_multiline_content(self):
        """Test formatting box with multiline content"""
        result = format_box("Title", "Line 1\nLine 2\nLine 3")
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result


class TestFormatSeparator:
    """Tests for format_separator function"""

    def test_format_separator_default(self):
        """Test default separator"""
        result = format_separator()
        assert len(result) == 60
        assert all(c == "─" for c in result)

    def test_format_separator_custom_char(self):
        """Test custom separator character"""
        result = format_separator(char="=", width=30)
        assert len(result) == 30
        assert all(c == "=" for c in result)


class TestFormatToolCall:
    """Tests for format_tool_call function"""

    def test_format_tool_call_executing(self):
        """Test formatting executing tool call"""
        result = format_tool_call("test_tool", {"arg1": "value1"}, status="executing")
        assert "test_tool" in result
        assert "arg1" in result

    def test_format_tool_call_success(self):
        """Test formatting successful tool call"""
        result = format_tool_call("test_tool", {"arg1": "value1"}, status="success")
        assert "Success" in result
        assert "test_tool" in result

    def test_format_tool_call_error(self):
        """Test formatting error tool call"""
        result = format_tool_call("test_tool", {"arg1": "value1"}, status="error")
        assert "Error" in result
        assert "test_tool" in result

    def test_format_tool_call_long_args(self):
        """Test formatting tool call with long arguments"""
        long_value = "x" * 100
        result = format_tool_call("test_tool", {"arg1": long_value})
        # Should be truncated
        assert len(result) < 200


class TestFormatToolResult:
    """Tests for format_tool_result function"""

    def test_format_tool_result_basic(self):
        """Test basic tool result formatting"""
        result = format_tool_result("test_tool", {"arg1": "val1"}, "Output text")
        assert "test_tool" in result
        assert "Output text" in result
        assert "─" in result

    def test_format_tool_result_multiline(self):
        """Test tool result with multiple lines"""
        output = "\n".join([f"Line {i}" for i in range(5)])
        result = format_tool_result("test_tool", {}, output, max_lines=10)
        assert "Line 0" in result
        assert "Line 4" in result

    def test_format_tool_result_truncation(self):
        """Test tool result truncation"""
        output = "\n".join([f"Line {i}" for i in range(100)])
        result = format_tool_result("test_tool", {}, output, max_lines=5)
        assert "truncated" in result


class TestFormatPlanDisplay:
    """Tests for format_plan_display function"""

    def test_format_plan_display_basic(self):
        """Test basic plan formatting"""
        tool_calls = [
            {"name": "tool1", "arguments": {"arg1": "val1"}},
            {"name": "tool2", "arguments": {"arg2": "val2"}},
        ]
        result = format_plan_display("PLAN", "Test explanation", tool_calls)
        assert "PLAN FOR APPROVAL" in result
        assert "Test explanation" in result
        assert "tool1" in result
        assert "tool2" in result

    def test_format_plan_display_no_explanation(self):
        """Test plan formatting without explanation"""
        tool_calls = [{"name": "tool1", "arguments": {}}]
        result = format_plan_display("PLAN", "", tool_calls)
        assert "PLAN FOR APPROVAL" in result
        assert "tool1" in result

    def test_format_plan_display_multiple_tools(self):
        """Test plan with multiple tools"""
        tool_calls = [
            {"name": f"tool{i}", "arguments": {"arg": f"val{i}"}} for i in range(5)
        ]
        result = format_plan_display("REVISED PLAN", "Updating approach", tool_calls)
        assert "REVISED PLAN" in result
        assert "tool0" in result
        assert "tool4" in result


class TestSavePlan:
    """Tests for save_plan function"""

    @patch("chatgpt.utils.vim")
    @patch("chatgpt.utils.debug_log")
    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("os.getcwd")
    @patch("builtins.open", new_callable=mock_open)
    def test_saves_plan_to_file(
        self, mock_file, mock_getcwd, mock_makedirs, mock_exists, mock_debug_log, mock_vim
    ):
        """Test that save_plan writes plan to plan.md in project directory"""
        mock_vim.eval.return_value = "1"  # Session mode enabled
        mock_getcwd.return_value = "/test/project"
        # get_project_dir will check for directories, return True so it uses .vim-llm-agent
        mock_exists.return_value = True

        plan_content = """GOAL: Test the feature

PLAN:
1. Step one
2. Step two"""

        save_plan(plan_content)

        # Verify file was opened for writing - using new directory name
        mock_file.assert_called_once_with(
            "/test/project/.vim-llm-agent/plan.md", "w", encoding="utf-8"
        )

        # Verify content was written with metadata
        handle = mock_file()
        written_content = "".join(call.args[0] for call in handle.write.call_args_list)
        assert "Plan saved at:" in written_content
        assert "GOAL: Test the feature" in written_content
        assert "Step one" in written_content

    @patch("chatgpt.utils.debug_log")
    @patch("chatgpt.utils.vim")
    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("os.getcwd")
    def test_creates_directory_if_not_exists(
        self, mock_getcwd, mock_makedirs, mock_exists, mock_vim, mock_debug_log
    ):
        """Test that save_plan creates project directory if needed"""
        mock_vim.eval.return_value = "1"  # Session mode enabled
        mock_getcwd.return_value = "/test/project"
        # get_project_dir will check for both directories, both don't exist
        mock_exists.return_value = False

        with patch("builtins.open", mock_open()):
            save_plan("Test plan")

        # Verify directory was created - using new directory name
        mock_makedirs.assert_called_once_with("/test/project/.vim-llm-agent")

    @patch("chatgpt.utils.vim")
    def test_skips_when_session_disabled(self, mock_vim):
        """Test that save_plan does nothing when session mode is disabled"""
        mock_vim.eval.return_value = "0"  # Session mode disabled

        with patch("builtins.open", mock_open()) as mock_file:
            save_plan("Test plan")

        # Verify file was not opened
        mock_file.assert_not_called()

    @patch("chatgpt.utils.vim")
    @patch("os.getcwd")
    @patch("builtins.open", side_effect=OSError("Write error"))
    def test_handles_write_errors_gracefully(self, mock_file, mock_getcwd, mock_vim):
        """Test that save_plan handles write errors without crashing"""
        mock_vim.eval.return_value = "1"
        mock_getcwd.return_value = "/test/project"

        with patch("os.path.exists", return_value=True):
            # Should not raise exception
            save_plan("Test plan")


class TestLoadPlan:
    """Tests for load_plan function"""

    @patch("os.getcwd")
    @patch("os.path.exists")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="""<!-- Plan saved at: 2024-01-01 12:00:00 -->

GOAL: Test the feature

PLAN:
1. Step one
2. Step two""",
    )
    def test_loads_plan_from_file(self, mock_file, mock_exists, mock_getcwd):
        """Test that load_plan reads and parses plan.md"""
        mock_getcwd.return_value = "/test/project"
        # When neither directory exists, get_project_dir() returns .vim-llm-agent
        mock_exists.return_value = True

        result = load_plan()

        # Verify file was opened for reading - using new directory name
        mock_file.assert_called_once_with(
            "/test/project/.vim-llm-agent/plan.md", "r", encoding="utf-8"
        )

        # Verify metadata was stripped
        assert "Plan saved at:" not in result
        assert "GOAL: Test the feature" in result
        assert "Step one" in result

    @patch("os.getcwd")
    @patch("os.path.exists")
    def test_returns_none_when_file_not_exists(self, mock_exists, mock_getcwd):
        """Test that load_plan returns None when plan.md doesn't exist"""
        mock_getcwd.return_value = "/test/project"
        # get_project_dir checks for .vim-llm-agent and .vim-chatgpt directories
        # os.path.exists will be called multiple times, return False for all
        mock_exists.return_value = False

        result = load_plan()

        assert result is None

    @patch("os.getcwd")
    @patch("os.path.exists")
    @patch("builtins.open", side_effect=OSError("Read error"))
    def test_handles_read_errors_gracefully(self, mock_file, mock_exists, mock_getcwd):
        """Test that load_plan handles read errors without crashing"""
        mock_getcwd.return_value = "/test/project"
        # get_project_dir will check directories, plan file exists but can't be read
        mock_exists.return_value = True

        result = load_plan()

        # Should return None on error
        assert result is None


class TestGetConfig:
    """Tests for get_config function (backwards compatibility)"""

    @patch("chatgpt.utils.vim")
    def test_uses_new_config_when_available(self, mock_vim):
        """Test that new config variable takes precedence"""
        from tests.conftest import VimError

        # Setup: both old and new exist
        def eval_side_effect(expr):
            if "g:llm_agent_model" in expr:
                return "claude-3-5-sonnet"
            elif "g:chat_gpt_model" in expr:
                return "gpt-4"
            return ""

        mock_vim.eval.side_effect = eval_side_effect
        mock_vim.error = VimError

        result = get_config("model")

        # Should use new value
        assert result == "claude-3-5-sonnet"

    @patch("chatgpt.utils.vim")
    def test_falls_back_to_old_config(self, mock_vim):
        """Test fallback to old config variable"""
        from tests.conftest import VimError

        # Setup: only old exists
        def eval_side_effect(expr):
            if "g:llm_agent_model" in expr:
                return ""
            elif "g:chat_gpt_model" in expr:
                return "gpt-4"
            return ""

        mock_vim.eval.side_effect = eval_side_effect
        mock_vim.error = VimError

        result = get_config("model")

        # Should use old value
        assert result == "gpt-4"

    @patch("chatgpt.utils.vim")
    def test_returns_default_when_neither_exists(self, mock_vim):
        """Test default value when neither config exists"""
        from tests.conftest import VimError

        mock_vim.eval.return_value = ""
        mock_vim.error = VimError

        result = get_config("model", "default-model")

        # Should use default
        assert result == "default-model"

    @patch("chatgpt.utils.vim")
    def test_returns_none_when_no_default(self, mock_vim):
        """Test None return when neither exists and no default"""
        from tests.conftest import VimError

        mock_vim.eval.return_value = ""
        mock_vim.error = VimError

        result = get_config("model")

        # Should return None
        assert result is None


class TestGetProjectDir:
    """Tests for get_project_dir function (backwards compatibility)"""

    @patch("os.getcwd")
    @patch("os.path.exists")
    def test_uses_new_directory_when_exists(self, mock_exists, mock_getcwd):
        """Test that new directory is used when it exists"""
        mock_getcwd.return_value = "/test/project"

        # Both directories exist
        def exists_side_effect(path):
            if ".vim-llm-agent" in path:
                return True
            elif ".vim-chatgpt" in path:
                return True
            return False

        mock_exists.side_effect = exists_side_effect

        result = get_project_dir()

        # Should use new directory
        assert result == "/test/project/.vim-llm-agent"

    @patch("os.getcwd")
    @patch("os.path.exists")
    def test_falls_back_to_old_directory(self, mock_exists, mock_getcwd):
        """Test fallback to old directory when new doesn't exist"""
        mock_getcwd.return_value = "/test/project"

        # Only old directory exists
        def exists_side_effect(path):
            if ".vim-llm-agent" in path:
                return False
            elif ".vim-chatgpt" in path:
                return True
            return False

        mock_exists.side_effect = exists_side_effect

        result = get_project_dir()

        # Should use old directory for backwards compatibility
        assert result == "/test/project/.vim-chatgpt"

    @patch("os.getcwd")
    @patch("os.path.exists")
    def test_returns_new_when_neither_exists(self, mock_exists, mock_getcwd):
        """Test that new directory name is returned when neither exists"""
        mock_getcwd.return_value = "/test/project"
        mock_exists.return_value = False

        result = get_project_dir()

        # Should return new directory name (will be created)
        assert result == "/test/project/.vim-llm-agent"


class TestAnthropicFormatProviders:
    """Tests for uses_anthropic_format / append_tool_results routing"""

    def test_uses_anthropic_format(self):
        from chatgpt.utils import uses_anthropic_format

        assert uses_anthropic_format("anthropic")
        assert uses_anthropic_format("bedrock")
        assert not uses_anthropic_format("openai")
        assert not uses_anthropic_format("gemini")

    def test_append_tool_results_bedrock(self):
        from chatgpt.utils import append_tool_results

        messages = {"system": "s", "messages": [{"role": "user", "content": "hi"}]}
        append_tool_results(
            messages,
            "bedrock",
            "Reading",
            [{"id": "t1", "name": "read_file", "arguments": {"path": "a"}}],
            [("t1", "read_file", {"path": "a"}, "contents")],
        )
        assert messages["messages"][1] == {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Reading"},
                {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "a"}},
            ],
        }
        assert messages["messages"][2] == {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "contents"}],
        }


class TestGetConfigLegacy:
    """Tests for get_config's deprecated unprefixed-name fallback"""

    @pytest.fixture(autouse=True)
    def reset_warnings(self):
        import chatgpt.utils as utils

        utils._warned_deprecated.clear()
        yield
        utils._warned_deprecated.clear()

    @staticmethod
    def _eval_for(values):
        def eval_side_effect(expr):
            for var, val in values.items():
                if f'exists("{var}")' in expr:
                    return val
            return ""

        return eval_side_effect

    @patch("chatgpt.utils.vim")
    def test_new_name_wins_over_legacy(self, mock_vim):
        from tests.conftest import VimError

        mock_vim.error = VimError
        mock_vim.eval.side_effect = self._eval_for(
            {"g:llm_agent_anthropic_model": "new", "g:anthropic_model": "old"}
        )
        assert get_config("anthropic_model", legacy="g:anthropic_model") == "new"
        mock_vim.command.assert_not_called()

    @patch("chatgpt.utils.vim")
    def test_legacy_fallback_warns_once(self, mock_vim):
        from tests.conftest import VimError

        mock_vim.error = VimError
        mock_vim.eval.side_effect = self._eval_for({"g:anthropic_model": "old"})

        assert get_config("anthropic_model", legacy="g:anthropic_model") == "old"
        assert get_config("anthropic_model", legacy="g:anthropic_model") == "old"

        echoes = [c for c in mock_vim.command.call_args_list if "echomsg" in c.args[0]]
        assert len(echoes) == 1
        assert "g:anthropic_model is deprecated" in echoes[0].args[0]
        assert "g:llm_agent_anthropic_model" in echoes[0].args[0]

    @patch("chatgpt.utils.vim")
    def test_chat_gpt_fallback_does_not_echo(self, mock_vim):
        from tests.conftest import VimError

        mock_vim.error = VimError
        mock_vim.eval.side_effect = self._eval_for({"g:chat_gpt_model": "gpt-4"})
        assert get_config("model") == "gpt-4"
        echoes = [c for c in mock_vim.command.call_args_list if "echomsg" in c.args[0]]
        assert echoes == []

    @patch("chatgpt.utils.vim")
    def test_legacy_unset_returns_default(self, mock_vim):
        from tests.conftest import VimError

        mock_vim.error = VimError
        mock_vim.eval.return_value = ""
        assert get_config("gemini_model", "d", legacy="g:gemini_model") == "d"
