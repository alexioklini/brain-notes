#!/usr/bin/env python3.12
"""Brain Notes — Notion Clone Backend with Docs, Projects, Knowledge Base"""
import json, logging, os, sqlite3, uuid
from datetime import datetime, date
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notes.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pages (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'Untitled',
                icon TEXT DEFAULT '',
                cover TEXT DEFAULT '',
                parent_id TEXT DEFAULT NULL,
                workspace TEXT DEFAULT 'docs',
                sort_order INTEGER DEFAULT 0,
                is_favorite BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES pages(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS blocks (
                id TEXT PRIMARY KEY,
                page_id TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'text',
                content TEXT DEFAULT '',
                properties TEXT DEFAULT '{}',
                sort_order INTEGER DEFAULT 0,
                indent_level INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE
            );

            -- Databases (for Projects & Knowledge Base)
            CREATE TABLE IF NOT EXISTS databases (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'Untitled Database',
                icon TEXT DEFAULT '',
                workspace TEXT DEFAULT 'projects',
                description TEXT DEFAULT '',
                properties_schema TEXT DEFAULT '[]',
                default_view TEXT DEFAULT 'table',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Database items (rows)
            CREATE TABLE IF NOT EXISTS db_items (
                id TEXT PRIMARY KEY,
                database_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT 'Untitled',
                icon TEXT DEFAULT '',
                properties TEXT DEFAULT '{}',
                page_id TEXT DEFAULT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (database_id) REFERENCES databases(id) ON DELETE CASCADE,
                FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE SET NULL
            );

            -- Database views
            CREATE TABLE IF NOT EXISTS db_views (
                id TEXT PRIMARY KEY,
                database_id TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT 'Default',
                type TEXT NOT NULL DEFAULT 'table',
                config TEXT DEFAULT '{}',
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (database_id) REFERENCES databases(id) ON DELETE CASCADE
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
                id, title, content='pages', content_rowid=rowid
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS blocks_fts USING fts5(
                id, content, content='blocks', content_rowid=rowid
            );
        """)
        # Add workspace column if missing (migration)
        try:
            conn.execute("SELECT workspace FROM pages LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE pages ADD COLUMN workspace TEXT DEFAULT 'docs'")
        conn.commit()
    logger.info("Database initialized")

init_db()

def dict_row(row):
    if row is None: return None
    return dict(row)

def now():
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

def gen_id():
    return str(uuid.uuid4())[:8]

# ── Pages ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/pages', methods=['GET'])
def list_pages():
    workspace = request.args.get('workspace')
    with get_db() as conn:
        if workspace:
            rows = conn.execute(
                "SELECT * FROM pages WHERE workspace=? ORDER BY is_favorite DESC, sort_order ASC, updated_at DESC",
                (workspace,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pages ORDER BY is_favorite DESC, sort_order ASC, updated_at DESC"
            ).fetchall()
    return jsonify([dict_row(r) for r in rows])

@app.route('/api/pages', methods=['POST'])
def create_page():
    data = request.get_json(force=True)
    page_id = data.get('id', gen_id())
    title = data.get('title', 'Untitled')
    parent_id = data.get('parent_id')
    icon = data.get('icon', '')
    workspace = data.get('workspace', 'docs')
    
    with get_db() as conn:
        if parent_id:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order),0) FROM pages WHERE parent_id=?", (parent_id,)
            ).fetchone()[0]
        else:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order),0) FROM pages WHERE parent_id IS NULL AND workspace=?",
                (workspace,)
            ).fetchone()[0]
        
        conn.execute(
            "INSERT INTO pages (id, title, icon, parent_id, workspace, sort_order) VALUES (?,?,?,?,?,?)",
            (page_id, title, icon, parent_id, workspace, max_order + 1)
        )
        block_id = gen_id()
        conn.execute(
            "INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,'text','',0)",
            (block_id, page_id)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()
    return jsonify(dict_row(row)), 201

@app.route('/api/pages/<page_id>', methods=['GET'])
def get_page(page_id):
    with get_db() as conn:
        page = conn.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()
        if not page:
            return jsonify({'error': 'Not found'}), 404
        blocks = conn.execute(
            "SELECT * FROM blocks WHERE page_id=? ORDER BY sort_order", (page_id,)
        ).fetchall()
        children = conn.execute(
            "SELECT id, title, icon FROM pages WHERE parent_id=? ORDER BY sort_order", (page_id,)
        ).fetchall()
    result = dict_row(page)
    result['blocks'] = [dict_row(b) for b in blocks]
    result['children'] = [dict_row(c) for c in children]
    return jsonify(result)

@app.route('/api/pages/<page_id>', methods=['PUT'])
def update_page(page_id):
    data = request.get_json(force=True)
    with get_db() as conn:
        page = conn.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()
        if not page:
            return jsonify({'error': 'Not found'}), 404
        
        updates, params = [], []
        for field in ['title', 'icon', 'cover', 'parent_id', 'sort_order', 'is_favorite', 'workspace']:
            if field in data:
                updates.append(f"{field}=?")
                params.append(data[field])
        if updates:
            updates.append("updated_at=?")
            params.append(now())
            params.append(page_id)
            conn.execute(f"UPDATE pages SET {','.join(updates)} WHERE id=?", params)
            conn.commit()
        
        row = conn.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()
    return jsonify(dict_row(row))

@app.route('/api/pages/<page_id>', methods=['DELETE'])
def delete_page(page_id):
    with get_db() as conn:
        children = conn.execute("SELECT id FROM pages WHERE parent_id=?", (page_id,)).fetchall()
        for child in children:
            delete_page_recursive(conn, child['id'])
        conn.execute("DELETE FROM blocks WHERE page_id=?", (page_id,))
        conn.execute("DELETE FROM pages WHERE id=?", (page_id,))
        conn.commit()
    return jsonify({'ok': True})

def delete_page_recursive(conn, page_id):
    children = conn.execute("SELECT id FROM pages WHERE parent_id=?", (page_id,)).fetchall()
    for child in children:
        delete_page_recursive(conn, child['id'])
    conn.execute("DELETE FROM blocks WHERE page_id=?", (page_id,))
    conn.execute("DELETE FROM pages WHERE id=?", (page_id,))

@app.route('/api/pages/reorder', methods=['PUT'])
def reorder_pages():
    data = request.get_json(force=True)
    order = data.get('order', [])
    with get_db() as conn:
        for idx, pid in enumerate(order):
            conn.execute("UPDATE pages SET sort_order=? WHERE id=?", (idx, pid))
        conn.commit()
    return jsonify({'ok': True})

# ── Blocks ─────────────────────────────────────────────────────────────────

@app.route('/api/pages/<page_id>/blocks', methods=['GET'])
def get_blocks(page_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM blocks WHERE page_id=? ORDER BY sort_order", (page_id,)
        ).fetchall()
    return jsonify([dict_row(r) for r in rows])

@app.route('/api/pages/<page_id>/blocks', methods=['POST'])
def create_block(page_id):
    data = request.get_json(force=True)
    block_id = data.get('id', gen_id())
    block_type = data.get('type', 'text')
    content = data.get('content', '')
    properties = json.dumps(data.get('properties', {}))
    after_id = data.get('after_id')
    indent = data.get('indent_level', 0)
    
    with get_db() as conn:
        if after_id:
            after_block = conn.execute("SELECT sort_order FROM blocks WHERE id=?", (after_id,)).fetchone()
            if after_block:
                sort_order = after_block['sort_order'] + 1
                conn.execute(
                    "UPDATE blocks SET sort_order = sort_order + 1 WHERE page_id=? AND sort_order >= ?",
                    (page_id, sort_order)
                )
            else:
                sort_order = conn.execute(
                    "SELECT COALESCE(MAX(sort_order),0)+1 FROM blocks WHERE page_id=?", (page_id,)
                ).fetchone()[0]
        else:
            sort_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order),0)+1 FROM blocks WHERE page_id=?", (page_id,)
            ).fetchone()[0]
        
        conn.execute(
            "INSERT INTO blocks (id, page_id, type, content, properties, sort_order, indent_level) VALUES (?,?,?,?,?,?,?)",
            (block_id, page_id, block_type, content, properties, sort_order, indent)
        )
        conn.execute("UPDATE pages SET updated_at=? WHERE id=?", (now(), page_id))
        conn.commit()
        row = conn.execute("SELECT * FROM blocks WHERE id=?", (block_id,)).fetchone()
    return jsonify(dict_row(row)), 201

@app.route('/api/blocks/<block_id>', methods=['PUT'])
def update_block(block_id):
    data = request.get_json(force=True)
    with get_db() as conn:
        block = conn.execute("SELECT * FROM blocks WHERE id=?", (block_id,)).fetchone()
        if not block:
            return jsonify({'error': 'Not found'}), 404
        
        updates, params = [], []
        for field in ['type', 'content', 'sort_order', 'indent_level']:
            if field in data:
                updates.append(f"{field}=?")
                params.append(data[field])
        if 'properties' in data:
            updates.append("properties=?")
            params.append(json.dumps(data['properties']))
        if updates:
            params.append(block_id)
            conn.execute(f"UPDATE blocks SET {','.join(updates)} WHERE id=?", params)
            conn.execute("UPDATE pages SET updated_at=? WHERE id=?", (now(), block['page_id']))
            conn.commit()
        
        row = conn.execute("SELECT * FROM blocks WHERE id=?", (block_id,)).fetchone()
    return jsonify(dict_row(row))

@app.route('/api/blocks/<block_id>', methods=['DELETE'])
def delete_block(block_id):
    with get_db() as conn:
        block = conn.execute("SELECT * FROM blocks WHERE id=?", (block_id,)).fetchone()
        if block:
            conn.execute("DELETE FROM blocks WHERE id=?", (block_id,))
            conn.execute("UPDATE pages SET updated_at=? WHERE id=?", (now(), block['page_id']))
            conn.commit()
    return jsonify({'ok': True})

@app.route('/api/pages/<page_id>/blocks/reorder', methods=['PUT'])
def reorder_blocks(page_id):
    data = request.get_json(force=True)
    order = data.get('order', [])
    with get_db() as conn:
        for idx, bid in enumerate(order):
            conn.execute("UPDATE blocks SET sort_order=? WHERE id=? AND page_id=?", (idx, bid, page_id))
        conn.execute("UPDATE pages SET updated_at=? WHERE id=?", (now(), page_id))
        conn.commit()
    return jsonify({'ok': True})

# ── Databases ──────────────────────────────────────────────────────────────

@app.route('/api/databases', methods=['GET'])
def list_databases():
    workspace = request.args.get('workspace')
    with get_db() as conn:
        if workspace:
            rows = conn.execute(
                "SELECT * FROM databases WHERE workspace=? ORDER BY updated_at DESC",
                (workspace,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM databases ORDER BY updated_at DESC").fetchall()
    result = []
    for r in rows:
        d = dict_row(r)
        d['properties_schema'] = json.loads(d['properties_schema']) if d['properties_schema'] else []
        return_views = []
        with get_db() as conn2:
            views = conn2.execute(
                "SELECT * FROM db_views WHERE database_id=? ORDER BY sort_order", (d['id'],)
            ).fetchall()
            return_views = [dict_row(v) for v in views]
            for v in return_views:
                v['config'] = json.loads(v['config']) if v['config'] else {}
        d['views'] = return_views
        result.append(d)
    return jsonify(result)

@app.route('/api/databases', methods=['POST'])
def create_database():
    data = request.get_json(force=True)
    db_id = data.get('id', gen_id())
    title = data.get('title', 'Untitled Database')
    icon = data.get('icon', '')
    workspace = data.get('workspace', 'projects')
    description = data.get('description', '')
    
    # Default schema based on workspace
    if workspace == 'projects':
        default_schema = [
            {'id': gen_id(), 'name': 'Status', 'type': 'select', 
             'options': [
                 {'id': gen_id(), 'name': 'Not Started', 'color': '#6B7280'},
                 {'id': gen_id(), 'name': 'In Progress', 'color': '#3B82F6'},
                 {'id': gen_id(), 'name': 'Done', 'color': '#10B981'},
                 {'id': gen_id(), 'name': 'Blocked', 'color': '#EF4444'}
             ]},
            {'id': gen_id(), 'name': 'Priority', 'type': 'select',
             'options': [
                 {'id': gen_id(), 'name': 'Low', 'color': '#6B7280'},
                 {'id': gen_id(), 'name': 'Medium', 'color': '#F59E0B'},
                 {'id': gen_id(), 'name': 'High', 'color': '#EF4444'},
                 {'id': gen_id(), 'name': 'Urgent', 'color': '#DC2626'}
             ]},
            {'id': gen_id(), 'name': 'Due Date', 'type': 'date'},
            {'id': gen_id(), 'name': 'Assignee', 'type': 'text'},
            {'id': gen_id(), 'name': 'Tags', 'type': 'multi_select',
             'options': [
                 {'id': gen_id(), 'name': 'Bug', 'color': '#EF4444'},
                 {'id': gen_id(), 'name': 'Feature', 'color': '#3B82F6'},
                 {'id': gen_id(), 'name': 'Improvement', 'color': '#10B981'}
             ]}
        ]
        default_view = 'board'
    elif workspace == 'wiki':
        default_schema = [
            {'id': gen_id(), 'name': 'Status', 'type': 'select',
             'options': [
                 {'id': gen_id(), 'name': 'Draft', 'color': '#6B7280'},
                 {'id': gen_id(), 'name': 'In Review', 'color': '#F59E0B'},
                 {'id': gen_id(), 'name': 'Published', 'color': '#10B981'}
             ]},
            {'id': gen_id(), 'name': 'Category', 'type': 'select',
             'options': [
                 {'id': gen_id(), 'name': 'General', 'color': '#6B7280'},
                 {'id': gen_id(), 'name': 'Technical', 'color': '#3B82F6'},
                 {'id': gen_id(), 'name': 'Process', 'color': '#10B981'},
                 {'id': gen_id(), 'name': 'Reference', 'color': '#8B5CF6'}
             ]},
            {'id': gen_id(), 'name': 'Owner', 'type': 'text'},
            {'id': gen_id(), 'name': 'Last Verified', 'type': 'date'},
            {'id': gen_id(), 'name': 'Tags', 'type': 'multi_select', 'options': []}
        ]
        default_view = 'table'
    else:
        default_schema = data.get('properties_schema', [])
        default_view = 'table'
    
    schema = data.get('properties_schema', default_schema)
    
    with get_db() as conn:
        conn.execute(
            "INSERT INTO databases (id, title, icon, workspace, description, properties_schema, default_view) VALUES (?,?,?,?,?,?,?)",
            (db_id, title, icon, workspace, description, json.dumps(schema), default_view)
        )
        # Create default view
        view_id = gen_id()
        view_type = data.get('default_view', default_view)
        group_by = schema[0]['id'] if schema and schema[0]['type'] == 'select' else None
        view_config = {'group_by': group_by} if view_type == 'board' and group_by else {}
        conn.execute(
            "INSERT INTO db_views (id, database_id, name, type, config, sort_order) VALUES (?,?,?,?,?,0)",
            (view_id, db_id, 'Default', view_type, json.dumps(view_config))
        )
        conn.commit()
        row = conn.execute("SELECT * FROM databases WHERE id=?", (db_id,)).fetchone()
    result = dict_row(row)
    result['properties_schema'] = json.loads(result['properties_schema'])
    return jsonify(result), 201

@app.route('/api/databases/<db_id>', methods=['GET'])
def get_database(db_id):
    with get_db() as conn:
        db = conn.execute("SELECT * FROM databases WHERE id=?", (db_id,)).fetchone()
        if not db:
            return jsonify({'error': 'Not found'}), 404
        items = conn.execute(
            "SELECT * FROM db_items WHERE database_id=? ORDER BY sort_order, created_at", (db_id,)
        ).fetchall()
        views = conn.execute(
            "SELECT * FROM db_views WHERE database_id=? ORDER BY sort_order", (db_id,)
        ).fetchall()
    result = dict_row(db)
    result['properties_schema'] = json.loads(result['properties_schema']) if result['properties_schema'] else []
    result['items'] = []
    for item in items:
        d = dict_row(item)
        d['properties'] = json.loads(d['properties']) if d['properties'] else {}
        result['items'].append(d)
    result['views'] = []
    for v in views:
        vd = dict_row(v)
        vd['config'] = json.loads(vd['config']) if vd['config'] else {}
        result['views'].append(vd)
    return jsonify(result)

@app.route('/api/databases/<db_id>', methods=['PUT'])
def update_database(db_id):
    data = request.get_json(force=True)
    with get_db() as conn:
        updates, params = [], []
        for field in ['title', 'icon', 'description', 'default_view']:
            if field in data:
                updates.append(f"{field}=?")
                params.append(data[field])
        if 'properties_schema' in data:
            updates.append("properties_schema=?")
            params.append(json.dumps(data['properties_schema']))
        if updates:
            updates.append("updated_at=?")
            params.append(now())
            params.append(db_id)
            conn.execute(f"UPDATE databases SET {','.join(updates)} WHERE id=?", params)
            conn.commit()
        row = conn.execute("SELECT * FROM databases WHERE id=?", (db_id,)).fetchone()
    result = dict_row(row)
    result['properties_schema'] = json.loads(result['properties_schema']) if result['properties_schema'] else []
    return jsonify(result)

@app.route('/api/databases/<db_id>', methods=['DELETE'])
def delete_database(db_id):
    with get_db() as conn:
        # Delete associated pages for items
        items = conn.execute("SELECT page_id FROM db_items WHERE database_id=? AND page_id IS NOT NULL", (db_id,)).fetchall()
        for item in items:
            if item['page_id']:
                conn.execute("DELETE FROM blocks WHERE page_id=?", (item['page_id'],))
                conn.execute("DELETE FROM pages WHERE id=?", (item['page_id'],))
        conn.execute("DELETE FROM db_items WHERE database_id=?", (db_id,))
        conn.execute("DELETE FROM db_views WHERE database_id=?", (db_id,))
        conn.execute("DELETE FROM databases WHERE id=?", (db_id,))
        conn.commit()
    return jsonify({'ok': True})

# ── Database Items ─────────────────────────────────────────────────────────

@app.route('/api/databases/<db_id>/items', methods=['POST'])
def create_db_item(db_id):
    data = request.get_json(force=True)
    item_id = data.get('id', gen_id())
    title = data.get('title', 'Untitled')
    icon = data.get('icon', '')
    properties = data.get('properties', {})
    
    with get_db() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order),0) FROM db_items WHERE database_id=?", (db_id,)
        ).fetchone()[0]
        
        # Create associated page for item content
        page_id = gen_id()
        conn.execute(
            "INSERT INTO pages (id, title, icon, workspace) VALUES (?,?,?,'_db_item')",
            (page_id, title, icon)
        )
        block_id = gen_id()
        conn.execute(
            "INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,'text','',0)",
            (block_id, page_id)
        )
        
        conn.execute(
            "INSERT INTO db_items (id, database_id, title, icon, properties, page_id, sort_order) VALUES (?,?,?,?,?,?,?)",
            (item_id, db_id, title, icon, json.dumps(properties), page_id, max_order + 1)
        )
        conn.execute("UPDATE databases SET updated_at=? WHERE id=?", (now(), db_id))
        conn.commit()
        row = conn.execute("SELECT * FROM db_items WHERE id=?", (item_id,)).fetchone()
    result = dict_row(row)
    result['properties'] = json.loads(result['properties']) if result['properties'] else {}
    return jsonify(result), 201

@app.route('/api/databases/<db_id>/items/<item_id>', methods=['PUT'])
def update_db_item(db_id, item_id):
    data = request.get_json(force=True)
    with get_db() as conn:
        item = conn.execute("SELECT * FROM db_items WHERE id=? AND database_id=?", (item_id, db_id)).fetchone()
        if not item:
            return jsonify({'error': 'Not found'}), 404
        
        updates, params = [], []
        for field in ['title', 'icon', 'sort_order']:
            if field in data:
                updates.append(f"{field}=?")
                params.append(data[field])
        if 'properties' in data:
            # Merge with existing
            existing = json.loads(item['properties']) if item['properties'] else {}
            existing.update(data['properties'])
            updates.append("properties=?")
            params.append(json.dumps(existing))
        if 'title' in data and item['page_id']:
            conn.execute("UPDATE pages SET title=? WHERE id=?", (data['title'], item['page_id']))
        if updates:
            updates.append("updated_at=?")
            params.append(now())
            params.append(item_id)
            conn.execute(f"UPDATE db_items SET {','.join(updates)} WHERE id=?", params)
            conn.execute("UPDATE databases SET updated_at=? WHERE id=?", (now(), db_id))
            conn.commit()
        row = conn.execute("SELECT * FROM db_items WHERE id=?", (item_id,)).fetchone()
    result = dict_row(row)
    result['properties'] = json.loads(result['properties']) if result['properties'] else {}
    return jsonify(result)

@app.route('/api/databases/<db_id>/items/<item_id>', methods=['DELETE'])
def delete_db_item(db_id, item_id):
    with get_db() as conn:
        item = conn.execute("SELECT * FROM db_items WHERE id=?", (item_id,)).fetchone()
        if item and item['page_id']:
            conn.execute("DELETE FROM blocks WHERE page_id=?", (item['page_id'],))
            conn.execute("DELETE FROM pages WHERE id=?", (item['page_id'],))
        conn.execute("DELETE FROM db_items WHERE id=?", (item_id,))
        conn.execute("UPDATE databases SET updated_at=? WHERE id=?", (now(), db_id))
        conn.commit()
    return jsonify({'ok': True})

@app.route('/api/databases/<db_id>/items/reorder', methods=['PUT'])
def reorder_db_items(db_id):
    data = request.get_json(force=True)
    order = data.get('order', [])
    with get_db() as conn:
        for idx, item_id in enumerate(order):
            conn.execute("UPDATE db_items SET sort_order=? WHERE id=?", (idx, item_id))
        conn.commit()
    return jsonify({'ok': True})

# ── Database Views ─────────────────────────────────────────────────────────

@app.route('/api/databases/<db_id>/views', methods=['POST'])
def create_db_view(db_id):
    data = request.get_json(force=True)
    view_id = gen_id()
    with get_db() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order),0) FROM db_views WHERE database_id=?", (db_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO db_views (id, database_id, name, type, config, sort_order) VALUES (?,?,?,?,?,?)",
            (view_id, db_id, data.get('name', 'New View'), data.get('type', 'table'),
             json.dumps(data.get('config', {})), max_order + 1)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM db_views WHERE id=?", (view_id,)).fetchone()
    result = dict_row(row)
    result['config'] = json.loads(result['config']) if result['config'] else {}
    return jsonify(result), 201

@app.route('/api/databases/<db_id>/views/<view_id>', methods=['PUT'])
def update_db_view(db_id, view_id):
    data = request.get_json(force=True)
    with get_db() as conn:
        updates, params = [], []
        for field in ['name', 'type', 'sort_order']:
            if field in data:
                updates.append(f"{field}=?")
                params.append(data[field])
        if 'config' in data:
            updates.append("config=?")
            params.append(json.dumps(data['config']))
        if updates:
            params.append(view_id)
            conn.execute(f"UPDATE db_views SET {','.join(updates)} WHERE id=?", params)
            conn.commit()
        row = conn.execute("SELECT * FROM db_views WHERE id=?", (view_id,)).fetchone()
    result = dict_row(row)
    result['config'] = json.loads(result['config']) if result['config'] else {}
    return jsonify(result)

# ── Search ─────────────────────────────────────────────────────────────────

@app.route('/api/search', methods=['GET'])
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    with get_db() as conn:
        pages = conn.execute(
            "SELECT id, title, icon, parent_id, workspace FROM pages WHERE title LIKE ? AND workspace != '_db_item' LIMIT 20",
            (f'%{q}%',)
        ).fetchall()
        blocks = conn.execute(
            """SELECT b.page_id, b.content, p.title, p.icon, p.workspace
               FROM blocks b JOIN pages p ON b.page_id = p.id 
               WHERE b.content LIKE ? AND p.workspace != '_db_item' LIMIT 20""",
            (f'%{q}%',)
        ).fetchall()
        db_items = conn.execute(
            """SELECT i.id, i.title, i.icon, i.database_id, d.title as db_title
               FROM db_items i JOIN databases d ON i.database_id = d.id
               WHERE i.title LIKE ? LIMIT 10""",
            (f'%{q}%',)
        ).fetchall()
    
    results = []
    seen = set()
    for p in pages:
        seen.add(p['id'])
        results.append({'type': 'page', 'page_id': p['id'], 'title': p['title'], 
                       'icon': p['icon'], 'workspace': p['workspace']})
    for b in blocks:
        if b['page_id'] not in seen:
            seen.add(b['page_id'])
            results.append({'type': 'block', 'page_id': b['page_id'], 'title': b['title'],
                          'icon': b['icon'], 'snippet': b['content'][:100], 'workspace': b['workspace']})
    for i in db_items:
        results.append({'type': 'db_item', 'item_id': i['id'], 'title': i['title'],
                       'icon': i['icon'], 'database_id': i['database_id'], 'db_title': i['db_title']})
    return jsonify(results)

# ── AI Chat Agent ──────────────────────────────────────────────────────────

import httpx, re

# Load API key from OpenClaw config
def get_api_config():
    """Use OpenClaw Gateway's OpenAI-compatible chat completions endpoint."""
    config_path = os.path.expanduser('~/.openclaw/openclaw.json')
    try:
        with open(config_path) as f:
            config = json.load(f)
        gw = config.get('gateway', {})
        token = gw.get('auth', {}).get('token', '')
        port = gw.get('port', 18789)
        return {
            'api_key': token,
            'base_url': f'http://127.0.0.1:{port}',
            'mode': 'openai',  # Use OpenAI-compatible API
        }
    except:
        return {'api_key': '', 'base_url': 'http://127.0.0.1:18789', 'mode': 'openai'}

# Chat configuration
CHAT_CONFIG = {
    'model': 'anthropic-cloud/claude-opus-4-6-20260205',
    'max_tokens': 4096,
}

# Gather all content from the app for RAG context
def gather_all_content():
    """Build a comprehensive context string of all app content."""
    sections = []
    with get_db() as conn:
        # Docs
        pages = conn.execute(
            "SELECT * FROM pages WHERE workspace='docs' OR workspace IS NULL ORDER BY updated_at DESC"
        ).fetchall()
        if pages:
            sections.append("## DOCS (Pages)")
            for p in pages:
                blocks = conn.execute(
                    "SELECT type, content FROM blocks WHERE page_id=? ORDER BY sort_order", (p['id'],)
                ).fetchall()
                content = '\n'.join(
                    b['content'] for b in blocks if b['content'] and b['type'] not in ('divider',)
                )
                if content.strip():
                    sections.append(f"\n### Page: {p['title']} (id: {p['id']})\n{content}")
                else:
                    sections.append(f"\n### Page: {p['title']} (id: {p['id']})\n[Empty page]")
        
        # Databases (Projects + Wiki)
        dbs = conn.execute("SELECT * FROM databases ORDER BY updated_at DESC").fetchall()
        for db in dbs:
            db_dict = dict_row(db)
            schema = json.loads(db_dict['properties_schema']) if db_dict['properties_schema'] else []
            items = conn.execute(
                "SELECT * FROM db_items WHERE database_id=? ORDER BY sort_order", (db_dict['id'],)
            ).fetchall()
            
            ws_label = 'PROJECT' if db_dict['workspace'] == 'projects' else 'KNOWLEDGE BASE'
            sections.append(f"\n## {ws_label}: {db_dict['title']} (id: {db_dict['id']})")
            if db_dict.get('description'):
                sections.append(f"Description: {db_dict['description']}")
            sections.append(f"Properties: {', '.join(p['name']+' ('+p['type']+')' for p in schema)}")
            
            for item in items:
                item_dict = dict_row(item)
                props = json.loads(item_dict['properties']) if item_dict['properties'] else {}
                prop_str = ', '.join(f"{next((s['name'] for s in schema if s['id']==k), k)}: {v}" 
                                    for k, v in props.items() if v)
                sections.append(f"  - {item_dict['title']} (id: {item_dict['id']}) [{prop_str}]")
                # Get item page content if exists
                if item_dict.get('page_id'):
                    blocks = conn.execute(
                        "SELECT type, content FROM blocks WHERE page_id=? ORDER BY sort_order",
                        (item_dict['page_id'],)
                    ).fetchall()
                    content = '\n    '.join(b['content'] for b in blocks if b['content'])
                    if content.strip():
                        sections.append(f"    Content: {content}")
    
    return '\n'.join(sections) if sections else "[No content in the app yet]"

# Tool definitions for the agent
TOOLS = [
    {
        "name": "search_content",
        "description": "Search across all pages, blocks, and database items. Use this to find specific information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_page",
        "description": "Create a new page in Docs with optional content blocks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Page title"},
                "icon": {"type": "string", "description": "Lucide icon name (e.g. 'file-text', 'lightbulb', 'target')"},
                "blocks": {
                    "type": "array",
                    "description": "Content blocks to add",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["text", "h1", "h2", "h3", "bullet", "numbered", "todo", "quote", "callout", "code", "divider"]},
                            "content": {"type": "string"}
                        },
                        "required": ["type", "content"]
                    }
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "edit_page",
        "description": "Edit an existing page's title, icon, or replace/append blocks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID to edit"},
                "title": {"type": "string", "description": "New title (optional)"},
                "icon": {"type": "string", "description": "New icon (optional)"},
                "append_blocks": {
                    "type": "array",
                    "description": "Blocks to append at the end",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "content": {"type": "string"}
                        }
                    }
                }
            },
            "required": ["page_id"]
        }
    },
    {
        "name": "create_project_item",
        "description": "Create a new item in a project database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database_id": {"type": "string", "description": "Project database ID"},
                "title": {"type": "string", "description": "Item title"},
                "properties": {
                    "type": "object",
                    "description": "Property values keyed by property ID"
                }
            },
            "required": ["database_id", "title"]
        }
    },
    {
        "name": "update_project_item",
        "description": "Update a project/wiki item's title or properties.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database_id": {"type": "string"},
                "item_id": {"type": "string"},
                "title": {"type": "string"},
                "properties": {"type": "object"}
            },
            "required": ["database_id", "item_id"]
        }
    },
    {
        "name": "create_database",
        "description": "Create a new project or knowledge base database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "workspace": {"type": "string", "enum": ["projects", "wiki"]},
                "description": {"type": "string"}
            },
            "required": ["title", "workspace"]
        }
    },
    {
        "name": "delete_page",
        "description": "Delete a page by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string"}
            },
            "required": ["page_id"]
        }
    },
    {
        "name": "get_page_content",
        "description": "Get full content of a specific page including all blocks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string"}
            },
            "required": ["page_id"]
        }
    }
]

