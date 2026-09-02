"""
Main chat logic for the ChatGPT Vim Plugin

This module contains the core chat_gpt() function that handles:
- Provider initialization
- Message history management
- Tool calling workflow
- Plan approval workflow
- Streaming responses
"""

import os
import json
import re
import vim

from chatgpt.utils import (
    debug_log,
    format_separator,
    format_tool_result,
    clear_plan,
    load_plan,
    get_config,
    parse_conversation_history,
)
from chatgpt.providers import create_provider
from chatgpt.tools import get_tool_definitions, execute_tool


def _display_response(content, finish_reason, session_id):
    """Pass display content via vim.vars to avoid VimScript string-escaping issues."""
    vim.vars["_llm_display_content"] = content
    vim.vars["_llm_display_finish"] = finish_reason
    vim.command(
        "call DisplayChatGPTResponse("
        "g:_llm_display_content, g:_llm_display_finish, "
        "'{0}')".format(session_id.replace("'", "''"))
    )


def is_plan_completed(response_text):
    """
    Detect if the AI's response indicates plan completion.

    Looks for completion indicators like:
    - "Goal achieved"
    - "Plan completed"
    - "All steps complete"
    - Phase 3: COMPLETION sections

    Args:
        response_text: The AI's response text

    Returns:
        bool: True if completion indicators found
    """
    completion_patterns = [
        r"goal\s+(has\s+been\s+)?achieved",
        r"plan\s+(has\s+been\s+)?completed",
        r"all\s+steps\s+(are\s+)?complete",
        r"phase\s+3:\s*completion",
        r"✅.*complete",
        r"successfully\s+completed\s+all",
        r"finished\s+(all\s+)?steps",
    ]

    text_lower = response_text.lower()
    for pattern in completion_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True

    return False


