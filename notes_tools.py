"""Shared note operations used by both app.py (AI agents) and mcp_server.py.
Pure Python — no MCP/FastMCP dependency."""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notes.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def gen_id():
    return uuid.uuid4().hex[:12]


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


# ── Search ──────────────────────────────────────────────────────────────────

def search_notes(query: str) -> str:
    """Search across all pages, blocks, and database items by keyword."""
    with get_db() as conn:
        pages = conn.execute(
            "SELECT id, title, icon, workspace FROM pages WHERE title LIKE ? AND workspace != '_db_item' LIMIT 10",
            (f'%{query}%',)
        ).fetchall()
        blocks = conn.execute(
            """SELECT b.page_id, b.content, b.type, p.title FROM blocks b
               JOIN pages p ON b.page_id = p.id
               WHERE b.content LIKE ? AND p.workspace != '_db_item' LIMIT 15""",
            (f'%{query}%',)
        ).fetchall()
        items = conn.execute(
            """SELECT i.id, i.title, d.title as db_title, i.properties
               FROM db_items i JOIN databases d ON i.database_id = d.id
               WHERE i.title LIKE ? LIMIT 10""",
            (f'%{query}%',)
        ).fetchall()

    results = []
    if pages:
        results.append("## Pages")
        for p in pages:
            results.append(f"- **{p['title']}** (id: `{p['id']}`, workspace: {p['workspace']})")
    if blocks:
        results.append("\n## Content Matches")
        for b in blocks:
            snippet = b['content'][:150]
            results.append(f"- In page \"{b['title']}\" (page_id: `{b['page_id']}`): {snippet}")
    if items:
        results.append("\n## Database Items")
        for i in items:
            results.append(f"- \"{i['title']}\" in {i['db_title']} (item_id: `{i['id']}`)")

    return '\n'.join(results) if results else "No results found."


# ── Read ────────────────────────────────────────────────────────────────────

def list_pages(workspace: str = "all") -> str:
    """List all pages, optionally filtered by workspace."""
    with get_db() as conn:
        if workspace == "all":
            pages = conn.execute(
                "SELECT id, title, icon, workspace, parent_id, updated_at FROM pages WHERE workspace != '_db_item' ORDER BY updated_at DESC"
            ).fetchall()
        else:
            pages = conn.execute(
                "SELECT id, title, icon, workspace, parent_id, updated_at FROM pages WHERE workspace=? ORDER BY updated_at DESC",
                (workspace,)
            ).fetchall()

    if not pages:
        return "No pages found."

    lines = [f"## Pages ({len(pages)} total)"]
    for p in pages:
        parent = f" (child of {p['parent_id']})" if p['parent_id'] else ""
        lines.append(f"- {p['icon'] or '📄'} **{p['title']}** — id: `{p['id']}`{parent} (updated: {p['updated_at']})")
    return '\n'.join(lines)


def get_page(page_id: str) -> str:
    """Get full content of a page including all its blocks."""
    with get_db() as conn:
        page = conn.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()
        if not page:
            return f"Page not found: {page_id}"
        blocks = conn.execute(
            "SELECT id, type, content, properties, sort_order FROM blocks WHERE page_id=? ORDER BY sort_order",
            (page_id,)
        ).fetchall()

    result = f"# {page['title']}\n"
    result += f"ID: `{page['id']}` | Workspace: {page['workspace']} | Icon: {page['icon'] or 'none'}\n\n"

    for b in blocks:
        prefix = {'h1': '# ', 'h2': '## ', 'h3': '### ', 'bullet': '- ',
                  'numbered': '1. ', 'quote': '> ', 'code': '```\n'}.get(b['type'], '')
        suffix = '\n```' if b['type'] == 'code' else ''
        if b['type'] == 'todo':
            props = json.loads(b['properties']) if b['properties'] else {}
            prefix = '[x] ' if props.get('checked') else '[ ] '
        result += f"{prefix}{b['content']}{suffix}\n"

    return result