def execute_tool(name, input_data):
    """Execute a tool call and return the result."""
    try:
        if name == "search_content":
            q = input_data['query']
            with get_db() as conn:
                pages = conn.execute(
                    "SELECT id, title, icon FROM pages WHERE title LIKE ? AND workspace != '_db_item' LIMIT 10",
                    (f'%{q}%',)
                ).fetchall()
                blocks = conn.execute(
                    """SELECT b.page_id, b.content, p.title FROM blocks b 
                       JOIN pages p ON b.page_id = p.id 
                       WHERE b.content LIKE ? AND p.workspace != '_db_item' LIMIT 10""",
                    (f'%{q}%',)
                ).fetchall()
                items = conn.execute(
                    "SELECT i.id, i.title, d.title as db_title FROM db_items i JOIN databases d ON i.database_id = d.id WHERE i.title LIKE ? LIMIT 10",
                    (f'%{q}%',)
                ).fetchall()
            results = []
            for p in pages: results.append(f"Page: {p['title']} (id: {p['id']})")
            for b in blocks: results.append(f"In '{b['title']}': {b['content'][:200]}")
            for i in items: results.append(f"Item '{i['title']}' in {i['db_title']}")
            return '\n'.join(results) if results else "No results found."

        elif name == "create_page":
            page_id = gen_id()
            title = input_data['title']
            icon = input_data.get('icon', 'file-text')
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO pages (id, title, icon, workspace, sort_order) VALUES (?,?,?,'docs',0)",
                    (page_id, title, icon)
                )
                blocks = input_data.get('blocks', [{'type': 'text', 'content': ''}])
                for i, block in enumerate(blocks):
                    bid = gen_id()
                    conn.execute(
                        "INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,?,?,?)",
                        (bid, page_id, block['type'], block['content'], i)
                    )
                conn.commit()
            return json.dumps({"created": page_id, "title": title})

        elif name == "edit_page":
            page_id = input_data['page_id']
            with get_db() as conn:
                if 'title' in input_data:
                    conn.execute("UPDATE pages SET title=?, updated_at=? WHERE id=?", (input_data['title'], now(), page_id))
                if 'icon' in input_data:
                    conn.execute("UPDATE pages SET icon=?, updated_at=? WHERE id=?", (input_data['icon'], now(), page_id))
                if 'append_blocks' in input_data:
                    max_order = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM blocks WHERE page_id=?", (page_id,)).fetchone()[0]
                    for i, block in enumerate(input_data['append_blocks']):
                        bid = gen_id()
                        conn.execute(
                            "INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,?,?,?)",
                            (bid, page_id, block['type'], block['content'], max_order + 1 + i)
                        )
                conn.commit()
            return json.dumps({"updated": page_id})

        elif name == "create_project_item":
            db_id = input_data['database_id']
            item_id = gen_id()
            title = input_data['title']
            props = input_data.get('properties', {})
            with get_db() as conn:
                max_order = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM db_items WHERE database_id=?", (db_id,)).fetchone()[0]
                page_id = gen_id()
                conn.execute("INSERT INTO pages (id, title, workspace) VALUES (?,?,'_db_item')", (page_id, title))
                conn.execute("INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,'text','',0)", (gen_id(), page_id))
                conn.execute(
                    "INSERT INTO db_items (id, database_id, title, properties, page_id, sort_order) VALUES (?,?,?,?,?,?)",
                    (item_id, db_id, title, json.dumps(props), page_id, max_order + 1)
                )
                conn.commit()
            return json.dumps({"created": item_id, "title": title})

        elif name == "update_project_item":
            db_id = input_data['database_id']
            item_id = input_data['item_id']
            with get_db() as conn:
                if 'title' in input_data:
                    conn.execute("UPDATE db_items SET title=?, updated_at=? WHERE id=?", (input_data['title'], now(), item_id))
                if 'properties' in input_data:
                    existing = conn.execute("SELECT properties FROM db_items WHERE id=?", (item_id,)).fetchone()
                    props = json.loads(existing['properties']) if existing and existing['properties'] else {}
                    props.update(input_data['properties'])
                    conn.execute("UPDATE db_items SET properties=?, updated_at=? WHERE id=?", (json.dumps(props), now(), item_id))
                conn.commit()
            return json.dumps({"updated": item_id})

        elif name == "create_database":
            # Delegate to existing endpoint logic
            from flask import Request
            db_id = gen_id()
            title = input_data['title']
            workspace = input_data['workspace']
            desc = input_data.get('description', '')
            # Generate default schema
            if workspace == 'projects':
                schema = [
                    {'id': gen_id(), 'name': 'Status', 'type': 'select',
                     'options': [{'id': gen_id(), 'name': s, 'color': c} for s, c in
                                [('Not Started','#6B7280'),('In Progress','#3B82F6'),('Done','#10B981'),('Blocked','#EF4444')]]},
                    {'id': gen_id(), 'name': 'Priority', 'type': 'select',
                     'options': [{'id': gen_id(), 'name': s, 'color': c} for s, c in
                                [('Low','#6B7280'),('Medium','#F59E0B'),('High','#EF4444')]]},
                    {'id': gen_id(), 'name': 'Due Date', 'type': 'date'},
                ]
            else:
                schema = [
                    {'id': gen_id(), 'name': 'Status', 'type': 'select',
                     'options': [{'id': gen_id(), 'name': s, 'color': c} for s, c in
                                [('Draft','#6B7280'),('In Review','#F59E0B'),('Published','#10B981')]]},
                    {'id': gen_id(), 'name': 'Category', 'type': 'select', 'options': []},
                ]
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO databases (id, title, icon, workspace, description, properties_schema, default_view) VALUES (?,?,?,?,?,?,?)",
                    (db_id, title, 'layout-grid' if workspace=='projects' else 'book-open',
                     workspace, desc, json.dumps(schema), 'board' if workspace=='projects' else 'table')
                )
                view_id = gen_id()
                vtype = 'board' if workspace == 'projects' else 'table'
                group_by = schema[0]['id'] if schema[0]['type'] == 'select' else None
                conn.execute(
                    "INSERT INTO db_views (id, database_id, name, type, config, sort_order) VALUES (?,?,?,?,?,0)",
                    (view_id, db_id, 'Default', vtype, json.dumps({'group_by': group_by} if group_by else {}))
                )
                conn.commit()
            return json.dumps({"created": db_id, "title": title, "workspace": workspace})

        elif name == "delete_page":
            page_id = input_data['page_id']
            with get_db() as conn:
                conn.execute("DELETE FROM blocks WHERE page_id=?", (page_id,))
                conn.execute("DELETE FROM pages WHERE id=?", (page_id,))
                conn.commit()
            return json.dumps({"deleted": page_id})

        elif name == "get_page_content":
            page_id = input_data['page_id']
            with get_db() as conn:
                page = conn.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()
                if not page:
                    return "Page not found."
                blocks = conn.execute(
                    "SELECT type, content, properties FROM blocks WHERE page_id=? ORDER BY sort_order", (page_id,)
                ).fetchall()
            result = f"# {page['title']}\n\n"
            for b in blocks:
                prefix = {'h1': '# ', 'h2': '## ', 'h3': '### ', 'bullet': '- ', 'quote': '> ', 'code': '```\n'}.get(b['type'], '')
                suffix = '\n```' if b['type'] == 'code' else ''
                if b['type'] == 'numbered':
                    prefix = '1. '
                if b['type'] == 'todo':
                    props = json.loads(b['properties']) if b['properties'] else {}
                    prefix = '[x] ' if props.get('checked') else '[ ] '
                result += f"{prefix}{b['content']}{suffix}\n"
            return result

        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error executing {name}: {str(e)}"


