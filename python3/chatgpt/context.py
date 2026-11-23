"""
Context generation module

This module handles generating project context files to help the AI
understand projects in future conversations.
"""

import os
import re
from datetime import datetime
from chatgpt.utils import debug_log, get_config, get_project_dir, append_tool_results
from chatgpt.providers import create_provider
from chatgpt.tools import get_tool_definitions, execute_tool


def _get_project_files(project_dir=None):
    """
    Get a sorted list of all files in the project.

    Args:
        project_dir: Project directory (defaults to current directory)

    Returns:
        List of file paths relative to project_dir
    """
    if project_dir is None:
        project_dir = os.getcwd()

    files = []
    ignore_dirs = {'.git', '.vim-llm-agent', '.vim-chatgpt', 'node_modules',
                   '__pycache__', '.venv', 'venv', 'env', '.env', 'target',
                   'dist', 'build', '.next', '.cache'}

    for root, dirs, filenames in os.walk(project_dir):
        # Remove ignored directories from traversal
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        for filename in filenames:
            filepath = os.path.join(root, filename)
            # Get path relative to project_dir
            relpath = os.path.relpath(filepath, project_dir)
            files.append(relpath)

    return sorted(files)


def _save_file_manifest(vim_dir):
    """
    Save a manifest of current project files for future comparison.

    Args:
        vim_dir: The .vim-llm-agent directory path
    """
    try:
        # Get project directory (parent of vim_dir)
        project_dir = os.path.dirname(vim_dir)
        files = _get_project_files(project_dir)

        manifest_file = os.path.join(vim_dir, "file_manifest.txt")
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write("\n".join(files))

        debug_log(f"INFO: Saved file manifest with {len(files)} files to {manifest_file}")
    except Exception as e:
        debug_log(f"WARNING: Failed to save file manifest: {str(e)}")


def has_new_files(vim_dir):
    """
    Check if there are new files since the last context generation.

    Args:
        vim_dir: The .vim-llm-agent directory path

    Returns:
        bool: True if new files were added, False otherwise
    """
    try:
        manifest_file = os.path.join(vim_dir, "file_manifest.txt")

        # If no manifest exists, we should generate context
        if not os.path.exists(manifest_file):
            debug_log("INFO: No file manifest exists, should generate context")
            return True

        # Load old file list
        with open(manifest_file, "r", encoding="utf-8") as f:
            old_files = set(line.strip() for line in f if line.strip())

        # Get current file list
        project_dir = os.path.dirname(vim_dir)
        current_files = set(_get_project_files(project_dir))

        # Check if there are new files
        new_files = current_files - old_files

        if new_files:
            debug_log(f"INFO: Found {len(new_files)} new files: {list(new_files)[:10]}")
            return True
        else:
            debug_log("INFO: No new files detected")
            return False

    except Exception as e:
        debug_log(f"WARNING: Error checking for new files: {str(e)}")
        # On error, default to regenerating to be safe
        return True


def generate_project_context():
    """
    Generate a project context file by having the AI analyze the project.

    This uses AI with tools to explore the project, then saves the generated
    context markdown to .vim-llm-agent/context.md
    """
    debug_log("INFO: Starting project context generation")

    # Get vim directory path (with fallback for backwards compatibility)
    vim_dir = get_project_dir()
    context_file = os.path.join(vim_dir, "context.md")

    # Build the prompt - asking AI to analyze and output markdown
    prompt = """Please analyze this project and create a concise project context summary.

Use the available tools to:
1. Get the working directory
2. List the root directory contents
3. Look for README files, package.json, requirements.txt, Cargo.toml, go.mod, pom.xml, or other project metadata files
4. Read key configuration/metadata files to understand the project

Then output a markdown summary in this format:

# Project: [Name]

## Type
[e.g., Python web application, JavaScript library, Rust CLI tool, etc.]

## Purpose
[Brief description of what this project does]

## Tech Stack
[Key technologies, frameworks, and dependencies]

## Structure
[Brief overview of directory structure and key files]

## Key Files
[List important entry points, config files, etc.]

Important: Output ONLY the markdown summary. Do not include any conversational text before or after the markdown."""

    debug_log(f"DEBUG: Context generation prompt:\n{prompt}")

    # Get provider
    provider_name = get_config("provider", "openai")
    try:
        provider = create_provider(provider_name)
    except Exception as e:
        debug_log(f"ERROR: Failed to create provider '{provider_name}': {str(e)}")
        return

    # Get parameters
    max_tokens = int(get_config("max_tokens", "2000"))
    temperature = float(get_config("temperature", "0.7"))
    model = provider.get_model()

    # System message for context generation
    system_message = "You are a helpful assistant that analyzes projects and creates concise context summaries. Use the available tools to explore the project structure and files."

    # Create messages without any history
    try:
        messages = provider.create_messages(system_message, [], prompt)
    except Exception as e:
        debug_log(f"ERROR: Failed to create messages: {str(e)}")
        return

    # Get tool definitions
    tools = get_tool_definitions()

    # Iterative tool calling loop
    max_iterations = 20
    context_content = ""

    for iteration in range(max_iterations):
        debug_log(f"INFO: Context generation iteration {iteration + 1}/{max_iterations}")

        try:
            response_content = ""
            finish_reason = None
            tool_calls = None

            # Stream the response
            for content, reason, calls in provider.stream_chat(
                messages, model, temperature, max_tokens, tools=tools
            ):
                if content:
                    response_content += content
                if reason:
                    finish_reason = reason
                if calls:
                    tool_calls = calls

            debug_log(f"DEBUG: Iteration {iteration + 1} - finish_reason={finish_reason}, tool_calls={tool_calls is not None}")

            # If we got content, save it
            if response_content:
                context_content = response_content

            # If no tool calls, we're done
            if finish_reason == "stop" or not tool_calls:
                debug_log(f"INFO: Context generation complete ({len(context_content)} chars)")
                break

            # Execute tool calls
            if tool_calls:
                debug_log(f"INFO: Executing {len(tool_calls)} tool calls")

                tool_results = []
                for tool_call in tool_calls:
                    tool_name = tool_call.get("name", "")
                    tool_args = tool_call.get("arguments", {})
                    tool_id = tool_call.get("id", "")
                    debug_log(f"INFO: Executing tool: {tool_name}")
                    result = execute_tool(tool_name, tool_args)
                    tool_results.append((tool_id, tool_name, tool_args, result))

                append_tool_results(messages, provider_name, response_content, tool_calls, tool_results)

        except Exception as e:
            debug_log(f"ERROR: Failed during context generation: {str(e)}")
            return

    if not context_content:
        debug_log("ERROR: No context content generated")
        return

    # Clean up the content - remove any conversational wrapper
    # Extract just the markdown if wrapped in ```markdown blocks
    import re
    markdown_match = re.search(r'```markdown\n(.*?)\n```', context_content, re.DOTALL)
    if markdown_match:
        context_content = markdown_match.group(1)

    # Add timestamp metadata
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    metadata = f"<!-- Context generated at: {timestamp} -->\n\n"
    full_context = metadata + context_content.strip()

    # Save the context file
    try:
        # Create directory if it doesn't exist
        os.makedirs(vim_dir, exist_ok=True)

        with open(context_file, "w", encoding="utf-8") as f:
            f.write(full_context)
        debug_log(f"INFO: Context saved to {context_file}")
    except Exception as e:
        debug_log(f"ERROR: Failed to save context: {str(e)}")
        return

    debug_log("INFO: Context generation complete")

    # Save file manifest for future comparisons
    _save_file_manifest(vim_dir)
