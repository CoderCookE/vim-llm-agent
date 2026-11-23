# Migration Guide: vim-chatgpt → vim-llm-agent

## Overview

This plugin has been renamed from `vim-chatgpt` to `vim-llm-agent` to better reflect its capabilities as a full-featured LLM agent supporting multiple providers (OpenAI, Anthropic, AWS Bedrock, Google, Ollama, OpenRouter).

**Full backwards compatibility is maintained** - all old configuration variables and directory names continue to work.

## What Changed

### Repository Name
- **Old:** `vim-chatgpt`
- **New:** `vim-llm-agent`

### Configuration Variables
All configuration variables now use the `g:llm_agent_` prefix, but **old `g:chat_gpt_` variables still work as fallbacks**.

| Old Variable | New Variable | Description |
|-------------|--------------|-------------|
| `g:chat_gpt_key` | `g:llm_agent_key` | API key for OpenAI / Azure OpenAI |
| `g:chat_gpt_model` | `g:llm_agent_model` | Model to use (OpenAI) |
| `g:chat_gpt_provider` | `g:llm_agent_provider` | Provider (openai, anthropic, etc.) |
| `g:chat_gpt_max_tokens` | `g:llm_agent_max_tokens` | Max tokens in response |
| `g:chat_gpt_temperature` | `g:llm_agent_temperature` | Sampling temperature |
| `g:chat_gpt_session_mode` | `g:llm_agent_session_mode` | Enable persistent sessions |
| `g:chat_gpt_enable_tools` | `g:llm_agent_enable_tools` | Enable tool execution |
| `g:chat_gpt_require_plan_approval` | `g:llm_agent_require_plan_approval` | Require plan approval |
| `g:chat_gpt_require_tool_approval` | `g:llm_agent_require_tool_approval` | Require tool approval |
| `g:chat_gpt_log_level` | `g:llm_agent_log_level` | Logging verbosity |
| `g:chat_gpt_recent_history_size` | `g:llm_agent_recent_history_size` | Recent history window size |

### Provider Variables

Provider-specific settings now use `g:llm_agent_<provider>_<setting>`. The old unprefixed names still work as a fallback, but are **deprecated**: the first time one is used in a session, Vim shows a warning naming its replacement. Environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.) are unchanged and still take precedence.

| Deprecated Variable | New Variable |
|---------------------|--------------|
| `g:openai_api_key` | `g:llm_agent_openai_api_key` |
| `g:openai_base_url` | `g:llm_agent_openai_base_url` |
| `g:api_type` | `g:llm_agent_api_type` |
| `g:azure_endpoint` | `g:llm_agent_azure_endpoint` |
| `g:azure_deployment` | `g:llm_agent_azure_deployment` |
| `g:azure_api_version` | `g:llm_agent_azure_api_version` |
| `g:anthropic_api_key` | `g:llm_agent_anthropic_api_key` |
| `g:anthropic_model` | `g:llm_agent_anthropic_model` |
| `g:anthropic_base_url` | `g:llm_agent_anthropic_base_url` |
| `g:gemini_api_key` | `g:llm_agent_gemini_api_key` |
| `g:gemini_model` | `g:llm_agent_gemini_model` |
| `g:ollama_base_url` | `g:llm_agent_ollama_base_url` |
| `g:ollama_model` | `g:llm_agent_ollama_model` |
| `g:openrouter_api_key` | `g:llm_agent_openrouter_api_key` |
| `g:openrouter_model` | `g:llm_agent_openrouter_model` |
| `g:openrouter_base_url` | `g:llm_agent_openrouter_base_url` |

The Bedrock provider only uses the new style (`g:llm_agent_bedrock_model`, `g:llm_agent_bedrock_region`, `g:llm_agent_bedrock_profile`, `g:llm_agent_bedrock_endpoint_url`, `g:llm_agent_bedrock_access_key_id`, `g:llm_agent_bedrock_secret_access_key`, `g:llm_agent_bedrock_session_token`).

### Project Directory
- **Old:** `.vim-chatgpt/`
- **New:** `.vim-llm-agent/`
- **Fallback:** If `.vim-chatgpt/` exists, it will be used automatically

### Commands
All commands remain unchanged and continue to work:

| Command | Description |
|---------|-------------|
| `:Ask` | Main chat interface |
| `:GenerateCommit` | Generate git commit message |
| `:GptGenerateContext` | Generate project context |
| `:GptGenerateSummary` | Generate conversation summary |
| `:GptBe` | Set agent persona |

**Note:** The `Gpt` prefix in commands is kept for backwards compatibility and brevity.

## Migration Options

### Option 1: No Changes Required (Recommended)
Your existing configuration continues to work. No action needed.

```vim
" This continues to work indefinitely
let g:chat_gpt_api_key = $OPENAI_API_KEY
let g:chat_gpt_model = 'gpt-4'
```

### Option 2: Gradual Migration
Update variables at your own pace. Mix and match old and new:

```vim
" Mix old and new - both work
let g:llm_agent_key = $OPENAI_API_KEY
let g:chat_gpt_model = 'gpt-4o'
```

### Option 3: Full Migration
Update all variables to new names:

```vim
" New configuration style - FULLY SUPPORTED variables
let g:llm_agent_provider = 'anthropic'        " ✅ Supported
let g:llm_agent_anthropic_model = 'claude-sonnet-4-5-20250929'  " ✅ Supported
let g:llm_agent_anthropic_api_key = $ANTHROPIC_API_KEY          " ✅ Supported
let g:llm_agent_max_tokens = 8192            " ✅ Supported
let g:llm_agent_temperature = 0.7            " ✅ Supported
let g:llm_agent_lang = 'Spanish'             " ✅ Supported
let g:llm_agent_log_level = 2                " ✅ Supported
let g:llm_agent_recent_history_size = 30480  " ✅ Supported
let g:llm_agent_enable_tools = 1             " ✅ Supported
let g:llm_agent_require_plan_approval = 1    " ✅ Supported
let g:llm_agent_session_mode = 1             " ✅ Supported
let g:llm_agent_suppress_display = 0         " ✅ Supported
```

## Project Directory Migration

### Automatic Migration
The plugin automatically handles directory migration:

1. First checks for `.vim-llm-agent/`
2. Falls back to `.vim-chatgpt/` if it exists
3. Creates `.vim-llm-agent/` for new projects

### Manual Migration (Optional)
To migrate your existing project data:

```bash
# In your project directory
mv .vim-chatgpt .vim-llm-agent
```

Or keep using `.vim-chatgpt/` - it will continue to work.

## Installation

### Update Plugin Manager Config

**vim-plug:**
```vim
" Old
Plug 'username/vim-chatgpt'

" New
Plug 'username/vim-llm-agent'
```

**Vundle:**
```vim
" Old
Plugin 'username/vim-chatgpt'

" New
Plugin 'username/vim-llm-agent'
```

**Pathogen:**
```bash
# Old
cd ~/.vim/bundle
git clone https://github.com/username/vim-chatgpt.git

# New
cd ~/.vim/bundle
mv vim-chatgpt vim-llm-agent
cd vim-llm-agent
git remote set-url origin https://github.com/username/vim-llm-agent.git
```

## Deprecation Timeline

**No removal planned.** The old `g:chat_gpt_*` variable names and the `.vim-chatgpt/` directory will continue to work indefinitely to ensure backwards compatibility.

The unprefixed provider variables listed under [Provider Variables](#provider-variables) (`g:anthropic_model`, `g:openai_api_key`, etc.) are deprecated: they still work today, but show a warning and may be removed in a future release.

## Questions?

If you have any issues with the migration, please open an issue on GitHub.