# Chat history stored in memory (per-session, resets on restart)
chat_histories = {}

@app.route('/api/chat/config', methods=['GET'])
def get_chat_config():
    return jsonify(CHAT_CONFIG)

@app.route('/api/chat/config', methods=['PUT'])
def update_chat_config():
    data = request.get_json(force=True)
    if 'model' in data:
        CHAT_CONFIG['model'] = data['model']
    if 'max_tokens' in data:
        CHAT_CONFIG['max_tokens'] = data['max_tokens']
    return jsonify(CHAT_CONFIG)

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True)
    message = data.get('message', '').strip()
    session_id = data.get('session_id', 'default')
    
    if not message:
        return jsonify({'error': 'Empty message'}), 400
    
    api_config = get_api_config()
    if not api_config['api_key']:
        return jsonify({'error': 'No API key configured'}), 500
    
    # Get or create chat history
    if session_id not in chat_histories:
        chat_histories[session_id] = []
    history = chat_histories[session_id]
    
    # Build context
    all_content = gather_all_content()
    
    system_prompt = f"""You are Brain Notes AI — an intelligent assistant embedded in a note-taking application.
You have full access to all content in the app and can create, edit, search, and manage pages, projects, and knowledge base items.

## Current App Content
{all_content}

## Actions
To perform actions, include a JSON block in your response wrapped in ```action tags. You can include multiple action blocks. Always include a text response alongside actions.

Available actions:

### create_page
```action
{{"action":"create_page","title":"Page Title","icon":"lucide-icon-name","blocks":[{{"type":"h1","content":"Heading"}},{{"type":"bullet","content":"Item 1"}},{{"type":"todo","content":"Task 1"}}]}}
```
Block types: text, h1, h2, h3, bullet, numbered, todo, quote, callout, code, divider

### edit_page
```action
{{"action":"edit_page","page_id":"id","title":"New Title","append_blocks":[{{"type":"text","content":"Added text"}}]}}
```

### create_project_item
```action
{{"action":"create_project_item","database_id":"id","title":"Item Title","properties":{{"prop_id":"value"}}}}
```

### create_database
```action
{{"action":"create_database","title":"DB Title","workspace":"projects|wiki","description":"..."}}
```

### delete_page
```action
{{"action":"delete_page","page_id":"id"}}
```

## Guidelines
- Be concise and helpful
- When creating content, use appropriate block types
- Use Lucide icon names for page icons (e.g., 'target', 'lightbulb', 'bar-chart-3', 'flask-conical', 'clipboard-list')
- Always respond with a human-readable message. Put action blocks at the END of your response.
- For analysis tasks, create a well-structured page with the results
"""
    
    # Add user message to history
    history.append({"role": "user", "content": message})
    
    # Keep history manageable (last 20 messages)
    if len(history) > 20:
        history = history[-20:]
        chat_histories[session_id] = history
    
    # Call LLM
    try:
        response = call_claude(api_config, system_prompt, history)
    except Exception as e:
        logger.error(f"LLM API error: {e}")
        return jsonify({'error': str(e)}), 500
    
    # Extract text
    text_parts = []
    for block in response.get('content', []):
        if block.get('type') == 'text':
            text_parts.append(block['text'])
    
    full_response = '\n'.join(text_parts)
    
    # Parse and execute action blocks
    tool_results = []
    action_pattern = re.compile(r'```action\s*\n(.*?)\n```', re.DOTALL)
    for match in action_pattern.finditer(full_response):
        try:
            action_data = json.loads(match.group(1).strip())
            action_name = action_data.pop('action', '')
            if action_name and action_name in ('create_page', 'edit_page', 'create_project_item', 
                                                 'update_project_item', 'create_database', 'delete_page',
                                                 'search_content', 'get_page_content'):
                result = execute_tool(action_name, action_data)
                tool_results.append({"tool": action_name, "input": action_data, "result": result})
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse/execute action: {e}")
    
    # Clean action blocks from the displayed message
    assistant_message = action_pattern.sub('', full_response).strip()
    
    history.append({"role": "assistant", "content": full_response})
    chat_histories[session_id] = history
    
    return jsonify({
        'response': assistant_message,
        'tool_results': tool_results,
        'model': CHAT_CONFIG['model'],
    })