def chat_gpt(prompt, silent=False):
    """Main chat function that handles conversation with AI providers
    
    Args:
        prompt: The user's prompt/question
        silent: If True, suppress all display output (for background operations)
    """

    # Log minimal info for debugging
    debug_log(f"INFO: chat_gpt called - prompt length: {len(prompt)}, silent={silent}")

    token_limits = {
        "gpt-3.5-turbo": 4097,
        "gpt-3.5-turbo-16k": 16385,
        "gpt-3.5-turbo-1106": 16385,
        "gpt-4": 8192,
        "gpt-4-turbo": 128000,
        "gpt-4-turbo-preview": 128000,
        "gpt-4-32k": 32768,
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "o1": 200000,
        "o3": 200000,
        "o3-mini": 200000,
        "o4-mini": 200000,
    }

    # Get provider
    provider_name = get_config("provider", "openai")

    try:
        provider = create_provider(provider_name)
    except Exception as e:
        print(f"Error creating provider '{provider_name}': {str(e)}")
        return

    # Get parameters
    max_tokens = int(get_config("max_tokens", "2000"))
    temperature = float(get_config("temperature", "0.7"))
    lang = get_config("lang", "None")
    resp = f" And respond in {lang}." if lang != "None" else ""
    # Use silent parameter if provided, otherwise check config
    suppress_display = 1 if silent else int(get_config("suppress_display", "0"))

    # Get model from provider
    # Get model from provider
    model = provider.get_model()

    # Build system message with persona
    personas = vim.eval("g:gpt_personas")  # Keep this as vim.eval since it's a dict
    persona = get_config("persona", "default")

    # Get the persona's system prompt
    persona_prompt = personas.get(persona, personas.get("default", ""))
    system_message = persona_prompt

    enable_tools = int(get_config("enable_tools", "1"))
    if enable_tools and provider.supports_tools():
        system_message += "\n\nCRITICAL: You have function/tool calling capability via the API. When you need to use a tool, you MUST use the API's native tool calling feature. NEVER write text that describes or mimics tool usage. The system handles all tool execution automatically.\n\n"

    # Load project context if available
    from chatgpt.utils import get_project_dir

    project_dir = get_project_dir()
    context_file = os.path.join(project_dir, "context.md")
    if os.path.exists(context_file):
        try:
            with open(context_file, "r", encoding="utf-8") as f:
                project_context = f.read().strip()
                if project_context:
                    system_message += f"\n\n## Project Context\n\n{project_context}"
        except Exception as e:
            # Silently ignore errors reading context file
            pass

    # Load conversation summary if available and extract cutoff position
    summary_file = os.path.join(project_dir, "summary.md")
    summary_cutoff_byte = 0
    if os.path.exists(summary_file):
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                conversation_summary = f.read().strip()

                # Extract cutoff_byte from metadata if present
                cutoff_match = re.search(r"cutoff_byte:\s*(\d+)", conversation_summary)
                if cutoff_match:
                    summary_cutoff_byte = int(cutoff_match.group(1))

                if conversation_summary:
                    system_message += f"\n\n## Conversation Summary & User Preferences\n\n{conversation_summary}"
        except Exception as e:
            # Silently ignore errors reading summary file
            pass

    # Load active plan if available
    from chatgpt.utils import load_plan

    active_plan = load_plan()
    if active_plan:
        system_message += f"\n\n## Current Active Plan\n\nYou previously created and the user approved this plan. Continue executing it:\n\n{active_plan}"

    # Add planning instruction if tools are enabled and plan approval required
    # In silent mode, disable all approvals to run in background
    require_plan_approval = 0 if silent else int(get_config("require_plan_approval", "1"))
    if enable_tools and provider.supports_tools():
        # Add tool calling capability instructions
        system_message += "\n\n## TOOL CALLING CAPABILITY\n\nYou have access to function/tool calling via the API. Tools are available through the native tool calling feature.\n\nIMPORTANT: When executing tools:\n- Use the API's tool/function calling feature (NOT text descriptions)\n- Do NOT write text that mimics tool execution like 'Success: git_status()'\n- Do NOT output text like 'Tool Execution' or 'Calling tool: X'\n- The system automatically handles and displays tool execution\n- Your job is to CALL the tools via the API, not describe them in text\n"

        if require_plan_approval:
            # Add planning workflow only when plan approval is required
            system_message += """
## AGENT WORKFLOW

You are an agentic assistant that follows a structured workflow:

### PHASE 1: PLANNING (when you receive a new user request)
1. Analyze the user's intention - what is their goal?
2. Create a detailed plan to achieve that goal
3. Identify which tools (if any) are needed
4. Present the plan in this EXACT format:

```
GOAL: [Clear statement of what we're trying to achieve]

PLAN:
1. [First step - include tool name if needed, e.g., "Check repository status (git_status)"]
2. [Second step - e.g., "Review changes (git_diff with staged=false)"]
3. [Continue with all steps...]

TOOLS REQUIRED: [List tool names: git_status, git_diff, git_commit, etc.]

ESTIMATED STEPS: [Number]
```

5. CRITICAL: Present ONLY the plan text - do NOT call any tools yet
6. Wait for user approval

### PHASE 2: EXECUTION (after plan approval)
When user approves the plan with a message like "Plan approved. Please proceed":
1. IMMEDIATELY use your tool calling API capability - do NOT write any text or descriptions
2. DO NOT output ANY text like: "Tool Execution", "======", "Step 1:", "Checking status", or descriptions of what you're doing
3. Your response must contain ONLY function/tool calls using the tool calling feature - NO text content
4. After each tool execution completes and you see the results, evaluate: "Do the results change the plan?"
5. If plan needs revision:
   - Present a REVISED PLAN using the same format
   - Mark it with "REVISED PLAN" at the top
   - Explain what changed and why
   - Wait for user approval
6. If plan is on track: make the NEXT tool call (again, ONLY tool calls, NO text)
7. Continue until all steps complete

### PHASE 3: COMPLETION
1. Confirm the goal has been achieved
2. Summarize what was done

CRITICAL EXECUTION RULES:
- ALWAYS start with PLANNING phase for new requests
- NEVER execute tools before showing a plan
- When executing: Your response must be ONLY tool calls, ZERO text content
- The system automatically displays tool execution progress - you must NOT output any text
"""
    else:
        # Direct execution mode - no planning workflow
        system_message += '\n## DIRECT EXECUTION MODE\n\n**CRITICAL INSTRUCTIONS:**\n- Plan approval is DISABLED\n- DO NOT present plans, goals, or explain what you will do\n- DO NOT write ANY text describing your actions\n- Your FIRST response must contain ONLY tool/function calls, ZERO text\n- Execute the user\'s request IMMEDIATELY using the appropriate tools\n- After tools complete, you may provide a brief summary of results\n\n**EXECUTION RULES:**\n- IMMEDIATELY call the required tools via the API\n- Do NOT output text like "Let me create..." or "I\'ll start by..."\n- The system handles all tool execution display\n- Just make the function calls and nothing else\n'

    # Session history management
    # In silent mode, disable session to avoid chat window
    history = []
    session_enabled = False if silent else (int(get_config("session_mode", "1")) == 1)
    session_mode_val = get_config("session_mode", "1")
    debug_log(
        f"DEBUG: session_enabled = {session_enabled}, g:chat_gpt_session_mode = {session_mode_val}, silent={silent}"
    )

    # Create project directory if it doesn't exist
    if session_enabled and not os.path.exists(project_dir):
        try:
            os.makedirs(project_dir)
        except:
            pass

    # Use file-based history
    history_file = os.path.join(project_dir, "history.txt") if session_enabled else None
    session_id = "gpt-persistent-session" if session_enabled else None

    # Load history from file
    debug_log(
        f"DEBUG: history_file = {history_file}, exists = {os.path.exists(history_file) if history_file else 'N/A'}"
    )
    if history_file and os.path.exists(history_file):
        debug_log(f"INFO: Loading history from {history_file}")
        try:
            # Read only from cutoff position onwards (recent uncompressed history)
            # Use binary mode with explicit decode to handle UTF-8 seek issues
            with open(history_file, "rb") as f:
                if summary_cutoff_byte > 0:
                    f.seek(summary_cutoff_byte)
                history_bytes = f.read()
                # Decode with error handling for potential mid-character seek
                history_content = history_bytes.decode("utf-8", errors="ignore")

            # Parse history using shared utility function
            parsed_messages = parse_conversation_history(history_content)

            # Always include last 4 messages (to maintain conversation context even after compaction)
            # Note: parsed_messages is in chronological order (oldest first)
            min_messages = 4
            if len(parsed_messages) >= min_messages:
                # Take last 4 messages (newest 4)
                history = parsed_messages[-min_messages:]
                remaining_messages = parsed_messages[:-min_messages]  # Older messages
            else:
                # Take all messages if less than min_messages
                history = parsed_messages[:]
                remaining_messages = []

            # Calculate remaining token budget after including last min_messages
            token_count = (
                token_limits.get(model, 100000)
                - max_tokens
                - len(prompt)
                - len(system_message)
            )
            for msg in history:
                token_count -= len(msg["content"])

            # Add older messages (from recent history window) until token limit
            # remaining_messages is in chronological order (oldest first)
            # We iterate through it in reverse and insert newer messages at the end of history
            for msg in reversed(remaining_messages):
                token_count -= len(msg["content"])
                if token_count > 0:
                    history.insert(
                        0, msg
                    )  # Insert at beginning to maintain chronological order
                else:
                    break
        except Exception as e:
            # Silently ignore errors reading history
            pass

    # Display initial prompt in session
    if session_id and not suppress_display:
        content = "\n\n\x01>>>User:\x01\n" + prompt + "\n\n\x01>>>Assistant:\x01\n"

        _display_response(content, "", session_id)
        vim.command("redraw")

    # Create messages using provider
    debug_log(f"DEBUG: Creating messages with {len(history)} history messages")
    if history:
        debug_log(
            f"DEBUG: Last history message: {history[-1]['role']}: {history[-1]['content'][:100]}"
        )
    try:
        messages = provider.create_messages(system_message, history, prompt)
    except Exception as e:
        print(f"Error creating messages: {str(e)}")
        return

    # Get tools if enabled and provider supports them
    tools = None
    enable_tools = int(get_config("enable_tools", "1"))
    if enable_tools and provider.supports_tools():
        tools = get_tool_definitions()
        debug_log(f"INFO: Tools enabled - {len(tools)} tools available")
        debug_log(f"DEBUG: Available tools: {[t['name'] for t in tools]}")
    else:
        debug_log(
            f"WARNING: Tools not enabled - enable_tools={enable_tools}, supports_tools={provider.supports_tools()}"
        )

    # Stream response using provider (with tool calling loop)
    try:
        chunk_session_id = session_id if session_id else "gpt-response"
        max_tool_iterations = 25  # Maximum total iterations
        tool_iteration = 0
        plan_approved = not require_plan_approval  # Skip approval if not required
        accumulated_content = ""  # Accumulate content for each iteration
        in_planning_phase = (
            require_plan_approval  # Only enter planning phase if approval is required
        )
        plan_loop_count = (
            0  # Track how many times we've seen a plan without tool execution
        )

        while tool_iteration < max_tool_iterations:
            tool_calls_to_process = None
            accumulated_content = ""  # Reset for each iteration

            chunk_count = 0
            for content, finish_reason, tool_calls in provider.stream_chat(
                messages, model, temperature, max_tokens, tools
            ):
                chunk_count += 1
                # Display content as it streams
                if content:
                    # Accumulate content to detect plan revisions
                    accumulated_content += content

                    if not suppress_display:
                        _display_response(content, "", chunk_session_id)
                        vim.command("redraw")

                # Handle finish
                if finish_reason:
                    if tool_calls:
                        debug_log(
                            f"INFO: Model requested {len(tool_calls)} tool call(s)"
                        )
                        for idx, tc in enumerate(tool_calls):
                            debug_log(
                                f"DEBUG: Tool call {idx+1}: {tc['name']} with args: {json.dumps(tc['arguments'])}"
                            )
                        tool_calls_to_process = tool_calls

                    if not suppress_display:
                        _display_response("", finish_reason, chunk_session_id)
                        vim.command("redraw")

            # If no tool calls, check if this is a planning response
            if not tool_calls_to_process:
                debug_log(f"INFO: No tool calls received from model")
                debug_log(f"DEBUG: Checking for plan presentation...")
                debug_log(
                    f"DEBUG:   accumulated_content length: {len(accumulated_content)}"
                )
                debug_log(f"DEBUG:   require_plan_approval: {require_plan_approval}")
                debug_log(f"DEBUG:   in_planning_phase: {in_planning_phase}")

                # Check if this is a plan presentation (contains goal/plan markers)
                has_text_markers = (
                    "GOAL:" in accumulated_content and "PLAN:" in accumulated_content
                )
                is_plan_presentation = has_text_markers
                debug_log(f"  is_plan_presentation: {is_plan_presentation}")
                debug_log(f"  Content preview: {accumulated_content[:300]}")

                if is_plan_presentation and require_plan_approval and in_planning_phase:
                    # Increment loop counter to detect infinite loops
                    plan_loop_count += 1
                    debug_log(
                        f"INFO: Plan presentation detected (loop count: {plan_loop_count}, in_planning_phase: {in_planning_phase})"
                    )
                    debug_log(
                        f"INFO: Full content that triggered detection:\n{accumulated_content}"
                    )

                    # Safeguard against infinite loops
                    if plan_loop_count > 2:
                        error_msg = "\n\nL ERROR: Model keeps presenting plans without executing. Please try rephrasing your request or disable plan approval.\n"
                        _display_response(error_msg, "", chunk_session_id)
                        break

                    # Verify this is actually a valid plan before asking for approval
                    # A valid plan should have multiple steps
                    has_numbered_steps = bool(
                        re.search(r"\d+\.\s+", accumulated_content)
                    )
                    if not has_numbered_steps:
                        debug_log(
                            f"  WARNING: Detected plan markers but no numbered steps found. Treating as regular response."
                        )
                        # Not a real plan, just continue
                        break

                    # IMPORTANT: Add the assistant's plan response to conversation history
                    # so the model has context when we send the approval message
                    if provider_name == "anthropic" and isinstance(messages, dict):
                        messages["messages"].append(
                            {
                                "role": "assistant",
                                "content": [
                                    {"type": "text", "text": accumulated_content}
                                ],
                            }
                        )
                    elif isinstance(messages, list):
                        messages.append(
                            {"role": "assistant", "content": accumulated_content}
                        )

                    # Ask for approval
                    if not suppress_display:
                        approval_prompt_msg = "\n\n" + "=" * 70 + "\n"
                        approval_prompt_msg += "Plan presented above.\n"
                        _display_response(approval_prompt_msg, "", chunk_session_id)
                        vim.command("redraw!")

                        # Use inputlist() for better input handling
                        approval_choice = int(
                            vim.eval(
                                "inputlist(['', 'Select an option:', '1. Approve and proceed', '2. Cancel plan', '3. Request revisions', '', 'Enter number (1-3): '])"
                            )
                        )

                        if (
                            approval_choice == 2 or approval_choice == 0
                        ):  # 2 = Cancel, 0 = ESC
                            cancel_msg = "\n\nL Plan cancelled by user.\n"
                            _display_response(cancel_msg, "", chunk_session_id)
                            break
                        elif approval_choice == 3:  # 3 = Request revisions
                            revise_msg = "\n\n= User requested plan revision.\n"
                            _display_response(revise_msg, "", chunk_session_id)
                            revision_request = vim.eval(
                                "input('What changes would you like? ')"
                            )

                            # Exit planning phase - revised plan will be detected separately
                            in_planning_phase = False

                            # Send revision request back to model - handle all provider formats
                            # Note: Assistant message with plan was already added above
                            if provider_name == "anthropic" and isinstance(
                                messages, dict
                            ):
                                messages["messages"].append(
                                    {
                                        "role": "user",
                                        "content": f"Please present a REVISED PLAN based on this feedback: {revision_request}\n\nMark it clearly with '= REVISED PLAN' at the top.",
                                    }
                                )
                            elif isinstance(messages, list):
                                # OpenAI, Gemini, Ollama format
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": f"Please present a REVISED PLAN based on this feedback: {revision_request}\n\nMark it clearly with '= REVISED PLAN' at the top.",
                                    }
                                )

                            continue  # Go to next iteration with revision request
                        else:  # approval_choice == 1 (Approve and proceed)
                            # Approved - proceed with execution
                            plan_approved = True
                            in_planning_phase = False

                            # Save the approved plan to disk so it persists across compactions
                            from chatgpt.utils import save_plan

                            save_plan(accumulated_content)
                            approval_msg = (
                                "\n\n Plan approved! Proceeding with execution...\n\n"
                            )
                            _display_response(approval_msg, "", chunk_session_id)

                            # Send approval message to model to trigger execution - handle all provider formats
                            approval_instruction = "Plan approved. Execute step 1 now.\n\nCRITICAL INSTRUCTIONS:\n- Your response must contain ONLY the tool/function call for step 1\n- Do NOT write ANY text content in your response\n- Do NOT output headers like 'Tool Execution' or '======' or 'Step 1:'\n- The system will automatically display the tool execution progress\n- Just make the actual API function call and nothing else\n- After the tool completes, you'll see the results and can proceed to the next step"

                            if provider_name == "anthropic" and isinstance(
                                messages, dict
                            ):
                                messages["messages"].append(
                                    {"role": "user", "content": approval_instruction}
                                )
                            elif isinstance(messages, list):
                                # OpenAI, Gemini, Ollama format
                                messages.append(
                                    {"role": "user", "content": approval_instruction}
                                )

                            continue  # Go to next iteration to start execution
                else:
                    # No tool calls and not a plan - conversation is done
                    debug_log(
                        f"INFO: No tool calls and not a plan presentation. Ending conversation loop."
                    )
                    debug_log(f"DEBUG: Breaking from main loop - conversation complete")

                    # Check if plan was completed and clear it
                    if accumulated_content and is_plan_completed(accumulated_content):
                        clear_plan()
                        debug_log("INFO: Plan completed - plan file deleted")

                    break

            # Check if model is presenting a revised plan during execution
            # Only check this if we're NOT in planning phase (to avoid double-asking)
            # and if there are tool calls to process (model is actually making changes)
            is_revised_plan = (
                "= REVISED PLAN" in accumulated_content
                or "=== REVISED PLAN ===" in accumulated_content
                or ("REVISED PLAN" in accumulated_content and not in_planning_phase)
            )

            # If revised plan is detected with tool calls, ask for approval
            # Skip if we already asked during planning phase
            if (
                is_revised_plan
                and require_plan_approval
                and not suppress_display
                and tool_calls_to_process
                and not in_planning_phase
            ):

                # Show the revised plan header
                revised_plan_header = "\n\n" + "=" * 70 + "\n"
                revised_plan_header += (
                    "= The agent has proposed a REVISED PLAN based on the results.\n"
                )
                revised_plan_header += "=" * 70 + "\n"
                _display_response(revised_plan_header, "", chunk_session_id)

                # Ask for approval
                vim.command("redraw!")
                vim.command("sleep 100m")
                vim.command("redraw!")

                approval = vim.eval(
                    "input('Approve revised plan? [y]es to proceed, [n]o to cancel: ')"
                )

                if approval.lower() not in ["y", "yes"]:
                    cancel_msg = "\n\nL Revised plan cancelled by user.\n"
                    _display_response(cancel_msg, "", chunk_session_id)
                    break

                # Approved - continue execution
                approval_msg = (
                    "\n\n Revised plan approved! Continuing execution...\n\n"
                )
                _display_response(approval_msg, "", chunk_session_id)

            # Execute tools and add results to messages
            tool_iteration += 1
            debug_log(
                f"INFO: Starting tool execution iteration {tool_iteration}/{max_tool_iterations}"
            )
            debug_log(
                f"DEBUG: Processing {len(tool_calls_to_process) if tool_calls_to_process else 0} tool calls"
            )

            if not suppress_display:
                # Display iteration header with formatting
                iteration_msg = (
                    "\n\n"
                    + format_separator("=", 70)
                    + f"\nTool Execution - Iteration {tool_iteration}\n"
                    + format_separator("=", 70)
                    + "\n"
                )
                _display_response(iteration_msg, "", chunk_session_id)
                vim.command("redraw")

            # For Anthropic, we need to add the assistant message with ALL tool_use blocks first
            if (
                provider_name == "anthropic"
                and isinstance(messages, dict)
                and "messages" in messages
            ):
                # Build assistant message with text + all tool_use blocks
                assistant_content = []
                if accumulated_content.strip():
                    assistant_content.append(
                        {"type": "text", "text": accumulated_content}
                    )

                for tool_call in tool_calls_to_process:
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": tool_call["id"],
                            "name": tool_call["name"],
                            "input": tool_call["arguments"],
                        }
                    )

                messages["messages"].append(
                    {"role": "assistant", "content": assistant_content}
                )

            # Now execute tools and collect results
            # Reset plan loop counter since we're successfully executing tools
            plan_loop_count = 0

            tool_results = []
            for tool_call in tool_calls_to_process:
                tool_name = tool_call["name"]
                tool_args = tool_call["arguments"]
                tool_id = tool_call.get("id", "unknown")

                debug_log(
                    f"INFO: About to execute tool: {tool_name} with id: {tool_id}"
                )
                debug_log(f"DEBUG: Tool arguments: {json.dumps(tool_args)}")

                # Execute the tool
                tool_result = execute_tool(tool_name, tool_args)

                # Log the result
                result_preview = (
                    tool_result[:200] if len(tool_result) > 200 else tool_result
                )
                debug_log(
                    f"INFO: Tool {tool_name} completed. Result length: {len(tool_result)} chars"
                )
                debug_log(f"DEBUG: Tool result preview: {result_preview}")

                tool_results.append((tool_id, tool_name, tool_args, tool_result))

                # Display tool usage in session
                # Display tool usage with formatting
                if not suppress_display:
                    tool_display = format_tool_result(
                        tool_name, tool_args, tool_result, max_lines=15
                    )
                    # Escape for VimScript by doubling single quotes
                    escaped_display = tool_display.replace("'", "''")
                    _display_response(escaped_display, "", chunk_session_id)
                    vim.command("redraw")

            # Add tool results to messages - format depends on provider
            if provider_name == "openai":
                # OpenAI format - add each tool call and result individually
                if isinstance(messages, list):
                    for tool_id, tool_name, tool_args, tool_result in tool_results:
                        # Add assistant message with tool call
                        messages.append(
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": tool_id,
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": json.dumps(tool_args),
                                        },
                                    }
                                ],
                            }
                        )
                        # Add tool response
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_id,
                                "content": tool_result,
                            }
                        )
            elif provider_name == "anthropic":
                # Anthropic format - add ONE user message with ALL tool_result blocks
                if isinstance(messages, dict) and "messages" in messages:
                    tool_result_content = []
                    for tool_id, tool_name, tool_args, tool_result in tool_results:
                        # Ensure tool_result is never None
                        if tool_result is None:
                            tool_result = "Error: Tool returned None"
                            debug_log(
                                f"WARNING: Tool {tool_name} returned None, using error placeholder"
                            )

                        tool_result_content.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": str(
                                    tool_result
                                ),  # Ensure it's always a string
                            }
                        )

                    if tool_result_content:  # Only append if we have results
                        messages["messages"].append(
                            {"role": "user", "content": tool_result_content}
                        )
                    else:
                        debug_log("WARNING: No tool results to add to messages")

    except Exception as e:
        import traceback

        error_details = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        debug_log(f"ERROR: Full traceback:\n{error_details}")
        print(f"Error streaming from {provider_name}: {str(e)}")
        print(f"See /tmp/vim-chatgpt-debug.log for full error details")
