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

# ── Run ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    logger.info("Starting Brain Notes on port 5006")
    app.run(host='0.0.0.0', port=5006, debug=False)
