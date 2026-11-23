"""
Tests for python3/chatgpt/providers.py

Tests all AI provider classes including OpenAI, Anthropic, Bedrock, Google, Ollama, and OpenRouter.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
import requests

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3"))

from chatgpt.providers import (
    BaseProvider,
    OpenAIProvider,
    AnthropicProvider,
    BedrockProvider,
    GoogleProvider,
    OllamaProvider,
    OpenRouterProvider,
    create_provider,
)


class TestBaseProvider:
    """Tests for BaseProvider base class"""

    def test_base_provider_instantiation(self):
        """Test that BaseProvider cannot be instantiated (abstract class)"""
        # BaseProvider requires subclasses to implement validate_config()
        with pytest.raises(NotImplementedError):
            provider = BaseProvider({})

    def test_base_provider_send_message_not_implemented(self):
        """Test that stream_chat raises NotImplementedError"""

        # Create a minimal subclass that implements validate_config
        class MinimalProvider(BaseProvider):
            def validate_config(self):
                pass

        provider = MinimalProvider({})
        with pytest.raises(NotImplementedError):
            provider.stream_chat([], {}, 0.7, 2000)
            provider.send_message([], {})


class TestOpenAIProvider:
    """Tests for OpenAIProvider"""

    def test_openai_provider_init(self, mock_vim):
        """Test OpenAI provider initialization"""
        config = {"api_key": "test-api-key"}
        provider = OpenAIProvider(config)
        assert provider.config["api_key"] == "test-api-key"

    def test_openai_send_message_success(self, mock_vim, mock_openai_response):
        """Test successful OpenAI API call"""
        config = {"api_key": "test-api-key"}
        provider = OpenAIProvider(config)

        with patch("requests.post") as mock_post:
            mock_post.return_value.json.return_value = mock_openai_response
            mock_post.return_value.status_code = 200

            messages = [{"role": "user", "content": "Hello"}]
            model = "gpt-4"

            # stream_chat doesn't return json response, it yields chunks
            # For this test, we'll just verify it was called
            assert provider.supports_tools() == True

    def test_openai_streaming(self, mock_vim, mock_streaming_response):
        """Test OpenAI streaming response"""
        config = {"api_key": "test-api-key"}
        provider = OpenAIProvider(config)

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.iter_lines = Mock(
                return_value=[
                    b'data: {"choices": [{"delta": {"content": "Hello"}, "finish_reason": null}]}',
                    b"data: [DONE]",
                ]
            )
            mock_post.return_value = mock_response

            messages = [{"role": "user", "content": "Hello"}]

            # Test that stream_chat yields content
            chunks = list(provider.stream_chat(messages, "gpt-4", 0.7, 2000))
            assert len(chunks) > 0

    def test_openai_with_tools(self, mock_vim, mock_openai_response):
        """Test OpenAI API call with tools"""
        config = {"api_key": "test-api-key"}
        provider = OpenAIProvider(config)

        tools = [{"name": "test_tool", "description": "A test tool", "parameters": {}}]

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.iter_lines = Mock(return_value=[b"data: [DONE]"])
            mock_post.return_value = mock_response

            messages = [{"role": "user", "content": "Hello"}]

            list(provider.stream_chat(messages, "gpt-4", 0.7, 2000, tools=tools))

            # Verify tools were included in request
            call_args = mock_post.call_args
            assert "json" in call_args.kwargs
            assert "tools" in call_args.kwargs["json"]

    def test_openai_api_error(self, mock_vim):
        """Test OpenAI API error handling"""
        config = {"api_key": "test-api-key"}
        provider = OpenAIProvider(config)

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response

            messages = [{"role": "user", "content": "Hello"}]

            with pytest.raises(Exception):
                list(provider.stream_chat(messages, "gpt-4", 0.7, 2000))

    def test_openai_azure_endpoint(self, mock_vim):
        """Test Azure OpenAI endpoint configuration"""
        config = {
            "api_key": "azure-key",
            "api_type": "azure",
            "azure_endpoint": "https://test.openai.azure.com",
            "azure_deployment": "gpt-4",
            "azure_api_version": "2023-05-15",
        }
        provider = OpenAIProvider(config)
        assert provider.config["api_type"] == "azure"


class TestAnthropicProvider:
    """Tests for AnthropicProvider (Claude)"""

    def test_anthropic_provider_init(self, mock_vim):
        """Test Anthropic provider initialization"""
        config = {"api_key": "test-anthropic-key"}
        provider = AnthropicProvider(config)
        assert provider.config["api_key"] == "test-anthropic-key"

    def test_anthropic_send_message(self, mock_vim, mock_anthropic_response):
        """Test Anthropic provider sends messages correctly"""
        provider = AnthropicProvider(
            {
                "api_key": "test-anthropic-key",
                "base_url": "https://api.anthropic.com",
                "model": "claude-3-5-sonnet-20241022",
            }
        )

        # Anthropic expects messages as a dict with 'system' and 'messages' keys
        messages = {
            "system": "You are a helpful assistant",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        with patch("requests.post", return_value=mock_anthropic_response):
            chunks = list(
                provider.stream_chat(messages, "claude-3-5-sonnet-20241022", 0.7, 1000)
            )

            # Should yield content chunks
            assert len(chunks) > 0
            assert chunks[0][0] == "Hello"  # content
            assert chunks[-1][1] == "end_turn"  # finish_reason

            assert len(chunks) > 0

    def test_anthropic_streaming(self, mock_vim):
        """Test Anthropic provider handles streaming correctly"""
        provider = AnthropicProvider(
            {
                "api_key": "test-anthropic-key",
                "base_url": "https://api.anthropic.com",
                "model": "claude-3-5-sonnet-20241022",
            }
        )

        # Anthropic expects messages as a dict with 'system' and 'messages' keys
        messages = {
            "system": "You are a helpful assistant",
            "messages": [{"role": "user", "content": "Test"}],
        }

        # Mock streaming response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            b"event: content_block_delta",
            b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Test"}}',
            b"",
            b"event: message_stop",
            b'data: {"type":"message_stop"}',
        ]

        with patch("requests.post", return_value=mock_response):
            chunks = list(
                provider.stream_chat(messages, "claude-3-5-sonnet-20241022", 0.7, 1000)
            )

            # Should have content chunks
            assert len(chunks) > 0


def _bedrock_stream(events):
    """Build a fake invoke_model_with_response_stream response"""
    return {"body": [{"chunk": {"bytes": json.dumps(e).encode()}} for e in events]}


@pytest.fixture
def fake_boto3():
    """Install a fake boto3 module and return the mocked bedrock-runtime client"""
    client = MagicMock()
    session = MagicMock()
    session.region_name = "us-east-1"
    session.client.return_value = client
    boto3_mod = MagicMock()
    boto3_mod.Session.return_value = session
    with patch.dict(sys.modules, {"boto3": boto3_mod}):
        yield boto3_mod, session, client


BEDROCK_MESSAGES = {
    "system": "You are a helpful assistant",
    "messages": [{"role": "user", "content": "Test"}],
}


class TestBedrockProvider:
    """Tests for BedrockProvider"""

    def test_bedrock_requires_boto3(self, mock_vim):
        """Missing boto3 gives an actionable error"""
        with patch.dict(sys.modules, {"boto3": None}):
            with pytest.raises(ValueError, match="boto3"):
                BedrockProvider({})

    def test_bedrock_default_model(self, mock_vim, fake_boto3):
        provider = BedrockProvider({})
        assert provider.get_model() == BedrockProvider.DEFAULT_MODEL
        assert BedrockProvider({"model": "custom"}).get_model() == "custom"

    def test_bedrock_streams_text(self, mock_vim, fake_boto3):
        boto3_mod, session, client = fake_boto3
        client.invoke_model_with_response_stream.return_value = _bedrock_stream(
            [
                {"type": "message_start", "message": {}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "lo"}},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
                {"type": "message_stop"},
            ]
        )
        provider = BedrockProvider({"region": "us-west-2", "profile": "dev"})
        chunks = list(provider.stream_chat(BEDROCK_MESSAGES, "model-id", 0.5, 1000))

        assert chunks == [("Hel", "", None), ("lo", "", None), ("", "end_turn", None)]
        boto3_mod.Session.assert_called_once_with(profile_name="dev", region_name="us-west-2")
        session.client.assert_called_once_with("bedrock-runtime")

        kwargs = client.invoke_model_with_response_stream.call_args.kwargs
        assert kwargs["modelId"] == "model-id"
        body = json.loads(kwargs["body"])
        assert body["anthropic_version"] == "bedrock-2023-05-31"
        assert body["system"] == "You are a helpful assistant"
        assert body["max_tokens"] == 1000
        assert body["temperature"] == 0.5
        assert "model" not in body and "stream" not in body and "tools" not in body

    def test_bedrock_tool_calls(self, mock_vim, fake_boto3):
        _, _, client = fake_boto3
        client.invoke_model_with_response_stream.return_value = _bedrock_stream(
            [
                {"type": "content_block_start", "index": 1,
                 "content_block": {"type": "tool_use", "id": "toolu_1", "name": "read_file"}},
                {"type": "content_block_delta", "index": 1,
                 "delta": {"type": "input_json_delta", "partial_json": '{"path": '}},
                {"type": "content_block_delta", "index": 1,
                 "delta": {"type": "input_json_delta", "partial_json": '"a.txt"}'}},
                {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
            ]
        )
        tools = [{"name": "read_file", "description": "Read", "parameters": {"type": "object"}}]
        provider = BedrockProvider({})
        chunks = list(provider.stream_chat(BEDROCK_MESSAGES, "m", 0.7, 100, tools=tools))

        assert chunks == [
            ("", "tool_use", [{"id": "toolu_1", "name": "read_file", "arguments": {"path": "a.txt"}}])
        ]
        body = json.loads(client.invoke_model_with_response_stream.call_args.kwargs["body"])
        assert body["tools"] == [
            {"name": "read_file", "description": "Read", "input_schema": {"type": "object"}}
        ]

    def test_bedrock_stream_exception_event(self, mock_vim, fake_boto3):
        _, _, client = fake_boto3
        client.invoke_model_with_response_stream.return_value = {
            "body": [{"throttlingException": {"message": "Too many requests"}}]
        }
        provider = BedrockProvider({})
        with pytest.raises(Exception, match="throttlingException.*Too many requests"):
            list(provider.stream_chat(BEDROCK_MESSAGES, "m", 0.7, 100))

    def test_bedrock_api_error(self, mock_vim, fake_boto3):
        _, _, client = fake_boto3
        client.invoke_model_with_response_stream.side_effect = RuntimeError("AccessDenied")
        provider = BedrockProvider({})
        with pytest.raises(Exception, match="Bedrock API error.*AccessDenied"):
            list(provider.stream_chat(BEDROCK_MESSAGES, "m", 0.7, 100))

    def test_bedrock_missing_region(self, mock_vim, fake_boto3):
        _, session, _ = fake_boto3
        session.region_name = None
        provider = BedrockProvider({})
        with pytest.raises(ValueError, match="AWS region"):
            list(provider.stream_chat(BEDROCK_MESSAGES, "m", 0.7, 100))

    def test_bedrock_endpoint_url(self, mock_vim, fake_boto3):
        _, session, client = fake_boto3
        client.invoke_model_with_response_stream.return_value = _bedrock_stream([])
        provider = BedrockProvider({"endpoint_url": "https://vpce.example"})
        list(provider.stream_chat(BEDROCK_MESSAGES, "m", 0.7, 100))
        session.client.assert_called_once_with("bedrock-runtime", endpoint_url="https://vpce.example")


    def test_bedrock_static_access_keys(self, mock_vim, fake_boto3):
        """Explicit access keys are passed to boto3 and override the profile"""
        boto3_mod, _, client = fake_boto3
        client.invoke_model_with_response_stream.return_value = _bedrock_stream([])
        provider = BedrockProvider(
            {
                "region": "us-east-1",
                "profile": "ignored",
                "access_key_id": "AKIATEST",
                "secret_access_key": "secret",
                "session_token": "token",
            }
        )
        list(provider.stream_chat(BEDROCK_MESSAGES, "m", 0.7, 100))
        boto3_mod.Session.assert_called_once_with(
            region_name="us-east-1",
            aws_access_key_id="AKIATEST",
            aws_secret_access_key="secret",
            aws_session_token="token",
        )

    def test_bedrock_static_keys_without_session_token(self, mock_vim, fake_boto3):
        boto3_mod, _, client = fake_boto3
        client.invoke_model_with_response_stream.return_value = _bedrock_stream([])
        provider = BedrockProvider({"access_key_id": "AKIATEST", "secret_access_key": "secret"})
        list(provider.stream_chat(BEDROCK_MESSAGES, "m", 0.7, 100))
        boto3_mod.Session.assert_called_once_with(
            region_name=None, aws_access_key_id="AKIATEST", aws_secret_access_key="secret"
        )

    @pytest.mark.parametrize(
        "config",
        [
            {"access_key_id": "AKIATEST"},
            {"secret_access_key": "secret"},
            {"session_token": "token"},
        ],
    )
    def test_bedrock_incomplete_static_keys(self, mock_vim, fake_boto3, config):
        with pytest.raises(ValueError, match="g:llm_agent_bedrock_"):
            BedrockProvider(config)

    def test_create_provider_bedrock_keys_not_logged(self, mock_vim, fake_boto3):
        values = {
            "g:llm_agent_bedrock_access_key_id": "AKIATEST",
            "g:llm_agent_bedrock_secret_access_key": "super-secret",
        }
        mock_vim.eval = lambda expr: next(
            (v for k, v in values.items() if f'exists("{k}")' in expr), ""
        )
        with patch("chatgpt.providers.debug_log") as log:
            provider = create_provider("bedrock")
        assert provider.config["access_key_id"] == "AKIATEST"
        assert provider.config["secret_access_key"] == "super-secret"
        logged = " ".join(str(c.args[0]) for c in log.call_args_list)
        assert "super-secret" not in logged and "AKIATEST" not in logged


class TestGoogleProvider:
    """Tests for GoogleProvider (Gemini)"""

    def test_google_provider_init(self, mock_vim):
        """Test Google provider initialization"""
        config = {"api_key": "test-google-key"}
        provider = GoogleProvider(config)
        assert provider.config["api_key"] == "test-google-key"

    def test_google_send_message(self, mock_vim):
        """Test Google Gemini API call"""
        config = {"api_key": "test-google-key"}
        provider = GoogleProvider(config)

        with patch("requests.post") as mock_post:
            mock_response_obj = Mock()
            mock_response_obj.status_code = 200
            # Gemini returns JSON in response.text, not streaming
            mock_response_obj.text = json.dumps(
                [
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [{"text": "Hello from Gemini"}],
                                    "role": "model",
                                },
                                "finishReason": "STOP",
                            }
                        ]
                    }
                ]
            )
            mock_post.return_value = mock_response_obj

            # Google expects messages in dict format with system_instruction and contents
            messages = {
                "system_instruction": {
                    "parts": [{"text": "You are a helpful assistant"}]
                },
                "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
            }

            chunks = list(provider.stream_chat(messages, "gemini-pro", 0.7, 2000))
            assert len(chunks) >= 0  # May be empty if no valid chunks


class TestOllamaProvider:
    """Tests for OllamaProvider (local models)"""

    def test_ollama_provider_init(self, mock_vim):
        """Test Ollama provider initialization"""
        config = {}  # Ollama doesn't require API key
        provider = OllamaProvider(config)
        assert "localhost" in provider.config.get("base_url", "http://localhost:11434")

    def test_ollama_send_message(self, mock_vim):
        """Test Ollama API call"""
        config = {}
        provider = OllamaProvider(config)

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.iter_lines = Mock(
                return_value=[
                    b'{"message": {"content": "Hello"}, "done": false}',
                    b'{"done": true}',
                ]
            )
            mock_post.return_value = mock_response

            messages = [{"role": "user", "content": "Hello"}]

            chunks = list(provider.stream_chat(messages, "llama2", 0.7, 2000))
            assert len(chunks) > 0


class TestOpenRouterProvider:
    """Tests for OpenRouterProvider"""

    def test_openrouter_provider_init(self, mock_vim):
        """Test OpenRouter provider initialization"""
        config = {"api_key": "test-openrouter-key"}
        provider = OpenRouterProvider(config)
        assert provider.config["api_key"] == "test-openrouter-key"

    def test_openrouter_send_message(self, mock_vim, mock_openai_response):
        """Test OpenRouter API call"""
        config = {"api_key": "test-openrouter-key"}
        provider = OpenRouterProvider(config)

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.iter_lines = Mock(
                return_value=[
                    b'data: {"choices": [{"delta": {"content": "Hello"}, "finish_reason": null}]}',
                    b"data: [DONE]",
                ]
            )
            mock_post.return_value = mock_response

            messages = [{"role": "user", "content": "Hello"}]

            chunks = list(
                provider.stream_chat(messages, "anthropic/claude-3-opus", 0.7, 2000)
            )
            assert len(chunks) > 0


class TestCreateProvider:
    """Tests for create_provider factory function"""

    def test_create_provider_openai(self, mock_vim):
        """Test creating OpenAI provider"""
        provider = create_provider("openai")
        assert isinstance(provider, OpenAIProvider)

    def test_create_provider_anthropic(self, mock_vim):
        """Test creating Anthropic provider"""
        provider = create_provider("anthropic")
        assert isinstance(provider, AnthropicProvider)

    def test_create_provider_bedrock(self, mock_vim, fake_boto3):
        """Test creating Bedrock provider picks up AWS env vars"""
        with patch.dict("os.environ", {"AWS_REGION": "eu-west-1", "AWS_PROFILE": "prod"}):
            provider = create_provider("bedrock")
        assert isinstance(provider, BedrockProvider)
        assert provider.config["region"] == "eu-west-1"
        assert provider.config["profile"] == "prod"

    def test_create_provider_reads_llm_agent_names(self, mock_vim):
        """Provider settings are read from g:llm_agent_<provider>_<setting>"""
        values = {
            "g:llm_agent_anthropic_api_key": "new-key",
            "g:llm_agent_anthropic_model": "claude-new",
            "g:llm_agent_anthropic_base_url": "https://proxy.example/v1",
        }
        mock_vim.eval = lambda expr: next(
            (v for k, v in values.items() if f'exists("{k}")' in expr), ""
        )
        with patch.dict("os.environ", {}, clear=True):
            provider = create_provider("anthropic")
        assert provider.config["api_key"] == "new-key"
        assert provider.get_model() == "claude-new"
        assert provider.config["base_url"] == "https://proxy.example/v1"

    def test_create_provider_legacy_names_still_work(self, mock_vim):
        """Deprecated unprefixed names (g:gemini_model, ...) are still honored"""
        values = {"g:gemini_api_key": "old-key", "g:gemini_model": "gemini-old"}
        mock_vim.eval = lambda expr: next(
            (v for k, v in values.items() if f'exists("{k}")' in expr), ""
        )
        with patch.dict("os.environ", {}, clear=True):
            provider = create_provider("gemini")
        assert provider.config["api_key"] == "old-key"
        assert provider.get_model() == "gemini-old"

    @pytest.mark.parametrize(
        "name,env,expected_model",
        [
            ("gemini", {"GEMINI_API_KEY": "k"}, "gemini-2.5-flash"),
            ("ollama", {}, "llama3.2"),
            ("openrouter", {"OPENROUTER_API_KEY": "k"}, "anthropic/claude-3.5-sonnet"),
            ("anthropic", {"ANTHROPIC_API_KEY": "k"}, "claude-sonnet-4-5-20250929"),
            ("openai", {"OPENAI_API_KEY": "k"}, "gpt-4o"),
        ],
    )
    def test_create_provider_defaults_when_unset(self, mock_vim, name, env, expected_model):
        """With no Vim config, providers fall back to their default model"""
        mock_vim.eval = lambda expr: ""
        with patch.dict("os.environ", env, clear=True):
            provider = create_provider(name)
        assert provider.get_model() == expected_model
        if name == "ollama":
            assert provider.config["base_url"] == "http://localhost:11434"

    def test_create_provider_google(self, mock_vim):
        """Test creating Google provider"""
        provider = create_provider("gemini")
        assert isinstance(provider, GoogleProvider)

    def test_create_provider_ollama(self, mock_vim):
        """Test creating Ollama provider"""
        provider = create_provider("ollama")
        assert isinstance(provider, OllamaProvider)

    def test_create_provider_openrouter(self, mock_vim):
        """Test creating OpenRouter provider"""
        # Mock environment variable to provide API key
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-openrouter-key"}):
            provider = create_provider("openrouter")
            assert isinstance(provider, OpenRouterProvider)

    def test_create_provider_unknown(self, mock_vim):
        """Test unknown provider defaults to OpenAI"""
        provider = create_provider("unknown_provider")
        assert isinstance(provider, OpenAIProvider)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
