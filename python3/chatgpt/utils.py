"""
Utility functions for the ChatGPT plugin
"""

import os
import vim


def get_config(name, default=None):
    """
    Get configuration value with automatic fallback from old to new names.

    Supports backwards compatibility by checking:
    1. New name: g:llm_agent_{name}
    2. Old name: g:chat_gpt_{name} (deprecated, for backward compatibility)
    3. Default value

    Args:
        name: Config variable name (without prefix)
        default: Default value if neither variable exists

    Returns:
        Configuration value or default

    Examples:
        get_config('api_key') checks g:llm_agent_api_key then g:chat_gpt_api_key
        get_config('model', 'gpt-4') returns 'gpt-4' if neither is set

    Note:
        The old g:chat_gpt_* naming is deprecated. Please migrate to g:llm_agent_*.
    """
    # Try new name first
    new_var = f"g:llm_agent_{name}"
    try:
        new_val = vim.eval(f'exists("{new_var}") ? {new_var} : ""')
        if new_val and new_val != "":
            return new_val
    except vim.error:
        pass

    # Fall back to old name for backward compatibility
    old_var = f"g:chat_gpt_{name}"
    try:
        old_val = vim.eval(f'exists("{old_var}") ? {old_var} : ""')
        if old_val and old_val != "":
            # Log deprecation warning (only once per variable)
            debug_log(
                f"WARNING: {old_var} is deprecated. Please use {new_var} instead.",
                force=True,
            )
            return old_val
    except vim.error:
        pass

    # Return default
    return default


def get_project_dir():
    """
    Get the project data directory with automatic fallback.

    Checks for:
    1. .vim-llm-agent/ (new name)
    2. .vim-chatgpt/ (old name, for backwards compatibility)

    Returns:
        str: Directory name to use (.vim-llm-agent or .vim-chatgpt)
    """
    new_dir = os.path.join(os.getcwd(), ".vim-llm-agent")
    old_dir = os.path.join(os.getcwd(), ".vim-chatgpt")

    # If new directory exists, use it
    if os.path.exists(new_dir):
        return new_dir

    # If old directory exists, use it (backwards compatibility)
    if os.path.exists(old_dir):
        return old_dir

    # Neither exists - return new name (will be created)
    return new_dir


# Log level constants
LOG_LEVEL_DEBUG = 0
LOG_LEVEL_INFO = 1
LOG_LEVEL_WARNING = 2
LOG_LEVEL_ERROR = 3

LOG_LEVEL_MAP = {
    "DEBUG:": LOG_LEVEL_DEBUG,
    "INFO:": LOG_LEVEL_INFO,
    "WARNING:": LOG_LEVEL_WARNING,
    "ERROR:": LOG_LEVEL_ERROR,
}


def debug_log(msg, force=False):
    """
    Write debug messages to a log file for troubleshooting.

    Messages can be prefixed with a log level:
    - DEBUG: Detailed debugging information (level 0)
    - INFO: General informational messages (level 1)
    - WARNING: Warning messages (level 2)
    - ERROR: Error messages (level 3)

    If no prefix is provided, the message is treated as DEBUG level.

    Args:
        msg: The message to log
        force: If True, always log regardless of configured level
    """
    try:
        import vim

        configured_level = int(get_config("log_level", "0"))

        if configured_level == 0 and not force:
            return

        message_level = LOG_LEVEL_DEBUG
        clean_msg = msg

        for prefix, level in LOG_LEVEL_MAP.items():
            if msg.startswith(prefix):
                message_level = level
                clean_msg = msg[len(prefix) :].strip()
                break

        if not force and message_level < (configured_level - 1):
            return

        # Use project directory for debug log (cross-platform)
        try:
            project_dir = get_project_dir()
            # Create directory if it doesn't exist
            if not os.path.exists(project_dir):
                os.makedirs(project_dir)
            log_file = os.path.join(project_dir, "debug.log")
        except Exception:
            # Fallback to temp directory if project dir fails (cross-platform)
            import tempfile

            log_file = os.path.join(tempfile.gettempdir(), "vim-llm-agent-debug.log")

        from datetime import datetime

        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        level_name = [k for k, v in LOG_LEVEL_MAP.items() if v == message_level]
        level_str = level_name[0].rstrip(":") if level_name else "DEBUG"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level_str}] {clean_msg}\n")
    except Exception as e:
        pass


