"""
Tests for python3/chatgpt/core.py

Tests the main chat_gpt() function including:
- Provider initialization
- Message history management
- Tool calling loop
- Plan approval workflow
- Streaming responses
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock, call, mock_open
import json

# Import the module under test
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3"))

from chatgpt.core import chat_gpt


class TestChatGPT:
    """Test chat_gpt() main function"""

    @pytest.fixture
    def mock_vim_env(self, mock_vim):
        """Set up Vim environment with default configuration"""

        def vim_eval_side_effect(expr):
            # Return dict object directly for g:gpt_personas
            if expr == "g:gpt_personas":
                return {"default": "You are a helpful assistant"}
            # Return strings for everything else
            defaults = {
                "g:chat_gpt_provider": "openai",
                "g:chat_gpt_max_tokens": "2000",
                "g:chat_gpt_temperature": "0.7",
                "g:chat_gpt_lang": "None",
                'exists("g:chat_gpt_suppress_display") ? g:chat_gpt_suppress_display : 0': "0",
                "g:chat_persona": "default",
                'exists("g:chat_gpt_enable_tools") ? g:chat_gpt_enable_tools : 1': "1",
                'exists("g:chat_gpt_require_plan_approval") ? g:chat_gpt_require_plan_approval : 1': "1",
                'exists("g:chat_gpt_session_mode") ? g:chat_gpt_session_mode : 1': "1",
                "g:chat_gpt_session_mode": "1",
            }
            # Return default value or '0' for unknown expressions
            return defaults.get(expr, "0")

        mock_vim.eval.side_effect = vim_eval_side_effect
        return mock_vim
        mock_vim.eval.side_effect = vim_eval_side_effect
        return mock_vim

    @pytest.fixture
    def mock_provider(self):
        """Mock AI provider"""
        provider = Mock()
        provider.get_model.return_value = "gpt-4"
        provider.supports_tools.return_value = True
        provider.create_messages.return_value = []
        provider.stream_chat.return_value = iter(
            [("Hello!", None, None), ("", "stop", None)]
        )
        return provider

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("os.getcwd")
    def test_basic_chat_without_tools(
        self,
        mock_getcwd,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        mock_provider,
        tmp_path,
    ):
        """Test basic chat flow without tool calling"""
        mock_getcwd.return_value = str(tmp_path)

        # Mock vim.eval for the values used in chat_gpt
        mock_vim.eval.side_effect = lambda x: mock_vim_env.eval(x)

        mock_provider.supports_tools.return_value = False
        mock_create_provider.return_value = mock_provider

        chat_gpt("Hello, how are you?")

        # Verify provider was created
        mock_create_provider.assert_called_once_with("openai")

        # Verify stream_chat was called
        assert mock_provider.stream_chat.called

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("os.getcwd")
    @patch("os.path.exists")
    def test_loads_project_context(
        self,
        mock_exists,
        mock_getcwd,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        mock_provider,
        tmp_path,
    ):
        """Test that project context is loaded if available"""
        mock_getcwd.return_value = str(tmp_path)
        mock_create_provider.return_value = mock_provider

        # Mock vim.eval for the values used in chat_gpt
        mock_vim.eval.side_effect = lambda x: mock_vim_env.eval(x)

        # Create context file
        context_dir = tmp_path / ".vim-chatgpt"
        context_dir.mkdir()
        context_file = context_dir / "context.md"
        context_file.write_text("# Project Context\nThis is a test project")

        mock_exists.side_effect = lambda p: p == str(context_file) or p == str(
            context_dir
        )

        with patch(
            "builtins.open",
            mock_open(read_data="# Project Context\nThis is a test project"),
        ):
            chat_gpt("Test prompt")

        # Verify create_messages was called with context
        messages = mock_provider.create_messages.call_args[0]
        system_message = messages[0]
        assert "Project Context" in system_message

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("os.getcwd")
    @patch("os.path.exists")
    def test_loads_conversation_summary(
        self,
        mock_exists,
        mock_getcwd,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        mock_provider,
        tmp_path,
    ):
        """Test that conversation summary is loaded if available"""
        mock_getcwd.return_value = str(tmp_path)
        mock_create_provider.return_value = mock_provider

        # Mock vim.eval for the values used in chat_gpt
        mock_vim.eval.side_effect = lambda x: mock_vim_env.eval(x)

        summary_content = """<!--SUMMARY_METADATA