def list_databases() -> str:
    """List all databases with their schemas."""
    with get_db() as conn:
        dbs = conn.execute("SELECT * FROM databases ORDER BY updated_at DESC").fetchall()

    if not dbs:
        return "No databases found."

    lines = []
    for db in dbs:
        schema = json.loads(db['properties_schema']) if db['properties_schema'] else []
        prop_names = ', '.join(f"{p['name']} ({p['type']})" for p in schema)
        with get_db() as conn:
            item_count = conn.execute("SELECT COUNT(*) FROM db_items WHERE database_id=?", (db['id'],)).fetchone()[0]
        lines.append(f"### {db['title']} ({db['workspace']})")
        lines.append(f"ID: `{db['id']}` | Items: {item_count} | View: {db['default_view']}")
        lines.append(f"Properties: {prop_names or 'none'}")
        if db['description']:
            lines.append(f"Description: {db['description']}")
        lines.append("")

    return '\n'.join(lines)


def get_database_items(database_id: str) -> str:
    """Get all items in a database with their properties."""
    with get_db() as conn:
        db = conn.execute("SELECT * FROM databases WHERE id=?", (database_id,)).fetchone()
        if not db:
            return f"Database not found: {database_id}"
        schema = json.loads(db['properties_schema']) if db['properties_schema'] else []
        items = conn.execute(
            "SELECT * FROM db_items WHERE database_id=? ORDER BY sort_order", (database_id,)
        ).fetchall()

    lines = [f"## {db['title']} — {len(items)} items"]
    for item in items:
        props = json.loads(item['properties']) if item['properties'] else {}
        prop_strs = []
        for k, v in props.items():
            name = next((s['name'] for s in schema if s['id'] == k), k)
            prop_strs.append(f"{name}: {v}")
        prop_display = ' | '.join(prop_strs) if prop_strs else 'no properties'
        lines.append(f"- **{item['title']}** (id: `{item['id']}`) [{prop_display}]")

    return '\n'.join(lines)


# ── Create ──────────────────────────────────────────────────────────────────

def create_page(title: str, blocks: str = "[]", icon: str = "file-text",
                workspace: str = "docs", parent_id: str = "") -> str:
    """Create a new page with blocks."""
    page_id = gen_id()
    try:
        block_list = json.loads(blocks)
    except json.JSONDecodeError:
        block_list = [{"type": "text", "content": blocks}]

    with get_db() as conn:
        conn.execute(
            "INSERT INTO pages (id, title, icon, workspace, parent_id, sort_order) VALUES (?,?,?,?,?,0)",
            (page_id, title, icon, workspace, parent_id or None)
        )
        for i, block in enumerate(block_list):
            bid = gen_id()
            conn.execute(
                "INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,?,?,?)",
                (bid, page_id, block.get('type', 'text'), block.get('content', ''), i)
            )
        conn.commit()

    return json.dumps({"created": page_id, "title": title, "blocks": len(block_list)})


def create_database(title: str, workspace: str = "projects", description: str = "") -> str:
    """Create a new database (project board or knowledge base)."""
    db_id = gen_id()
    if workspace == 'projects':
        schema = [
            {'id': gen_id(), 'name': 'Status', 'type': 'select',
             'options': [{'id': gen_id(), 'name': s, 'color': c} for s, c in
                        [('Not Started', '#6B7280'), ('In Progress', '#3B82F6'),
                         ('Done', '#10B981'), ('Blocked', '#EF4444')]]},
            {'id': gen_id(), 'name': 'Priority', 'type': 'select',
             'options': [{'id': gen_id(), 'name': s, 'color': c} for s, c in
                        [('Low', '#6B7280'), ('Medium', '#F59E0B'), ('High', '#EF4444')]]},
            {'id': gen_id(), 'name': 'Due Date', 'type': 'date'},
        ]
    else:
        schema = [
            {'id': gen_id(), 'name': 'Status', 'type': 'select',
             'options': [{'id': gen_id(), 'name': s, 'color': c} for s, c in
                        [('Draft', '#6B7280'), ('In Review', '#F59E0B'), ('Published', '#10B981')]]},
            {'id': gen_id(), 'name': 'Category', 'type': 'select', 'options': []},
        ]

    with get_db() as conn:
        default_view = 'board' if workspace == 'projects' else 'table'
        conn.execute(
            "INSERT INTO databases (id, title, icon, workspace, description, properties_schema, default_view) VALUES (?,?,?,?,?,?,?)",
            (db_id, title, 'layout-grid' if workspace == 'projects' else 'book-open',
             workspace, description, json.dumps(schema), default_view)
        )
        view_id = gen_id()
        group_by = schema[0]['id'] if schema[0]['type'] == 'select' else None
        conn.execute(
            "INSERT INTO db_views (id, database_id, name, type, config, sort_order) VALUES (?,?,?,?,?,0)",
            (view_id, db_id, 'Default', default_view, json.dumps({'group_by': group_by} if group_by else {}))
        )
        conn.commit()

    return json.dumps({"created": db_id, "title": title, "workspace": workspace,
                       "properties": [p['name'] for p in schema]})