@app.route('/api/chat/history', methods=['GET'])
def get_chat_history():
    session_id = request.args.get('session_id', 'default')
    history = chat_histories.get(session_id, [])
    # Flatten to simple messages
    messages = []
    for msg in history:
        if msg['role'] == 'user':
            if isinstance(msg['content'], str):
                messages.append({'role': 'user', 'content': msg['content']})
        elif msg['role'] == 'assistant':
            text = ''
            if isinstance(msg['content'], list):
                text = ' '.join(b.get('text', '') for b in msg['content'] if b.get('type') == 'text')
            elif isinstance(msg['content'], str):
                text = msg['content']
            if text.strip():
                messages.append({'role': 'assistant', 'content': text})
    return jsonify(messages)


@app.route('/api/chat/clear', methods=['POST'])
def clear_chat():
    session_id = request.get_json(force=True).get('session_id', 'default')
    chat_histories.pop(session_id, None)
    return jsonify({'ok': True})


def call_claude(api_config, system, messages):
    """Call LLM via OpenClaw Gateway (OpenAI-compatible chat completions)."""
    url = f"{api_config['base_url']}/v1/chat/completions"
    headers = {
        'Authorization': f"Bearer {api_config['api_key']}",
        'content-type': 'application/json',
    }
    
    oai_messages = [{"role": "system", "content": system}]
    for msg in messages:
        if isinstance(msg.get('content'), str):
            oai_messages.append({"role": msg['role'], "content": msg['content']})
    
    model = CHAT_CONFIG['model']
    if '/' not in model:
        model = f"anthropic-cloud/{model}"
    
    body = {
        'model': model,
        'max_tokens': CHAT_CONFIG['max_tokens'],
        'messages': oai_messages,
    }
    
    with httpx.Client(timeout=120) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        oai_resp = r.json()
    
    choice = oai_resp.get('choices', [{}])[0]
    text = choice.get('message', {}).get('content', '')
    
    return {
        'content': [{"type": "text", "text": text}],
        'stop_reason': 'end_turn',
    }


# ── Run ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    logger.info("Starting Brain Notes on port 5006")
    app.run(host='0.0.0.0', port=5006, debug=False)
