"""
AI Provider abstraction layer for multi-provider support

This module provides a unified interface for interacting with different LLM providers
including OpenAI, Anthropic (Claude), AWS Bedrock, Google (Gemini), Ollama, and OpenRouter.
"""

import os
import json
import requests
from urllib.parse import urlparse

from chatgpt.utils import debug_log, get_config


# Provider abstraction layer for multi-provider support
class BaseProvider:
    """Base interface for all LLM providers"""

    def __init__(self, config):
        self.config = config
        self.validate_config()

    def validate_config(self):
        """Validate required configuration"""
        raise NotImplementedError("Subclasses must implement validate_config()")

    def get_model(self):
        """Get the model name from config"""
        raise NotImplementedError("Subclasses must implement get_model()")

    def create_messages(self, system_message, history, user_message):
        """Format messages for provider's API"""
        raise NotImplementedError("Subclasses must implement create_messages()")

    def stream_chat(self, messages, model, temperature, max_tokens, tools=None):
        """
        Stream chat completion chunks
        Yields: (content_delta, finish_reason, tool_calls)
        tool_calls format: [{"id": "...", "name": "...", "arguments": {...}}] or None
        """
        raise NotImplementedError("Subclasses must implement stream_chat()")

    def supports_tools(self):
        """Whether this provider supports function/tool calling"""
        return False

    def format_tools_for_api(self, tools):
        """Format tool definitions for this provider's API"""
        return tools