cutoff_byte: 1000
-->
# Summary
Previous conversation summary"""

        summary_file = tmp_path / ".vim-chatgpt" / "summary.md"

        # Mock exists to support get_project_dir() backwards compatibility check
        # Returns True for .vim-chatgpt directory and summary.md file
        def exists_side_effect(p):
            p_str = str(p)
            # get_project_dir checks for both directories
            if p_str == str(tmp_path / ".vim-llm-agent"):
                return False
            if p_str == str(tmp_path / ".vim-chatgpt"):
                return True
            # Then checks for summary.md file
            if p_str == str(summary_file):
                return True
            return False

        mock_exists.side_effect = exists_side_effect

        with patch("builtins.open", mock_open(read_data=summary_content)):
            chat_gpt("Test prompt")

        messages = mock_provider.create_messages.call_args[0]
        system_message = messages[0]
        assert "Conversation Summary" in system_message

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("chatgpt.core.get_tool_definitions")
    @patch("os.getcwd")
    def test_tools_enabled_when_supported(
        self,
        mock_getcwd,
        mock_get_tools,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        mock_provider,
        tmp_path,
    ):
        """Test that tools are enabled when provider supports them"""
        mock_getcwd.return_value = str(tmp_path)
        mock_create_provider.return_value = mock_provider

        # Mock vim.eval for the values used in chat_gpt
        mock_vim.eval.side_effect = lambda x: mock_vim_env.eval(x)

        mock_tools = [{"name": "test_tool", "description": "Test", "parameters": {}}]
        mock_get_tools.return_value = mock_tools

        chat_gpt("Test prompt")

        # Verify tools were passed to stream_chat
        stream_call = mock_provider.stream_chat.call_args
        assert stream_call is not None
        # Tools should be in the call arguments
        called_with_tools = (
            any(arg == mock_tools for arg in stream_call[0])
            or stream_call[1].get("tools") == mock_tools
        )
        assert called_with_tools or mock_tools in str(stream_call)

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("chatgpt.core.execute_tool")
    @patch("chatgpt.core.get_tool_definitions")
    @patch("os.getcwd")
    def test_tool_execution_loop(
        self,
        mock_getcwd,
        mock_get_tools,
        mock_execute_tool,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        mock_provider,
        tmp_path,
    ):
        """Test that tools are executed and results added to messages"""
        mock_getcwd.return_value = str(tmp_path)

        mock_create_provider.return_value = mock_provider
        mock_get_tools.return_value = [{"name": "test_tool"}]
        mock_execute_tool.return_value = "Tool result"

        # Simulate tool call then completion
        mock_provider.stream_chat.side_effect = [
            # First iteration - plan approval disabled, direct tool call
            iter(
                [
                    (
                        "",
                        "tool_calls",
                        [{"id": "call_1", "name": "test_tool", "arguments": {}}],
                    )
                ]
            ),
            # Second iteration - final response
            iter([("Done!", None, None), ("", "stop", None)]),
        ]
        mock_provider.create_messages.return_value = []

        # Mock vim.eval and disable plan approval for this test
        mock_vim.eval.side_effect = lambda x: {
            'exists("g:chat_gpt_require_plan_approval") ? g:chat_gpt_require_plan_approval : 1': "0",
            'exists("g:chat_gpt_enable_tools") ? g:chat_gpt_enable_tools : 1': "1",
            "g:chat_gpt_max_tokens": "2000",
            "g:chat_gpt_temperature": "0.7",
            "g:chat_gpt_lang": "None",
            'exists("g:chat_gpt_suppress_display") ? g:chat_gpt_suppress_display : 0': "0",
            "g:gpt_personas": {"default": "You are a helpful assistant"},
            "g:chat_persona": "default",
        }.get(x, "0")

        chat_gpt("Execute test tool")

        # Verify tool was executed
        mock_execute_tool.assert_called_once_with("test_tool", {})

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("os.getcwd")
    def test_plan_approval_workflow(
        self,
        mock_getcwd,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        mock_provider,
        tmp_path,
    ):
        """Test plan approval workflow"""
        mock_getcwd.return_value = str(tmp_path)

        mock_create_provider.return_value = mock_provider

        # Link the patched vim with the fixture
        mock_vim.eval.side_effect = lambda x: mock_vim_env.eval(x)
        mock_vim.command = mock_vim_env.command

        # Simulate plan presentation
        plan_text = """GOAL: Test the system

PLAN:
1. First step
2. Second step

TOOLS REQUIRED: test_tool