def create_database_item(database_id: str, title: str, properties: str = "{}") -> str:
    """Add an item to a database."""
    try:
        props = json.loads(properties)
    except json.JSONDecodeError:
        props = {}

    item_id = gen_id()
    with get_db() as conn:
        db = conn.execute("SELECT id FROM databases WHERE id=?", (database_id,)).fetchone()
        if not db:
            return f"Database not found: {database_id}"
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order),0) FROM db_items WHERE database_id=?", (database_id,)
        ).fetchone()[0]
        page_id = gen_id()
        conn.execute("INSERT INTO pages (id, title, workspace) VALUES (?,?,'_db_item')", (page_id, title))
        conn.execute("INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,'text','',0)",
                     (gen_id(), page_id))
        conn.execute(
            "INSERT INTO db_items (id, database_id, title, properties, page_id, sort_order) VALUES (?,?,?,?,?,?)",
            (item_id, database_id, title, json.dumps(props), page_id, max_order + 1)
        )
        conn.commit()

    return json.dumps({"created": item_id, "title": title})


# ── Edit ────────────────────────────────────────────────────────────────────

def edit_page(page_id: str, title: str = "", icon: str = "",
              replace_blocks: str = "", append_blocks: str = "") -> str:
    """Edit an existing page."""
    with get_db() as conn:
        page = conn.execute("SELECT id FROM pages WHERE id=?", (page_id,)).fetchone()
        if not page:
            return f"Page not found: {page_id}"

        if title:
            conn.execute("UPDATE pages SET title=?, updated_at=? WHERE id=?", (title, now(), page_id))
        if icon:
            conn.execute("UPDATE pages SET icon=?, updated_at=? WHERE id=?", (icon, now(), page_id))

        if replace_blocks:
            try:
                blocks = json.loads(replace_blocks)
            except json.JSONDecodeError:
                return "Invalid JSON in replace_blocks"
            conn.execute("DELETE FROM blocks WHERE page_id=?", (page_id,))
            for i, block in enumerate(blocks):
                bid = gen_id()
                conn.execute(
                    "INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,?,?,?)",
                    (bid, page_id, block.get('type', 'text'), block.get('content', ''), i)
                )

        elif append_blocks:
            try:
                blocks = json.loads(append_blocks)
            except json.JSONDecodeError:
                return "Invalid JSON in append_blocks"
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order),0) FROM blocks WHERE page_id=?", (page_id,)
            ).fetchone()[0]
            for i, block in enumerate(blocks):
                bid = gen_id()
                conn.execute(
                    "INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,?,?,?)",
                    (bid, page_id, block.get('type', 'text'), block.get('content', ''), max_order + 1 + i)
                )

        conn.commit()

    return json.dumps({"updated": page_id})