class OpenAIProvider(BaseProvider):
    """OpenAI and Azure OpenAI provider using HTTP requests"""

    def validate_config(self):
        """Validate OpenAI configuration"""
        if not self.config.get("api_key"):
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY or g:llm_agent_openai_api_key"
            )

        # Validate Azure-specific config if using Azure
        if self.config.get("api_type") == "azure":
            if not self.config.get("azure_endpoint"):
                raise ValueError("Azure endpoint required. Set g:llm_agent_azure_endpoint")
            if not self.config.get("azure_deployment"):
                raise ValueError("Azure deployment required. Set g:llm_agent_azure_deployment")
            if not self.config.get("azure_api_version"):
                raise ValueError("Azure API version required. Set g:llm_agent_azure_api_version")

    def get_model(self):
        """Get the model name from config"""
        return self.config.get("model") or "gpt-4o"

    def create_messages(self, system_message, history, user_message):
        """Create messages in OpenAI format"""
        messages = [{"role": "system", "content": system_message}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def supports_tools(self):
        """OpenAI supports function calling"""
        return True

    def format_tools_for_api(self, tools):
        """Format tools for OpenAI API"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in tools
        ]

    def stream_chat(self, messages, model, temperature, max_tokens, tools=None):
        """Stream chat completion from OpenAI via HTTP"""
        # Determine if using Azure or standard OpenAI
        api_type = self.config.get("api_type")

        if api_type == "azure":
            # Azure OpenAI endpoint format
            azure_endpoint = self.config["azure_endpoint"].rstrip("/")
            azure_deployment = self.config["azure_deployment"]
            azure_api_version = self.config["azure_api_version"]
            url = f"{azure_endpoint}/openai/deployments/{azure_deployment}/chat/completions?api-version={azure_api_version}"

            headers = {
                "api-key": self.config["api_key"],
                "Content-Type": "application/json",
            }
        else:
            # Standard OpenAI endpoint
            base_url = self.config.get("base_url") or "https://api.openai.com/v1"
            base_url = base_url.rstrip("/")
            url = f"{base_url}/chat/completions"

            headers = {
                "Authorization": f'Bearer {self.config["api_key"]}',
                "Content-Type": "application/json",
            }

        # Build payload
        payload = {"model": model, "messages": messages, "stream": True}

        # Add tools if provided
        if tools:
            payload["tools"] = self.format_tools_for_api(tools)
            payload["tool_choice"] = "auto"

        # Handle different model parameter requirements
        if model.startswith("gpt-"):
            payload["temperature"] = temperature
            payload["max_tokens"] = max_tokens
        else:
            # O-series models use different parameters
            payload["max_completion_tokens"] = max_tokens

        response = requests.post(
            url, headers=headers, json=payload, stream=True, timeout=60
        )

        # Check for HTTP errors
        if response.status_code != 200:
            error_body = response.text
            raise Exception(
                f"OpenAI API error (status {response.status_code}): {error_body}"
            )

        # Parse Server-Sent Events stream
        tool_calls_accumulator = {}  # Accumulate tool call chunks by index

        for line in response.iter_lines():
            if not line:
                continue

            line = line.decode("utf-8", errors="replace")
            if not line.startswith("data: "):
                continue

            data = line[6:]  # Remove 'data: ' prefix
            if data == "[DONE]":
                break

            try:
                chunk = json.loads(data)
                if "choices" in chunk and chunk["choices"]:
                    choice = chunk["choices"][0]
                    delta = choice.get("delta", {})
                    content = delta.get("content", "")
                    finish_reason = choice.get("finish_reason", "")

                    # Handle tool calls (streamed in chunks)
                    if "tool_calls" in delta:
                        for tool_call_chunk in delta["tool_calls"]:
                            idx = tool_call_chunk.get("index", 0)
                            if idx not in tool_calls_accumulator:
                                tool_calls_accumulator[idx] = {
                                    "id": "",
                                    "name": "",
                                    "arguments": "",
                                }

                            if "id" in tool_call_chunk:
                                tool_calls_accumulator[idx]["id"] = tool_call_chunk[
                                    "id"
                                ]
                            if "function" in tool_call_chunk:
                                func = tool_call_chunk["function"]
                                if "name" in func:
                                    tool_calls_accumulator[idx]["name"] = func["name"]
                                if "arguments" in func:
                                    tool_calls_accumulator[idx]["arguments"] += func[
                                        "arguments"
                                    ]

                    # Yield content if present
                    if content:
                        yield (content, "", None)

                    # On finish, yield tool calls if any
                    if finish_reason:
                        tool_calls = None
                        if tool_calls_accumulator:
                            tool_calls = []
                            for tool_data in tool_calls_accumulator.values():
                                try:
                                    tool_calls.append(
                                        {
                                            "id": tool_data["id"],
                                            "name": tool_data["name"],
                                            "arguments": json.loads(
                                                tool_data["arguments"]
                                            ),
                                        }
                                    )
                                except json.JSONDecodeError:
                                    pass  # Skip malformed tool calls
                        yield ("", finish_reason, tool_calls)
            except json.JSONDecodeError:
                continue


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider using HTTP requests"""

    name = "Anthropic"

    def validate_config(self):
        """Validate Anthropic configuration"""
        if not self.config.get("api_key"):
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY or g:llm_agent_anthropic_api_key"
            )

    def get_model(self):
        """Get the model name from config"""
        return self.config.get("model") or "claude-sonnet-4-5-20250929"

    def create_messages(self, system_message, history, user_message):
        """Create messages in Anthropic format"""
        # Anthropic separates system message from messages array
        messages = []
        for msg in history:
            if msg.get("role") != "system":
                messages.append(msg)
        messages.append({"role": "user", "content": user_message})

        return {"system": system_message, "messages": messages}

    def supports_tools(self):
        """Anthropic supports tool use"""
        return True

    def format_tools_for_api(self, tools):
        """Format tools for Anthropic API"""
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["parameters"],
            }
            for tool in tools
        ]

    def _validate_messages(self, messages):
        """Validate the Anthropic-style messages dict"""
        if not isinstance(messages, dict):
            raise ValueError(f"messages must be a dict, got {type(messages)}")
        if "system" not in messages:
            raise ValueError("messages dict must have 'system' key")
        if "messages" not in messages:
            raise ValueError("messages dict must have 'messages' key")
        if not isinstance(messages["messages"], list):
            raise ValueError(
                f"messages['messages'] must be a list, got {type(messages['messages'])}"
            )
        if len(messages["messages"]) == 0:
            raise ValueError("messages['messages'] cannot be empty")

    def _build_payload(self, messages, temperature, max_tokens, tools):
        """Build the request body shared by Anthropic and Bedrock"""
        payload = {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": messages["system"],
            "messages": messages["messages"],
        }
        if tools:
            formatted = self.format_tools_for_api(tools)
            payload["tools"] = formatted
            debug_log(f"INFO: Sending {len(formatted)} tools to {self.name} API")
            debug_log(f"DEBUG: Tool names being sent: {[t['name'] for t in formatted]}")
        else:
            debug_log(f"WARNING: No tools being sent to {self.name} API")
        return payload

    def stream_chat(self, messages, model, temperature, max_tokens, tools=None):
        """Stream chat completion from Anthropic"""
        self._validate_messages(messages)

        debug_log(
            f"DEBUG: Anthropic stream_chat called with {len(messages['messages'])} messages"
        )

        headers = {
            "x-api-key": self.config["api_key"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = self._build_payload(messages, temperature, max_tokens, tools)
        payload["model"] = model
        payload["stream"] = True

        # Construct URL - ensure we reach the /v1/messages endpoint
        base_url = self.config.get("base_url")
        if not base_url:
            raise ValueError("base_url is required for Anthropic provider")
        base_url = base_url.rstrip("/")
        parsed = urlparse(base_url)
        path = parsed.path.rstrip("/")
        if path.endswith("/messages"):
            url = base_url
        elif path.endswith("/v1"):
            url = base_url + "/messages"
        else:
            url = base_url + "/v1/messages"

        debug_log(f"DEBUG: Making request to Anthropic API: {url}")

        response = requests.post(
            url, headers=headers, json=payload, stream=True, timeout=60
        )

        # Check for HTTP errors
        if response.status_code != 200:
            error_body = response.text
            raise Exception(
                f"Anthropic API error (status {response.status_code}) at {url}: {error_body}"
            )

        yield from self._parse_stream_events(self._iter_sse_events(response))

    @staticmethod
    def _iter_sse_events(response):
        """Yield decoded JSON events from a Server-Sent Events response"""
        for line in response.iter_lines():
            if not line:
                continue

            line = line.decode("utf-8", errors="replace")
            if not line.startswith("data: "):
                continue

            data = line[6:]  # Remove 'data: ' prefix
            if data == "[DONE]":
                break

            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                continue

    @staticmethod
    def _parse_stream_events(events):
        """
        Convert Anthropic Messages streaming events into
        (content_delta, finish_reason, tool_calls) tuples.
        """
        tool_use_blocks = {}  # Accumulate tool use blocks

        for chunk in events:
            chunk_type = chunk.get("type")

            # Handle text content
            if chunk_type == "content_block_delta":
                delta = chunk.get("delta", {})
                if delta.get("type") == "text_delta":
                    content = delta.get("text", "")
                    if content:
                        yield (content, "", None)
                elif delta.get("type") == "input_json_delta":
                    # Accumulate tool use input
                    idx = chunk.get("index", 0)
                    if idx not in tool_use_blocks:
                        tool_use_blocks[idx] = {"id": "", "name": "", "input": ""}
                    tool_use_blocks[idx]["input"] += delta.get("partial_json", "")

            # Handle tool use block start
            elif chunk_type == "content_block_start":
                block = chunk.get("content_block", {})
                if block.get("type") == "tool_use":
                    idx = chunk.get("index", 0)
                    tool_use_blocks[idx] = {
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "input": "",
                    }

            # Handle message end
            elif chunk_type == "message_delta":
                finish_reason = chunk.get("delta", {}).get("stop_reason", "")
                if finish_reason:
                    # Convert accumulated tool blocks to tool_calls
                    tool_calls = None
                    if tool_use_blocks:
                        tool_calls = []
                        for tool_data in tool_use_blocks.values():
                            try:
                                # Handle empty input (tools with no parameters)
                                tool_input = tool_data["input"].strip()
                                arguments = json.loads(tool_input) if tool_input else {}
                                tool_calls.append(
                                    {
                                        "id": tool_data["id"],
                                        "name": tool_data["name"],
                                        "arguments": arguments,
                                    }
                                )
                            except json.JSONDecodeError:
                                pass  # Skip malformed tool calls
                    yield ("", finish_reason, tool_calls)

            # Bedrock surfaces mid-stream errors as events
            elif chunk_type == "error":
                error = chunk.get("error", {})
                raise Exception(
                    f"API stream error: {error.get('type', 'error')}: {error.get('message', chunk)}"
                )


class BedrockProvider(AnthropicProvider):
    """
    Claude models on AWS Bedrock.

    Uses the Anthropic Messages format via InvokeModelWithResponseStream, so
    message history and tool handling are identical to AnthropicProvider.
    Authentication uses the standard AWS credential chain (env vars, profiles,
    SSO, instance roles) through boto3, which is only imported when this
    provider is selected. Static access keys can also be set explicitly via
    g:llm_agent_bedrock_access_key_id / g:llm_agent_bedrock_secret_access_key
    (plus g:llm_agent_bedrock_session_token for temporary credentials), which
    take precedence over the credential chain and any profile.
    """

    name = "Bedrock"
    DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    def validate_config(self):
        """Validate Bedrock configuration (credentials are resolved by boto3)"""
        try:
            import boto3  # noqa: F401
        except ImportError:
            raise ValueError(
                "The Bedrock provider requires boto3. Install it into Vim's Python: pip install boto3"
            )

        has_key_id = bool(self.config.get("access_key_id"))
        has_secret = bool(self.config.get("secret_access_key"))
        if has_key_id != has_secret:
            raise ValueError(
                "Bedrock access keys require both g:llm_agent_bedrock_access_key_id "
                "and g:llm_agent_bedrock_secret_access_key"
            )
        if self.config.get("session_token") and not has_key_id:
            raise ValueError(
                "g:llm_agent_bedrock_session_token requires "
                "g:llm_agent_bedrock_access_key_id and g:llm_agent_bedrock_secret_access_key"
            )

    def get_model(self):
        """Get the Bedrock model ID or inference profile ID"""
        return self.config.get("model") or self.DEFAULT_MODEL

    def _client(self):
        import boto3

        session_kwargs = {"region_name": self.config.get("region") or None}
        if self.config.get("access_key_id"):
            # Explicit keys win; skip the profile so a missing/unrelated
            # AWS_PROFILE can't interfere.
            session_kwargs["aws_access_key_id"] = self.config["access_key_id"]
            session_kwargs["aws_secret_access_key"] = self.config["secret_access_key"]
            if self.config.get("session_token"):
                session_kwargs["aws_session_token"] = self.config["session_token"]
        else:
            session_kwargs["profile_name"] = self.config.get("profile") or None
        session = boto3.Session(**session_kwargs)
        if not session.region_name:
            raise ValueError(
                "AWS region required for Bedrock. Set AWS_REGION or g:llm_agent_bedrock_region"
            )
        kwargs = {}
        if self.config.get("endpoint_url"):
            kwargs["endpoint_url"] = self.config["endpoint_url"]
        return session.client("bedrock-runtime", **kwargs)

    def stream_chat(self, messages, model, temperature, max_tokens, tools=None):
        """Stream chat completion from Bedrock"""
        self._validate_messages(messages)

        debug_log(
            f"DEBUG: Bedrock stream_chat called with {len(messages['messages'])} messages, model={model}"
        )

        payload = self._build_payload(messages, temperature, max_tokens, tools)
        payload["anthropic_version"] = "bedrock-2023-05-31"

        client = self._client()
        try:
            response = client.invoke_model_with_response_stream(
                modelId=model,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload),
            )
        except Exception as e:
            raise Exception(f"Bedrock API error for model {model}: {e}")

        yield from self._parse_stream_events(self._iter_bedrock_events(response))

    @staticmethod
    def _iter_bedrock_events(response):
        """Yield decoded JSON events from a Bedrock response stream"""
        for event in response["body"]:
            if "chunk" in event:
                try:
                    yield json.loads(event["chunk"]["bytes"])
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
            else:
                # Exception events, e.g. throttlingException, modelStreamErrorException
                for key, value in event.items():
                    message = value.get("message", value) if isinstance(value, dict) else value
                    raise Exception(f"Bedrock stream error ({key}): {message}")


class GoogleProvider(BaseProvider):
    """Google Gemini provider using HTTP requests"""

    def validate_config(self):
        """Validate Gemini configuration"""
        if not self.config.get("api_key"):
            raise ValueError(
                "Gemini API key required. Set GEMINI_API_KEY or g:llm_agent_gemini_api_key"
            )

    def get_model(self):
        """Get the model name from config"""
        return self.config.get("model") or "gemini-2.5-flash"

    def create_messages(self, system_message, history, user_message):
        """Create messages in Gemini format"""
        # Gemini uses 'model' instead of 'assistant' for AI responses
        contents = []
        for msg in history:
            if msg.get("role") == "user":
                contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
            elif msg.get("role") == "assistant":
                contents.append({"role": "model", "parts": [{"text": msg["content"]}]})

        contents.append({"role": "user", "parts": [{"text": user_message}]})

        return {
            "system_instruction": {"parts": [{"text": system_message}]},
            "contents": contents,
        }

    def stream_chat(self, messages, model, temperature, max_tokens, tools=None):
        """Stream chat completion from Google Gemini"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={self.config['api_key']}"

        payload = {
            "systemInstruction": messages["system_instruction"],
            "contents": messages["contents"],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        response = requests.post(url, json=payload, stream=True, timeout=60)

        # Check for HTTP errors
        if response.status_code != 200:
            error_body = response.text
            raise Exception(
                f"Gemini API error (status {response.status_code}): {error_body}"
            )

        # Gemini streaming sends JSON array with one element per chunk
        # Read the raw text response
        response_text = response.text

        # Parse as JSON array
        try:
            response_data = json.loads(response_text)

            # Response is an array of chunks
            if isinstance(response_data, list):
                for item in response_data:
                    # Check for errors
                    if "error" in item:
                        raise Exception(
                            f"Gemini API error: {json.dumps(item['error'])}"
                        )

                    if "candidates" in item and item["candidates"]:
                        candidate = item["candidates"][0]
                        if "content" in candidate and "parts" in candidate["content"]:
                            for part in candidate["content"]["parts"]:
                                text = part.get("text", "")
                                if text:
                                    # Yield the full text at once
                                    yield (text, "", None)
                        finish_reason = candidate.get("finishReason", "")
                        if finish_reason:
                            if finish_reason == "STOP":
                                yield ("", "stop", None)
                            else:
                                yield ("", finish_reason, None)
            elif isinstance(response_data, dict):
                # Single object response
                if "error" in response_data:
                    raise Exception(
                        f"Gemini API error: {json.dumps(response_data['error'])}"
                    )

                if "candidates" in response_data and response_data["candidates"]:
                    candidate = response_data["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        for part in candidate["content"]["parts"]:
                            text = part.get("text", "")
                            if text:
                                yield (text, "", None)
                    finish_reason = candidate.get("finishReason", "")
                    if finish_reason:
                        if finish_reason == "STOP":
                            yield ("", "stop", None)
                        else:
                            yield ("", finish_reason, None)
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse Gemini response: {str(e)}")


class OllamaProvider(BaseProvider):
    """Ollama local provider using HTTP requests"""

    def validate_config(self):
        """Validate Ollama configuration"""
        if not self.config.get("base_url"):
            self.config["base_url"] = "http://localhost:11434"

    def get_model(self):
        """Get the model name from config"""
        return self.config.get("model") or "llama3.2"

    def create_messages(self, system_message, history, user_message):
        """Create messages in Ollama format (OpenAI-compatible)"""
        messages = [{"role": "system", "content": system_message}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def stream_chat(self, messages, model, temperature, max_tokens, tools=None):
        """Stream chat completion from Ollama"""
        url = f"{self.config['base_url']}/api/chat"

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        response = requests.post(url, json=payload, stream=True, timeout=60)

        # Check for HTTP errors
        if response.status_code != 200:
            error_body = response.text
            raise Exception(
                f"Ollama API error (status {response.status_code}): {error_body}"
            )

        for line in response.iter_lines():
            if not line:
                continue

            try:
                chunk = json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                done = chunk.get("done", False)

                if content:
                    yield (content, "", None)
                if done:
                    yield ("", "stop", None)
            except json.JSONDecodeError:
                continue


class OpenRouterProvider(BaseProvider):
    """OpenRouter provider using OpenAI-compatible HTTP API"""

    def validate_config(self):
        """Validate OpenRouter configuration"""
        if not self.config.get("api_key"):
            raise ValueError(
                "OpenRouter API key required. Set OPENROUTER_API_KEY or g:llm_agent_openrouter_api_key"
            )
        if not self.config.get("base_url"):
            self.config["base_url"] = "https://openrouter.ai/api/v1"

    def get_model(self):
        """Get the model name from config"""
        return self.config.get("model") or "anthropic/claude-3.5-sonnet"

    def create_messages(self, system_message, history, user_message):
        """Create messages in OpenAI format (OpenRouter compatible)"""
        messages = [{"role": "system", "content": system_message}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def stream_chat(self, messages, model, temperature, max_tokens, tools=None):
        """Stream chat completion from OpenRouter"""
        url = f"{self.config['base_url']}/chat/completions"

        headers = {
            "Authorization": f'Bearer {self.config["api_key"]}',
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/CoderCookE/vim-gpt",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        response = requests.post(
            url, headers=headers, json=payload, stream=True, timeout=60
        )

        # Check for HTTP errors
        if response.status_code != 200:
            error_body = response.text
            raise Exception(
                f"OpenRouter API error (status {response.status_code}): {error_body}"
            )

        # Parse Server-Sent Events stream (OpenAI-compatible)
        for line in response.iter_lines():
            if not line:
                continue

            line = line.decode("utf-8", errors="replace")
            if not line.startswith("data: "):
                continue

            data = line[6:]  # Remove 'data: ' prefix
            if data == "[DONE]":
                break

            try:
                chunk = json.loads(data)
                if "choices" in chunk and chunk["choices"]:
                    choice = chunk["choices"][0]
                    content = choice.get("delta", {}).get("content", "")
                    finish_reason = choice.get("finish_reason", "")

                    if content:
                        yield (content, "", None)
                    if finish_reason:
                        yield ("", finish_reason, None)
            except json.JSONDecodeError:
                continue


def _provider_setting(name, default=None):
    """
    Read a provider setting from g:llm_agent_{name}, falling back to the
    deprecated unprefixed g:{name} (e.g. g:anthropic_model).
    """
    return get_config(name, legacy=f"g:{name}") or default


def create_provider(provider_name):
    """Factory function to create the appropriate provider"""

    if provider_name == "anthropic":
        base_url = (
            os.getenv("ANTHROPIC_BASE_URL")
            or _provider_setting("anthropic_base_url")
            or "https://api.anthropic.com/v1"
        )
        config = {
            "api_key": os.getenv("ANTHROPIC_API_KEY")
            or _provider_setting("anthropic_api_key"),
            "model": _provider_setting("anthropic_model", "claude-sonnet-4-5-20250929"),
            "base_url": base_url,
        }
        debug_log(f"DEBUG: Creating Anthropic provider with base_url={base_url}")
        return AnthropicProvider(config)

    elif provider_name == "bedrock":
        config = {
            "model": get_config("bedrock_model"),
            "region": get_config("bedrock_region")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION"),
            "profile": get_config("bedrock_profile") or os.getenv("AWS_PROFILE"),
            "endpoint_url": get_config("bedrock_endpoint_url"),
            "access_key_id": get_config("bedrock_access_key_id"),
            "secret_access_key": get_config("bedrock_secret_access_key"),
            "session_token": get_config("bedrock_session_token"),
        }
        debug_log(
            "DEBUG: Creating Bedrock provider with "
            f"model={config['model']}, region={config['region']}, "
            f"profile={config['profile']}, endpoint_url={config['endpoint_url']}, "
            f"static_keys={'yes' if config['access_key_id'] else 'no'}"
        )
        return BedrockProvider(config)

    elif provider_name == "gemini":
        config = {
            "api_key": os.getenv("GEMINI_API_KEY") or _provider_setting("gemini_api_key"),
            "model": _provider_setting("gemini_model", "gemini-2.5-flash"),
        }
        return GoogleProvider(config)

    elif provider_name == "ollama":
        config = {
            "base_url": os.getenv("OLLAMA_HOST")
            or _provider_setting("ollama_base_url", "http://localhost:11434"),
            "model": _provider_setting("ollama_model", "llama3.2"),
        }
        return OllamaProvider(config)

    elif provider_name == "openrouter":
        config = {
            "api_key": os.getenv("OPENROUTER_API_KEY")
            or _provider_setting("openrouter_api_key"),
            "base_url": _provider_setting(
                "openrouter_base_url", "https://openrouter.ai/api/v1"
            ),
            "model": _provider_setting("openrouter_model", "anthropic/claude-3.5-sonnet"),
        }
        return OpenRouterProvider(config)

    else:  # Default to openai
        config = {
            "api_type": _provider_setting("api_type"),
            "api_key": os.getenv("OPENAI_API_KEY")
            or get_config("key")
            or _provider_setting("openai_api_key"),
            "base_url": os.getenv("OPENAI_PROXY")
            or os.getenv("OPENAI_API_BASE")
            or _provider_setting("openai_base_url"),
            "model": get_config("model", "gpt-4o"),
            # Azure-specific config
            "azure_endpoint": _provider_setting("azure_endpoint"),
            "azure_deployment": _provider_setting("azure_deployment"),
            "azure_api_version": _provider_setting("azure_api_version"),
        }
        return OpenAIProvider(config)
