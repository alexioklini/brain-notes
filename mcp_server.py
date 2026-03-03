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


# ── Resources ───────────────────────────────────────────────────────────────

@mcp.tool()
def list_resources(database_id: str) -> str:
    """List all resources (files/directories) linked to a project database."""
    return notes_tools.list_resources(database_id)


@mcp.tool()
def add_resource(database_id: str, path: str, name: str = "") -> str:
    """Add a file or directory as a resource to a project for indexing and semantic search.

    Args:
        database_id: Project database ID
        path: Absolute or ~ path to file or directory
        name: Display name (auto-detected from path if empty)
    """
    return notes_tools.add_resource(database_id, path, name)


@mcp.tool()
def remove_resource(database_id: str, resource_id: str) -> str:
    """Remove a resource from a project and delete its QMD search index."""
    return notes_tools.remove_resource(database_id, resource_id)


@mcp.tool()
def index_resource(database_id: str, resource_id: str) -> str:
    """Index a resource with QMD for semantic search. Creates vector embeddings for all files.
    Must be called after add_resource to enable search."""
    return notes_tools.index_resource(database_id, resource_id)


@mcp.tool()
def search_resources(database_id: str, query: str) -> str:
    """Semantic search across all indexed resources of a project using QMD vector search.
    Returns ranked results with snippets and relevance scores.

    Args:
        database_id: Project database ID
        query: Natural language search query (e.g. 'security vulnerabilities', 'budget costs')
    """
    return notes_tools.search_resources(database_id, query)


# ── Context ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_all_content() -> str:
    """Get a comprehensive overview of ALL content in the notes app — pages, databases, items.
    Use this for broad questions about what exists in the app."""
    return notes_tools.get_all_content()


if __name__ == "__main__":
    mcp.run()