def update_database_item(database_id: str, item_id: str, title: str = "", properties: str = "") -> str:
    """Update a database item's title and/or properties."""
    with get_db() as conn:
        item = conn.execute("SELECT * FROM db_items WHERE id=? AND database_id=?",
                           (item_id, database_id)).fetchone()
        if not item:
            return f"Item not found: {item_id} in database {database_id}"

        if title:
            conn.execute("UPDATE db_items SET title=?, updated_at=? WHERE id=?", (title, now(), item_id))
        if properties:
            try:
                new_props = json.loads(properties)
            except json.JSONDecodeError:
                return "Invalid JSON in properties"
            existing = json.loads(item['properties']) if item['properties'] else {}
            existing.update(new_props)
            conn.execute("UPDATE db_items SET properties=?, updated_at=? WHERE id=?",
                        (json.dumps(existing), now(), item_id))
        conn.commit()

    return json.dumps({"updated": item_id})


# ── Delete ──────────────────────────────────────────────────────────────────

def delete_page(page_id: str) -> str:
    """Delete a page and all its blocks."""
    with get_db() as conn:
        page = conn.execute("SELECT title FROM pages WHERE id=?", (page_id,)).fetchone()
        if not page:
            return f"Page not found: {page_id}"
        conn.execute("DELETE FROM blocks WHERE page_id=?", (page_id,))
        conn.execute("DELETE FROM pages WHERE id=?", (page_id,))
        conn.commit()

    return json.dumps({"deleted": page_id, "title": page['title']})


def delete_database_item(database_id: str, item_id: str) -> str:
    """Delete an item from a database."""
    with get_db() as conn:
        item = conn.execute("SELECT title, page_id FROM db_items WHERE id=? AND database_id=?",
                           (item_id, database_id)).fetchone()
        if not item:
            return f"Item not found: {item_id}"
        if item['page_id']:
            conn.execute("DELETE FROM blocks WHERE page_id=?", (item['page_id'],))
            conn.execute("DELETE FROM pages WHERE id=?", (item['page_id'],))
        conn.execute("DELETE FROM db_items WHERE id=?", (item_id,))
        conn.commit()

    return json.dumps({"deleted": item_id, "title": item['title']})


# ── Context ─────────────────────────────────────────────────────────────────

def get_all_content() -> str:
    """Get a comprehensive overview of ALL content in the notes app."""
    sections = []
    with get_db() as conn:
        pages = conn.execute(
            "SELECT * FROM pages WHERE (workspace='docs' OR workspace IS NULL) ORDER BY updated_at DESC"
        ).fetchall()
        if pages:
            sections.append("## DOCS (Pages)")
            for p in pages:
                blocks = conn.execute(
                    "SELECT type, content FROM blocks WHERE page_id=? ORDER BY sort_order", (p['id'],)
                ).fetchall()
                content = '\n'.join(b['content'] for b in blocks if b['content'] and b['type'] != 'divider')
                preview = content[:300] + '...' if len(content) > 300 else content
                sections.append(f"\n### {p['title']} (id: `{p['id']}`)\n{preview or '[Empty page]'}")

        dbs = conn.execute("SELECT * FROM databases ORDER BY updated_at DESC").fetchall()
        for db in dbs:
            schema = json.loads(db['properties_schema']) if db['properties_schema'] else []
            items = conn.execute(
                "SELECT * FROM db_items WHERE database_id=? ORDER BY sort_order", (db['id'],)
            ).fetchall()
            ws = 'PROJECT' if db['workspace'] == 'projects' else 'KNOWLEDGE BASE'
            sections.append(f"\n## {ws}: {db['title']} (id: `{db['id']}`)")
            sections.append(f"Properties: {', '.join(p['name'] + ' (' + p['type'] + ')' for p in schema)}")
            for item in items:
                props = json.loads(item['properties']) if item['properties'] else {}
                prop_str = ', '.join(
                    f"{next((s['name'] for s in schema if s['id'] == k), k)}: {v}"
                    for k, v in props.items() if v
                )
                sections.append(f"  - {item['title']} (id: `{item['id']}`) [{prop_str}]")

    return '\n'.join(sections) if sections else "No content in the app yet."
