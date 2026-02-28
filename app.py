#!/usr/bin/env python3.12
"""Brain Notes — Notion Clone Backend"""
import json, logging, os, sqlite3, uuid
from datetime import datetime
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

            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
                id, title, content='pages', content_rowid=rowid
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS blocks_fts USING fts5(
                id, content, content='blocks', content_rowid=rowid
            );
        """)
        conn.commit()
    logger.info("Database initialized")

init_db()

def dict_row(row):
    if row is None: return None
    return dict(row)

def now():
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

# ── Pages ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/pages', methods=['GET'])
def list_pages():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM pages ORDER BY is_favorite DESC, sort_order ASC, updated_at DESC"
        ).fetchall()
    return jsonify([dict_row(r) for r in rows])

@app.route('/api/pages', methods=['POST'])
def create_page():
    data = request.get_json(force=True)
    page_id = data.get('id', str(uuid.uuid4())[:8])
    title = data.get('title', 'Untitled')
    parent_id = data.get('parent_id')
    icon = data.get('icon', '')
    
    with get_db() as conn:
        # Get max sort_order for siblings
        if parent_id:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order),0) FROM pages WHERE parent_id=?", (parent_id,)
            ).fetchone()[0]
        else:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order),0) FROM pages WHERE parent_id IS NULL"
            ).fetchone()[0]
        
        conn.execute(
            "INSERT INTO pages (id, title, icon, parent_id, sort_order) VALUES (?,?,?,?,?)",
            (page_id, title, icon, parent_id, max_order + 1)
        )
        # Create initial empty block
        block_id = str(uuid.uuid4())[:8]
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
        # Get child pages
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
        
        updates = []
        params = []
        for field in ['title', 'icon', 'cover', 'parent_id', 'sort_order', 'is_favorite']:
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
        # Recursively delete children
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
    block_id = data.get('id', str(uuid.uuid4())[:8])
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
                # Shift subsequent blocks
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

# ── Search ─────────────────────────────────────────────────────────────────

@app.route('/api/search', methods=['GET'])
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    with get_db() as conn:
        # Search page titles
        pages = conn.execute(
            "SELECT id, title, icon, parent_id FROM pages WHERE title LIKE ? LIMIT 20",
            (f'%{q}%',)
        ).fetchall()
        # Search block content
        blocks = conn.execute(
            """SELECT b.page_id, b.content, p.title, p.icon 
               FROM blocks b JOIN pages p ON b.page_id = p.id 
               WHERE b.content LIKE ? LIMIT 20""",
            (f'%{q}%',)
        ).fetchall()
    
    results = []
    seen_pages = set()
    for p in pages:
        seen_pages.add(p['id'])
        results.append({'type': 'page', 'page_id': p['id'], 'title': p['title'], 'icon': p['icon']})
    for b in blocks:
        if b['page_id'] not in seen_pages:
            seen_pages.add(b['page_id'])
            snippet = b['content'][:100]
            results.append({'type': 'block', 'page_id': b['page_id'], 'title': b['title'],
                          'icon': b['icon'], 'snippet': snippet})
    return jsonify(results)

# ── Run ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    logger.info("Starting Brain Notes (Notion) on port 5006")
    app.run(host='0.0.0.0', port=5006, debug=False)
