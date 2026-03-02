#!/usr/bin/env python3
"""MCP Server for Brain Notes — thin wrapper around notes_tools.py.
All actual logic lives in notes_tools.py (shared with app.py AI agents)."""

from mcp.server.fastmcp import FastMCP
import notes_tools

mcp = FastMCP("brain-notes", instructions="""
Brain Notes MCP Server — manage pages, blocks, databases, and project items in the Brain Notes app.
Use these tools to search, read, create, edit, and delete content.
""")


# ── Search ──────────────────────────────────────────────────────────────────

@mcp.tool()
def search_notes(query: str) -> str:
    """Search across all pages, blocks, and database items by keyword.
    Returns matching page titles, block content snippets, and database item titles."""
    return notes_tools.search_notes(query)


# ── Read ────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_pages(workspace: str = "all") -> str:
    """List all pages. Filter by workspace: 'docs', 'all', etc. Excludes internal _db_item pages."""
    return notes_tools.list_pages(workspace)


@mcp.tool()
def get_page(page_id: str) -> str:
    """Get full content of a page including all its blocks."""
    return notes_tools.get_page(page_id)


@mcp.tool()
def list_databases() -> str:
    """List all databases (projects and knowledge bases) with their schemas."""
    return notes_tools.list_databases()


@mcp.tool()
def get_database_items(database_id: str) -> str:
    """Get all items in a database with their properties."""
    return notes_tools.get_database_items(database_id)


# ── Create ──────────────────────────────────────────────────────────────────

@mcp.tool()
def create_page(title: str, blocks: str, icon: str = "file-text", workspace: str = "docs", parent_id: str = "") -> str:
    """Create a new page with blocks.

    Args:
        title: Page title
        blocks: JSON array of blocks, e.g. [{"type":"h1","content":"Heading"},{"type":"text","content":"Body"}]
               Block types: text, h1, h2, h3, bullet, numbered, todo, quote, callout, code, divider
        icon: Lucide icon name (e.g. 'target', 'lightbulb', 'flask-conical')
        workspace: 'docs' (default)
        parent_id: Optional parent page ID for nesting
    """
    return notes_tools.create_page(title, blocks, icon, workspace, parent_id)


@mcp.tool()
def create_database(title: str, workspace: str = "projects", description: str = "") -> str:
    """Create a new database (project board or knowledge base).

    Args:
        title: Database title
        workspace: 'projects' (kanban board) or 'wiki' (knowledge base table)
        description: Optional description
    """
    return notes_tools.create_database(title, workspace, description)


@mcp.tool()
def create_database_item(database_id: str, title: str, properties: str = "{}") -> str:
    """Add an item to a database.

    Args:
        database_id: Database ID
        title: Item title
        properties: JSON object mapping property_id to value, e.g. {"prop_id": "value"}
    """
    return notes_tools.create_database_item(database_id, title, properties)


# ── Edit ────────────────────────────────────────────────────────────────────

@mcp.tool()
def edit_page(page_id: str, title: str = "", icon: str = "", replace_blocks: str = "", append_blocks: str = "") -> str:
    """Edit an existing page — change title, icon, replace all blocks, or append blocks.

    Args:
        page_id: Page ID to edit
        title: New title (leave empty to keep current)
        icon: New Lucide icon name (leave empty to keep current)
        replace_blocks: JSON array of blocks to REPLACE all existing content
        append_blocks: JSON array of blocks to APPEND at the end
    """
    return notes_tools.edit_page(page_id, title, icon, replace_blocks, append_blocks)


@mcp.tool()
def update_database_item(database_id: str, item_id: str, title: str = "", properties: str = "") -> str:
    """Update a database item's title and/or properties.

    Args:
        database_id: Database ID
        item_id: Item ID to update
        title: New title (leave empty to keep current)
        properties: JSON object of properties to update (merged with existing)
    """
    return notes_tools.update_database_item(database_id, item_id, title, properties)


# ── Delete ──────────────────────────────────────────────────────────────────

@mcp.tool()
def delete_page(page_id: str) -> str:
    """Delete a page and all its blocks."""
    return notes_tools.delete_page(page_id)


@mcp.tool()
def delete_database_item(database_id: str, item_id: str) -> str:
    """Delete an item from a database."""
    return notes_tools.delete_database_item(database_id, item_id)


# ── Context ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_all_content() -> str:
    """Get a comprehensive overview of ALL content in the notes app — pages, databases, items.
    Use this for broad questions about what exists in the app."""
    return notes_tools.get_all_content()


if __name__ == "__main__":
    mcp.run()
