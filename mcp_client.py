"""MCP Client for Brain Notes — calls the MCP server via stdio protocol.
Used by the AI chat agents in app.py to execute tools through the MCP server."""

import asyncio
import json
import logging
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

# Path to the MCP server script
MCP_SERVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mcp_server.py')

# Tool name mapping: legacy in-app names → MCP server names
TOOL_NAME_MAP = {
    'search_content': 'search_notes',
    'get_page_content': 'get_page',
    'create_project_item': 'create_database_item',
    'update_project_item': 'update_database_item',
}


def _get_server_params():
    """Get StdioServerParameters for spawning the MCP server."""
    return StdioServerParameters(
        command="/opt/homebrew/bin/python3.12",
        args=[MCP_SERVER_PATH],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )


async def _call_tool_async(name: str, arguments: dict) -> str:
    """Call an MCP tool asynchronously via the stdio protocol."""
    server_params = _get_server_params()

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)

            # Extract text from result content
            texts = []
            for content in result.content:
                if hasattr(content, 'text'):
                    texts.append(content.text)
            return '\n'.join(texts) if texts else str(result)


def call_tool(name: str, input_data: dict) -> str:
    """Call an MCP tool synchronously. Entry point for app.py's AI agents.
    
    Handles:
    - Tool name normalization (legacy → MCP names)
    - JSON serialization of complex arguments (blocks, properties)
    - Spawns MCP server process per call via stdio
    """
    # Normalize tool name
    name = TOOL_NAME_MAP.get(name, name)

    # Prepare arguments — MCP tools expect simple types (strings, not dicts/lists)
    arguments = dict(input_data)

    # Serialize complex types to JSON strings (MCP tool signatures use str)
    for key in ('blocks', 'replace_blocks', 'append_blocks', 'properties'):
        if key in arguments and isinstance(arguments[key], (dict, list)):
            arguments[key] = json.dumps(arguments[key])

    try:
        # Run async call in a new event loop (safe from sync Flask context)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_call_tool_async(name, arguments))
        finally:
            loop.close()
        return result
    except Exception as e:
        logger.error(f"MCP tool call failed: {name}({arguments}): {e}")
        return f"Error executing {name}: {str(e)}"
