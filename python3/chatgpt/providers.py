"""
AI Provider abstraction layer for multi-provider support

This module provides a unified interface for interacting with different LLM providers
including OpenAI, Anthropic (Claude), Google (Gemini), Ollama, and OpenRouter.
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
                "OpenAI API key required. Set OPENAI_API_KEY or g:openai_api_key"
            )

        # Validate Azure-specific config if using Azure
        if self.config.get("api_type") == "azure":
            if not self.config.get("azure_endpoint"):
                raise ValueError("Azure endpoint required. Set g:azure_endpoint")
            if not self.config.get("azure_deployment"):
                raise ValueError("Azure deployment required. Set g:azure_deployment")
            if not self.config.get("azure_api_version"):
                raise ValueError("Azure API version required. Set g:azure_api_version")

    def get_model(self):
        """Get the model name from config"""
        return self.config.get("model", "gpt-4o")

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

    def validate_config(self):
        """Validate Anthropic configuration"""
        if not self.config.get("api_key"):
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY or g:anthropic_api_key"
            )

    def get_model(self):
        """Get the model name from config"""
        return self.config.get("model", "claude-sonnet-4-5-20250929")

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

    def stream_chat(self, messages, model, temperature, max_tokens, tools=None):
        """Stream chat completion from Anthropic"""
        import sys

        # Validate messages format
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

        debug_log(
            f"DEBUG: Anthropic stream_chat called with {len(messages['messages'])} messages"
        )

        headers = {
            "x-api-key": self.config["api_key"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": messages["system"],
            "messages": messages["messages"],
            "stream": True,
        }

        # Add tools if provided
        if tools:
            formatted = self.format_tools_for_api(tools)
            payload["tools"] = formatted
            debug_log(f"INFO: Sending {len(formatted)} tools to Anthropic API")
            debug_log(f"DEBUG: Tool names being sent: {[t['name'] for t in formatted]}")
        else:
            debug_log(f"WARNING: No tools being sent to Anthropic API")

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

        # Parse Server-Sent Events stream
        tool_use_blocks = {}  # Accumulate tool use blocks

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
                                    if not tool_input:
                                        arguments = {}
                                    else:
                                        arguments = json.loads(tool_input)

                                    tool_calls.append(
                                        {
                                            "id": tool_data["id"],
                                            "name": tool_data["name"],
                                            "arguments": arguments,
                                        }
                                    )
                                except json.JSONDecodeError as e:
                                    pass  # Skip malformed tool calls
                        yield ("", finish_reason, tool_calls)
            except json.JSONDecodeError:
                continue


class GoogleProvider(BaseProvider):
    """Google Gemini provider using HTTP requests"""

    def validate_config(self):
        """Validate Gemini configuration"""
        if not self.config.get("api_key"):
            raise ValueError(
                "Gemini API key required. Set GEMINI_API_KEY or g:gemini_api_key"
            )

    def get_model(self):
        """Get the model name from config"""
        return self.config.get("model", "gemini-2.5-flash")

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
        return self.config.get("model", "llama3.2")

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
                "OpenRouter API key required. Set OPENROUTER_API_KEY or g:openrouter_api_key"
            )
        if not self.config.get("base_url"):
            self.config["base_url"] = "https://openrouter.ai/api/v1"

    def get_model(self):
        """Get the model name from config"""
        return self.config.get("model", "anthropic/claude-3.5-sonnet")

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


def create_provider(provider_name):
    """Factory function to create the appropriate provider"""

    if provider_name == "anthropic":
        base_url = os.getenv("ANTHROPIC_BASE_URL") or get_config("anthropic_base_url")
        if not base_url:
            # Fallback to default if not set
            base_url = "https://api.anthropic.com/v1"
        config = {
            "api_key": os.getenv("ANTHROPIC_API_KEY")
            or get_config("anthropic_api_key"),
            "model": get_config("anthropic_model") or "claude-sonnet-4-5-20250929",
            "base_url": base_url,
        }
        debug_log(f"DEBUG: Creating Anthropic provider with base_url={base_url}")
        return AnthropicProvider(config)

    elif provider_name == "gemini":
        config = {
            "api_key": os.getenv("GEMINI_API_KEY") or get_config("gemini_api_key"),
            "model": get_config("gemini_model"),
        }
        return GoogleProvider(config)

    elif provider_name == "ollama":
        config = {
            "base_url": os.getenv("OLLAMA_HOST") or get_config("ollama_base_url"),
            "model": get_config("ollama_model"),
        }
        return OllamaProvider(config)

    elif provider_name == "openrouter":
        config = {
            "api_key": os.getenv("OPENROUTER_API_KEY")
            or get_config("openrouter_api_key"),
            "base_url": get_config("openrouter_base_url"),
            "model": get_config("openrouter_model"),
        }
        return OpenRouterProvider(config)

    else:  # Default to openai
        config = {
            "api_type": get_config("api_type"),
            "api_key": os.getenv("OPENAI_API_KEY")
            or get_config("key")
            or get_config("openai_api_key"),
            "base_url": os.getenv("OPENAI_PROXY")
            or os.getenv("OPENAI_API_BASE")
            or get_config("openai_base_url"),
            "model": get_config("model"),
            # Azure-specific config
            "azure_endpoint": get_config("azure_endpoint"),
            "azure_deployment": get_config("azure_deployment"),
            "azure_api_version": get_config("azure_api_version"),
        }
        return OpenAIProvider(config)