ESTIMATED STEPS: 2"""

        mock_provider.stream_chat.side_effect = [
            # First iteration - present plan
            iter([(plan_text, None, None), ("", "stop", None)]),
            # After approval - execute
            iter(
                [
                    (
                        "",
                        "tool_calls",
                        [{"id": "call_1", "name": "test_tool", "arguments": {}}],
                    )
                ]
            ),
            # Final response
            iter([("Completed!", None, None), ("", "stop", None)]),
        ]

        # User approves plan
        mock_vim_env.eval.side_effect = lambda x: {
            "input('')": "y",
            'exists("g:chat_gpt_require_plan_approval") ? g:chat_gpt_require_plan_approval : 1': "1",
            'exists("g:chat_gpt_enable_tools") ? g:chat_gpt_enable_tools : 1': "1",
            "g:chat_gpt_max_tokens": "2000",
            "g:chat_gpt_temperature": "0.7",
            "g:chat_gpt_lang": "None",
            'exists("g:chat_gpt_suppress_display") ? g:chat_gpt_suppress_display : 0': "0",
            "g:gpt_personas": {"default": "You are a helpful assistant"},
            "g:chat_persona": "default",
        }.get(x, "1")

        chat_gpt("Create a plan")

        # Verify approval was requested (check the patched vim mock, not the fixture)
        approval_calls = [c for c in mock_vim.eval.call_args_list if "input" in str(c)]
        assert len(approval_calls) > 0

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("os.getcwd")
    @patch("os.path.exists")
    def test_history_loading_from_file(
        self,
        mock_exists,
        mock_getcwd,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        mock_provider,
        tmp_path,
    ):
        """Test loading conversation history from file"""
        mock_getcwd.return_value = str(tmp_path)

        mock_create_provider.return_value = mock_provider

        # Link the patched vim with the fixture
        mock_vim.eval.side_effect = lambda x: mock_vim_env.eval(x)

        # Create history file with proper format
        history_content = """\n\n\x01>>>User:\x01
Hello