def save_to_history(content):
    """Save content to history file"""
    try:
        # Check both old and new variable names for backwards compatibility
        session_mode = get_config("session_mode", "1")
        session_enabled = int(session_mode) == 1
        if not session_enabled:
            return

        project_dir = get_project_dir()
        history_file = os.path.join(project_dir, "history.txt")

        if not os.path.exists(project_dir):
            os.makedirs(project_dir)

        with open(history_file, "a", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        pass


def save_plan(plan_content):
    """
    Save the approved plan to plan.md in the project directory

    This ensures the plan persists across conversation compactions and sessions.

    Args:
        plan_content: The plan text to save
    """
    try:
        session_enabled = int(get_config("session_mode", "1")) == 1
        if not session_enabled:
            debug_log("INFO: Session mode disabled, not saving plan")
            return

        project_dir = get_project_dir()
        plan_file = os.path.join(project_dir, "plan.md")

        if not os.path.exists(project_dir):
            os.makedirs(project_dir)

        # Add metadata header
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        content_with_metadata = f"""<!-- Plan saved at: {timestamp} -->

{plan_content.strip()}
"""

        with open(plan_file, "w", encoding="utf-8") as f:
            f.write(content_with_metadata)

        debug_log(f"INFO: Plan saved to {plan_file}")
    except Exception as e:
        debug_log(f"ERROR: Failed to save plan: {str(e)}")


def load_plan():
    """
    Load the saved plan from plan.md in the project directory

    Returns:
        str: The plan content, or None if no plan exists
    """
    try:
        plan_file = os.path.join(get_project_dir(), "plan.md")

        if not os.path.exists(plan_file):
            return None

        with open(plan_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Strip metadata comments
        import re

        content = re.sub(r"<!--.*?-->\s*\n", "", content, flags=re.DOTALL)

        debug_log(f"INFO: Loaded plan from {plan_file}")
        return content.strip()
    except Exception as e:
        debug_log(f"WARNING: Failed to load plan: {str(e)}")
        return None


def clear_plan():
    """
    Delete the saved plan file.

    This should be called when a plan is completed or the user wants to discard it.

    Returns:
        bool: True if plan was deleted, False if no plan existed or deletion failed
    """
    try:
        plan_file = os.path.join(get_project_dir(), "plan.md")

        if not os.path.exists(plan_file):
            debug_log("INFO: No plan file to clear")
            return False

        os.remove(plan_file)
        debug_log(f"INFO: Plan file deleted: {plan_file}")
        return True
    except Exception as e:
        debug_log(f"ERROR: Failed to delete plan: {str(e)}")
        return False


# Formatting helpers for better chat display
def format_box(title, content="", width=60):
    """Create a formatted box with title and optional content"""
    top = "╔" + "═" * (width - 2) + "╗"
    bottom = "╚" + "═" * (width - 2) + "╝"

    lines = [top]

    if title:
        title_padded = f" {title} ".center(width - 2, " ")
        lines.append(f"║{title_padded}║")
        if content:
            lines.append("║" + " " * (width - 2) + "║")

    if content:
        for line in content.split("\n"):
            while len(line) > width - 6:
                lines.append(f"║  {line[:width-6]}  ║")
                line = line[width - 6 :]
            if line:
                line_padded = f"  {line}".ljust(width - 2)
                lines.append(f"║{line_padded}║")

    lines.append(bottom)
    return "\n".join(lines)


def format_separator(char="─", width=60):
    """Create a horizontal separator"""
    return char * width


def format_tool_call(tool_name, tool_args, status="executing"):
    """Format a tool call with status indicator"""
    if status == "executing":
        icon = "🔧"
        status_text = "Executing"
    elif status == "success":
        icon = "✓"
        status_text = "Success"
    elif status == "error":
        icon = "✗"
        status_text = "Error"
    else:
        icon = "→"
        status_text = status

    args_str = ", ".join(f"{k}={repr(v)[:40]}" for k, v in tool_args.items())
    if len(args_str) > 60:
        args_str = args_str[:57] + "..."

    return f"{icon} {status_text}: {tool_name}({args_str})"


def format_tool_result(tool_name, tool_args, result, max_lines=20):
    """Format tool execution result with header"""
    header = format_separator("─", 60)
    tool_call_str = format_tool_call(tool_name, tool_args, "success")

    result_lines = result.split("\n")
    if len(result_lines) > max_lines:
        result_lines = result_lines[:max_lines]
        result_lines.append(
            f"... (truncated, {len(result.split(chr(10))) - max_lines} more lines)"
        )

    result_formatted = "\n".join(f"  {line}" for line in result_lines)

    return f"\n{header}\n{tool_call_str}\n\nOutput:\n{result_formatted}\n{header}\n"


def format_plan_display(plan_type, explanation, tool_calls):
    """Format plan approval display with nice boxes"""
    title = f"{plan_type} FOR APPROVAL"

    content_parts = []

    if explanation and explanation.strip():
        content_parts.append("Explanation:")
        content_parts.append(explanation.strip())
        content_parts.append("")

    content_parts.append("Tools to execute:")
    for i, tc in enumerate(tool_calls, 1):
        args_str = ", ".join(f"{k}={repr(v)[:30]}" for k, v in tc["arguments"].items())
        content_parts.append(f"  {i}. {tc['name']}({args_str})")

    content = "\n".join(content_parts)

    return "\n\n" + format_box(title, content, width=70) + "\n"


def parse_conversation_history(history_text):
    """
    Parse conversation history text into structured messages.
    
    The history format is:
    >>>User:
    <user message>
    
    >>>Assistant:
    <assistant response>
    
    Args:
        history_text: Raw conversation history text
        
    Returns:
        list: List of message dicts with 'role' and 'content' keys
    """
    messages = []
    current_role = None
    current_content = []
    
    for line in history_text.split('\n'):
        if line.strip() == '\x01>>>User:\x01':
            # Save previous message if exists
            if current_role and current_content:
                messages.append({
                    'role': current_role,
                    'content': '\n'.join(current_content).strip()
                })
            # Start new user message
            current_role = 'user'
            current_content = []
        elif line.strip() == '\x01>>>Assistant:\x01':
            # Save previous message if exists
            if current_role and current_content:
                messages.append({
                    'role': current_role,
                    'content': '\n'.join(current_content).strip()
                })
            # Start new assistant message
            current_role = 'assistant'
            current_content = []
        else:
            # Accumulate content for current message
            if current_role:
                current_content.append(line)
    
    # Save final message
    if current_role and current_content:
        messages.append({
            'role': current_role,
            'content': '\n'.join(current_content).strip()
        })

    return messages


def append_tool_results(messages, provider_name, accumulated_content, tool_calls, tool_results):
    """
    Append tool-use and tool-result messages in the format required by each provider.

    For Anthropic: adds a single assistant message containing all tool_use blocks,
    then a single user message containing all tool_result blocks.
    For OpenAI / others: adds one assistant+tool pair per tool call.

    Args:
        messages: The messages structure (dict for Anthropic, list for others).
        provider_name: "anthropic", "openai", etc.
        accumulated_content: Text the assistant emitted before the tool calls.
        tool_calls: List of dicts with {id, name, arguments}.
        tool_results: List of (tool_id, tool_name, tool_args, tool_result) tuples.
    """
    import json as _json

    if provider_name == "anthropic" and isinstance(messages, dict) and "messages" in messages:
        assistant_content = []
        if accumulated_content.strip():
            assistant_content.append({"type": "text", "text": accumulated_content})
        for tc in tool_calls:
            assistant_content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["arguments"],
            })
        messages["messages"].append({"role": "assistant", "content": assistant_content})

        tool_result_content = []
        for tool_id, tool_name, _args, tool_result in tool_results:
            tool_result_content.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": str(tool_result) if tool_result is not None else "Error: Tool returned None",
            })
        if tool_result_content:
            messages["messages"].append({"role": "user", "content": tool_result_content})

    elif isinstance(messages, list):
        for tool_id, tool_name, tool_args, tool_result in tool_results:
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": _json.dumps(tool_args),
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": str(tool_result) if tool_result is not None else "Error: Tool returned None",
            })
