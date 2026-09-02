" LLM Agent Configuration Management
" This file handles default configuration values
" 
" NOTE: The old g:chat_gpt_* naming is deprecated but still supported for backward compatibility.
" Please migrate to g:llm_agent_* naming in your .vimrc

function! chatgpt#config#setup() abort
  " Set default values for Vim variables if they don't exist
  " New naming: g:llm_agent_* (falls back to g:chat_gpt_* for compatibility)
  
  if !exists("g:llm_agent_max_tokens") && !exists("g:chat_gpt_max_tokens")
    let g:llm_agent_max_tokens = 2000
  elseif !exists("g:llm_agent_max_tokens")
    let g:llm_agent_max_tokens = g:chat_gpt_max_tokens
  endif

  if !exists("g:llm_agent_temperature") && !exists("g:chat_gpt_temperature")
    let g:llm_agent_temperature = 0.7
  elseif !exists("g:llm_agent_temperature")
    let g:llm_agent_temperature = g:chat_gpt_temperature
  endif

  if !exists("g:llm_agent_model") && !exists("g:chat_gpt_model")
    let g:llm_agent_model = 'gpt-4o'
  elseif !exists("g:llm_agent_model")
    let g:llm_agent_model = g:chat_gpt_model
  endif

  if !exists("g:llm_agent_lang") && !exists("g:chat_gpt_lang")
    let g:llm_agent_lang = v:none
  elseif !exists("g:llm_agent_lang")
    let g:llm_agent_lang = g:chat_gpt_lang
  endif

  if !exists("g:llm_agent_split_direction") && !exists("g:chat_gpt_split_direction")
    let g:llm_agent_split_direction = 'vertical'
  elseif !exists("g:llm_agent_split_direction")
    let g:llm_agent_split_direction = g:chat_gpt_split_direction
  endif

  if !exists("g:split_ratio")
    let g:split_ratio = 3
  endif

  if !exists("g:llm_agent_persona") && !exists("g:chat_gpt_persona")
    let g:llm_agent_persona = 'default'
  elseif !exists("g:llm_agent_persona")
    let g:llm_agent_persona = g:chat_gpt_persona
  endif

  " Enable tools/function calling (default: enabled for supported providers)
  if !exists("g:llm_agent_enable_tools") && !exists("g:chat_gpt_enable_tools")
    let g:llm_agent_enable_tools = 1
  elseif !exists("g:llm_agent_enable_tools")
    let g:llm_agent_enable_tools = g:chat_gpt_enable_tools
  endif

  " Require plan approval before tool execution
  if !exists("g:llm_agent_require_plan_approval") && !exists("g:chat_gpt_require_plan_approval")
    let g:llm_agent_require_plan_approval = 1
  elseif !exists("g:llm_agent_require_plan_approval")
    let g:llm_agent_require_plan_approval = g:chat_gpt_require_plan_approval
  endif

  " Require individual tool approval (prompts user for each new tool)
  if !exists("g:llm_agent_require_tool_approval") && !exists("g:chat_gpt_require_tool_approval")
    let g:llm_agent_require_tool_approval = 1
  elseif !exists("g:llm_agent_require_tool_approval")
    let g:llm_agent_require_tool_approval = g:chat_gpt_require_tool_approval
  endif

  " Session mode (persistent chat history)
  if !exists("g:llm_agent_session_mode") && !exists("g:chat_gpt_session_mode")
    let g:llm_agent_session_mode = 1
  elseif !exists("g:llm_agent_session_mode")
    let g:llm_agent_session_mode = g:chat_gpt_session_mode
  endif

  " Conversation history compaction settings
  if !exists("g:llm_agent_summary_compaction_size") && !exists("g:chat_gpt_summary_compaction_size")
    let g:llm_agent_summary_compaction_size = 76800  " 76KB
  elseif !exists("g:llm_agent_summary_compaction_size")
    let g:llm_agent_summary_compaction_size = g:chat_gpt_summary_compaction_size
  endif

  if !exists("g:llm_agent_recent_history_size") && !exists("g:chat_gpt_recent_history_size")
    let g:llm_agent_recent_history_size = 30480  " 30KB
  elseif !exists("g:llm_agent_recent_history_size")
    let g:llm_agent_recent_history_size = g:chat_gpt_recent_history_size
  endif

  " Provider selection
  if !exists("g:llm_agent_provider") && !exists("g:chat_gpt_provider")
    let g:llm_agent_provider = 'openai'
  elseif !exists("g:llm_agent_provider")
    let g:llm_agent_provider = g:chat_gpt_provider
  endif

  " Anthropic (Claude) configuration
  if !exists("g:anthropic_api_key")
    let g:anthropic_api_key = ''
  endif

  if !exists("g:anthropic_model")
    let g:anthropic_model = 'claude-sonnet-4-5-20250929'
  endif

  if !exists("g:anthropic_base_url")
    let g:anthropic_base_url = 'https://api.anthropic.com/v1'
  endif

  " Gemini (Google) configuration
  if !exists("g:gemini_api_key")
    let g:gemini_api_key = ''
  endif

  if !exists("g:gemini_model")
    let g:gemini_model = 'gemini-2.5-flash'
  endif

  " Ollama configuration
  if !exists("g:ollama_base_url")
    let g:ollama_base_url = 'http://localhost:11434'
  endif

  if !exists("g:ollama_model")
    let g:ollama_model = 'llama3.2'
  endif

  " OpenRouter configuration
  if !exists("g:openrouter_api_key")
    let g:openrouter_api_key = ''
  endif

  if !exists("g:openrouter_model")
    let g:openrouter_model = 'anthropic/claude-3.5-sonnet'
  endif

  if !exists("g:openrouter_base_url")
    let g:openrouter_base_url = 'https://openrouter.ai/api/v1'
  endif

  " Debug logging level (0=off, 1=basic, 2=verbose)
  if !exists("g:llm_agent_log_level") && !exists("g:chat_gpt_log_level")
    let g:llm_agent_log_level = 0
  elseif !exists("g:llm_agent_log_level")
    let g:llm_agent_log_level = g:chat_gpt_log_level
  endif

  " Suppress display (for programmatic usage)
  if !exists("g:llm_agent_suppress_display") && !exists("g:chat_gpt_suppress_display")
    let g:llm_agent_suppress_display = 0
  elseif !exists("g:llm_agent_suppress_display")
    let g:llm_agent_suppress_display = g:chat_gpt_suppress_display
  endif

  " Prompt templates (backward compatibility: check both old and new custom prompts)
  let code_wrapper_snippet = "Given the following code snippet: "
  let g:prompt_templates = {
  \ 'ask': '',
  \ 'rewrite': 'Can you rewrite this more idiomatically? ' . code_wrapper_snippet,
  \ 'review': 'Can you provide a code review? ' . code_wrapper_snippet,
  \ 'document': 'Return documentation following language pattern conventions. ' . code_wrapper_snippet,
  \ 'explain': 'Can you explain how this works? ' . code_wrapper_snippet,
  \ 'test': 'Can you write a test? ' . code_wrapper_snippet,
  \ 'fix':  'I have an error I need you to fix. ' . code_wrapper_snippet,
  \}

  if exists('g:llm_agent_custom_prompts')
    call extend(g:prompt_templates, g:llm_agent_custom_prompts)
  elseif exists('g:chat_gpt_custom_prompts')
    call extend(g:prompt_templates, g:chat_gpt_custom_prompts)
  endif

  let g:promptKeys = keys(g:prompt_templates)

  " Personas (backward compatibility: check both old and new custom personas)
  let g:gpt_personas = {
  \ "default": 'You are a helpful expert programmer we are working together to solve complex coding challenges, and I need your help. Please make sure to wrap all code blocks in ``` annotate the programming language you are using.',
  \}

  if exists('g:llm_agent_custom_persona')
    call extend(g:gpt_personas, g:llm_agent_custom_persona)
  elseif exists('g:chat_gpt_custom_persona')
    call extend(g:gpt_personas, g:chat_gpt_custom_persona)
  endif

  " Set up Python path once at plugin load so all heredocs can import chatgpt.*
  call chatgpt#ensure_python_path()
endfunction
