"""
Pytest fixtures and configuration for vim-chatgpt tests

This module provides shared fixtures for mocking the Vim environment
and common test utilities.
"""

import pytest
import sys
from unittest.mock import MagicMock, Mock
import os
import tempfile
import shutil

# Mock vim module BEFORE any imports happen
# This needs to be at module level so it runs before test discovery
vim_mock = MagicMock()


# Create proper vim.error exception class
class VimError(Exception):
    pass


vim_mock.error = VimError
vim_mock.eval = MagicMock(return_value="")
vim_mock.command = MagicMock()
vim_mock.current = MagicMock()
vim_mock.current.buffer = []
sys.modules["vim"] = vim_mock


@pytest.fixture
def mock_vim():
    """Mock the vim module for testing outside of Vim"""
    vim_mock = MagicMock()

    # Mock vim.eval() to return sensible defaults
    def mock_eval(expr):
        defaults = {
            "g:chat_gpt_max_tokens": "2000",
            "g:chat_gpt_model": "gpt-4",
            "g:chat_gpt_session_mode": "0",
            "g:chat_gpt_temperature": "0.7",
            "g:chat_gpt_custom_persona": "",
            "g:chat_gpt_lang": "None",
            "g:chat_gpt_split_direction": "vertical",
            "g:chat_gpt_debug": "0",
            "g:chat_gpt_log_level": "0",
            "g:openai_api_key": "test-api-key",
            "g:anthropic_api_key": "test-anthropic-key",
            "g:gemini_api_key": "test-gemini-key",
            "g:openrouter_api_key": "test-openrouter-key",
            "g:chat_gpt_suppress_display": "0",
            "g:chat_gpt_session_id": "test-session",
            "g:chat_gpt_provider": "openai",
            "g:chat_persona": "default",
            "g:llm_agent_persona": "default",
            "g:gpt_personas": {
                "default": "You are a helpful assistant"
            },  # Return actual dict
            'exists("g:chat_gpt_custom_persona")': "0",
            'exists("g:chat_gpt_suppress_display") ? g:chat_gpt_suppress_display : 0': "0",
            'exists("g:chat_gpt_enable_tools") ? g:chat_gpt_enable_tools : 1': "1",
            'exists("g:chat_gpt_require_plan_approval") ? g:chat_gpt_require_plan_approval : 1': "1",
            'exists("g:chat_gpt_session_mode") ? g:chat_gpt_session_mode : 1': "0",
            'exists("g:chat_gpt_log_level") ? g:chat_gpt_log_level : 0': "0",
        }
        return defaults.get(expr, "")

    vim_mock.eval = mock_eval
    vim_mock.command = MagicMock()
    vim_mock.current = MagicMock()
    vim_mock.current.buffer = []
    vim_mock.error = VimError

    # Update the global mock
    sys.modules["vim"] = vim_mock

    yield vim_mock


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing"""
    temp_dir = tempfile.mkdtemp(prefix="vim_chatgpt_test_")

    # Create a .git directory to simulate a git repo
    git_dir = os.path.join(temp_dir, ".git")
    os.makedirs(git_dir)

    # Create a .vim-chatgpt directory
    vim_chatgpt_dir = os.path.join(temp_dir, ".vim-chatgpt")
    os.makedirs(vim_chatgpt_dir)

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_history_file(temp_project_dir):
    """Create a mock history file"""
    history_path = os.path.join(temp_project_dir, ".vim-chatgpt", "history.txt")
    with open(history_path, "w") as f:
        f.write(
            "\x01>>>User:\x01\nHello\n\n"
            "\x01>>>Assistant:\x01\nHi there!\n\n"
        )
    return history_path


@pytest.fixture
def mock_context_file(temp_project_dir):
    """Create a mock context file"""
    context_path = os.path.join(temp_project_dir, ".vim-chatgpt", "context.md")
    with open(context_path, "w") as f:
        f.write("# Project Context\n\nThis is a test project.\n")
    return context_path


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response"""
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "This is a test response"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.iter_lines.return_value = [
        b"event: content_block_start",
        b'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
        b"",
        b"event: content_block_delta",
        b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}',
        b"",
        b"event: content_block_stop",
        b'data: {"type":"content_block_stop","index":0}',
        b"",
        b"event: message_delta",
        b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}',
        b"",
        b"event: message_stop",
        b'data: {"type":"message_stop"}',
    ]
    return mock_response


@pytest.fixture
def mock_streaming_response():
    """Mock streaming SSE response"""

    def generate_chunks():
        chunks = [
            b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n',
            b'data: {"choices": [{"delta": {"content": " world"}}]}\n\n',
            b'data: {"choices": [{"delta": {}}], "finish_reason": "stop"}\n\n',
            b"data: [DONE]\n\n",
        ]
        for chunk in chunks:
            yield chunk

    mock_response = Mock()
    mock_response.iter_lines = Mock(return_value=generate_chunks())
    mock_response.status_code = 200
    return mock_response


@pytest.fixture
def sample_tool_call():
    """Sample tool call for testing"""
    return {
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "find_file",
            "arguments": '{"pattern": "*.py", "max_results": 10}',
        },
    }


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables"""
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