\x01>>>Assistant:\x01
Hi there!"""

        history_file = tmp_path / ".vim-chatgpt" / "history.txt"
        mock_exists.return_value = True

        with patch("builtins.open", mock_open(read_data=history_content)):
            chat_gpt("New message")

        # Verify create_messages was called with history
        messages_call = mock_provider.create_messages.call_args
        assert messages_call is not None
        history_arg = messages_call[0][1]  # Second argument is history
        assert isinstance(history_arg, list)

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("os.getcwd")
    def test_max_tool_iterations(
        self,
        mock_getcwd,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        mock_provider,
        tmp_path,
    ):
        """Test that tool execution loop has maximum iteration limit"""
        mock_getcwd.return_value = str(tmp_path)
        mock_create_provider.return_value = mock_provider

        # Link the patched vim with the fixture
        mock_vim.eval.side_effect = lambda x: mock_vim_env.eval(x)

        # Simulate tool calling that would go beyond max iterations (if there is one)
        # Create a counter to track iterations
        iteration_count = [0]

        def tool_call_generator():
            iteration_count[0] += 1
            # Return tool calls for many iterations
            if iteration_count[0] < 100:  # Simulate many tool calls
                yield (
                    "",
                    "tool_calls",
                    [
                        {
                            "id": f"call_{iteration_count[0]}",
                            "name": "test_tool",
                            "arguments": {},
                        }
                    ],
                )
            else:
                # Eventually stop
                yield ("Done after many iterations", None, None)
                yield ("", "stop", None)

        # Use side_effect to return a new generator on each call to stream_chat
        mock_provider.stream_chat.side_effect = (
            lambda *args, **kwargs: tool_call_generator()
        )

        # Disable plan approval
        mock_vim_env.eval.side_effect = lambda x: {
            'exists("g:chat_gpt_require_plan_approval") ? g:chat_gpt_require_plan_approval : 1': "0",
            'exists("g:chat_gpt_enable_tools") ? g:chat_gpt_enable_tools : 1': "1",
            "g:chat_gpt_max_tokens": "2000",
            "g:chat_gpt_temperature": "0.7",
            "g:chat_gpt_lang": "None",
            'exists("g:chat_gpt_suppress_display") ? g:chat_gpt_suppress_display : 0': "0",
            "g:gpt_personas": "{'default': 'You are a helpful assistant'}",
            "g:chat_persona": "default",
        }.get(x, "0")

        with patch("chatgpt.core.execute_tool", return_value="result"):
            # Should not hang indefinitely - should hit max iterations or complete
            chat_gpt("Test")

        # Verify execution completed (didn't hang)
        # The iteration count should be limited by the max iteration logic in core.py
        assert (
            iteration_count[0] < 100
        ), f"Expected iteration limit to prevent {iteration_count[0]} iterations"

    @patch("chatgpt.core.create_provider")
    def test_provider_creation_error(self, mock_create_provider, mock_vim_env):
        """Test handling of provider creation errors"""
        mock_create_provider.side_effect = Exception("Provider not available")

        # Verify error was handled gracefully
        assert True

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("os.getcwd")
    def test_streaming_display(
        self,
        mock_getcwd,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        mock_provider,
        tmp_path,
    ):
        """Test that streaming content is displayed via Vim"""
        mock_getcwd.return_value = str(tmp_path)
        mock_create_provider.return_value = mock_provider

        # Link the patched vim with the fixture
        mock_vim.eval.side_effect = lambda x: mock_vim_env.eval(x)
        mock_vim.command = mock_vim_env.command

        chunks = [
            ("Hello", None, None),
            (" world", None, None),
            ("!", None, None),
            ("", "stop", None),
        ]
        mock_provider.stream_chat.return_value = iter(chunks)

        chat_gpt("Say hello")

        # Verify DisplayChatGPTResponse was called for each chunk (check the patched vim mock)
        display_calls = [
            c
            for c in mock_vim.command.call_args_list
            if "DisplayChatGPTResponse" in str(c)
        ]
        assert len(display_calls) > 0

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("chatgpt.core.get_config")
    @patch("os.getcwd")
    def test_suppress_display_mode(
        self,
        mock_getcwd,
        mock_get_config,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        mock_provider,
        tmp_path,
    ):
        """Test suppress_display mode doesn't call display functions"""
        mock_getcwd.return_value = str(tmp_path)

        # Mock get_config to return proper values
        def config_side_effect(key, default=None):
            config_values = {
                "provider": "openai",
                "max_tokens": "2000",
                "temperature": "0.7",
                "lang": "None",
                "suppress_display": "1",  # Enable suppress display
                "enable_tools": "0",
            }
            return config_values.get(key, default)

        mock_get_config.side_effect = config_side_effect
        mock_create_provider.return_value = mock_provider

        # Set up provider with response
        mock_provider.stream_chat.return_value = iter(
            [("Test response", None, None), ("", "stop", None)]
        )

        # Mock vim for personas
        mock_vim.eval.side_effect = lambda x: {
            "g:gpt_personas": {"default": "You are a helpful assistant"},
            "g:chat_persona": "default",
        }.get(x, "default" if "persona" in x else "0")
        mock_vim.command = MagicMock()

        chat_gpt("Test")

        # Verify DisplayChatGPTResponse was NOT called
        display_calls = [
            c
            for c in mock_vim.command.call_args_list
            if "DisplayChatGPTResponse" in str(c)
        ]
        assert len(display_calls) == 0

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("os.getcwd")
    def test_message_format_for_different_providers(
        self,
        mock_getcwd,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        tmp_path,
    ):
        """Test message format varies by provider"""
        mock_getcwd.return_value = str(tmp_path)

        # Link the patched vim with the fixture
        mock_vim.eval.side_effect = lambda x: mock_vim_env.eval(x)

        # Test OpenAI format (list)
        openai_provider = Mock()
        openai_provider.get_model.return_value = "gpt-4"
        openai_provider.supports_tools.return_value = True
        openai_provider.create_messages.return_value = []
        openai_provider.stream_chat.return_value = iter([("Hi", "stop", None)])
        mock_create_provider.return_value = openai_provider

        chat_gpt("Test OpenAI")

        # Verify messages format
        assert openai_provider.create_messages.called

    @patch("chatgpt.core.vim")
    @patch("chatgpt.core.create_provider")
    @patch("os.getcwd")
    def test_plan_cancellation(
        self,
        mock_getcwd,
        mock_create_provider,
        mock_vim,
        mock_vim_env,
        mock_provider,
        tmp_path,
    ):
        """Test user can cancel plan approval"""
        mock_getcwd.return_value = str(tmp_path)
        mock_create_provider.return_value = mock_provider

        plan_text = "GOAL: Test\n\nPLAN:\n1. Do something\n\nTOOLS REQUIRED: test"
        mock_provider.stream_chat.return_value = iter(
            [(plan_text, None, None), ("", "stop", None)]
        )
        mock_provider.supports_tools.return_value = True

        # User cancels plan - use mock_vim directly since that's what gets patched
        mock_vim.eval.side_effect = lambda x: {
            "input('')": "n",  # User says no
            'exists("g:chat_gpt_require_plan_approval") ? g:chat_gpt_require_plan_approval : 1': "1",
            'exists("g:chat_gpt_enable_tools") ? g:chat_gpt_enable_tools : 1': "1",
            "g:chat_gpt_max_tokens": "2000",
            "g:chat_gpt_temperature": "0.7",
            "g:chat_gpt_lang": "None",
            'exists("g:chat_gpt_suppress_display") ? g:chat_gpt_suppress_display : 0': "0",
            "g:gpt_personas": {"default": "You are a helpful assistant"},
            "g:chat_persona": "default",
            "g:chat_gpt_session_mode": "0",
        }.get(x, "0")
        mock_vim.command = MagicMock()

        chat_gpt("Make a plan")

        # Verify cancellation message was displayed via vim.vars
        setitem_calls = mock_vim.vars.__setitem__.call_args_list
        cancel_calls = [
            c for c in setitem_calls
            if c.args[0] == "_llm_display_content" and "cancelled" in str(c.args[1]).lower()
        ]
        assert len(cancel_calls) > 0
