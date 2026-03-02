#!/usr/bin/env python3.12
"""Brain Notes — Notion Clone Backend with Docs, Projects, Knowledge Base"""
import json, logging, os, sqlite3, uuid, functools, secrets
from datetime import datetime, date
from flask import Flask, request, jsonify, send_from_directory, session, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app, supports_credentials=True)
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

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL DEFAULT 'default',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id);

            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
                id, title, content='pages', content_rowid=rowid
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS blocks_fts USING fts5(
                id, content, content='blocks', content_rowid=rowid
            );

            -- Users
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE DEFAULT '',
                password_hash TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Teams
            CREATE TABLE IF NOT EXISTS teams (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_by TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            -- Team members
            CREATE TABLE IF NOT EXISTS team_members (
                team_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT DEFAULT 'member',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (team_id, user_id),
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- Permissions (granular sharing)
            CREATE TABLE IF NOT EXISTS permissions (
                id TEXT PRIMARY KEY,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                grantee_type TEXT NOT NULL,
                grantee_id TEXT NOT NULL,
                permission TEXT NOT NULL,
                granted_by TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (granted_by) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_perm_resource ON permissions(resource_type, resource_id);
            CREATE INDEX IF NOT EXISTS idx_perm_grantee ON permissions(grantee_type, grantee_id);
        """)
        # Migrations
        try:
            conn.execute("SELECT workspace FROM pages LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE pages ADD COLUMN workspace TEXT DEFAULT 'docs'")
        # Add owner columns to pages and databases
        for table in ('pages', 'databases'):
            try:
                conn.execute(f"SELECT owner_id FROM {table} LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN owner_id TEXT DEFAULT ''")
                conn.execute(f"ALTER TABLE {table} ADD COLUMN owner_type TEXT DEFAULT 'user'")
        # Add owner to chat_messages
        try:
            conn.execute("SELECT user_id FROM chat_messages LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE chat_messages ADD COLUMN user_id TEXT DEFAULT ''")
        conn.commit()
        # Create default admin if no users exist
        admin = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
        if not admin:
            admin_id = gen_id()
            conn.execute(
                "INSERT INTO users (id, username, email, password_hash, display_name, role) VALUES (?,?,?,?,?,?)",
                (admin_id, 'admin', '', generate_password_hash('admin'), 'Admin', 'admin')
            )
            # Assign existing content to admin
            conn.execute("UPDATE pages SET owner_id=?, owner_type='user' WHERE owner_id=''", (admin_id,))
            conn.execute("UPDATE databases SET owner_id=?, owner_type='user' WHERE owner_id=''", (admin_id,))
            conn.commit()
            logger.info(f"Created default admin user (username: admin, password: admin)")
    logger.info("Database initialized")

def dict_row(row):
    if row is None: return None
    return dict(row)

def now():
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

def gen_id():
    return str(uuid.uuid4())[:8]

init_db()

# ── Auth ───────────────────────────────────────────────────────────────────

def get_current_user():
    """Get the current logged-in user from session. Returns dict or None."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    with get_db() as conn:
        row = conn.execute("SELECT id, username, email, display_name, role FROM users WHERE id=?", (user_id,)).fetchone()
    return dict_row(row)

def login_required(f):
    """Decorator: require authentication. Sets g.user."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        g.user = user
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Decorator: require admin role."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        if user['role'] != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated

def get_user_team_ids(user_id):
    """Get list of team IDs a user belongs to."""
    with get_db() as conn:
        rows = conn.execute("SELECT team_id FROM team_members WHERE user_id=?", (user_id,)).fetchall()
    return [r['team_id'] for r in rows]

def can_access_resource(user, resource_type, resource_id, required_permission='read'):
    """Check if a user can access a resource. Admins can access everything."""
    if user['role'] == 'admin':
        return True
    with get_db() as conn:
        # Check ownership
        table = 'pages' if resource_type == 'page' else 'databases'
        row = conn.execute(f"SELECT owner_id, owner_type FROM {table} WHERE id=?", (resource_id,)).fetchone()
        if not row:
            return False
        owner_id, owner_type = row['owner_id'], row['owner_type']
        # User owns it directly
        if owner_type == 'user' and owner_id == user['id']:
            return True
        # User is in the owning team
        if owner_type == 'team':
            member = conn.execute(
                "SELECT role FROM team_members WHERE team_id=? AND user_id=?",
                (owner_id, user['id'])
            ).fetchone()
            if member:
                # Team owners/admins get full access, members get read+write
                if member['role'] in ('owner', 'admin'):
                    return True
                if required_permission in ('read', 'write'):
                    return True
        # Check explicit permissions
        perm_levels = {'read': ['read', 'write', 'delete'], 'write': ['write', 'delete'], 'delete': ['delete']}
        valid_perms = perm_levels.get(required_permission, [required_permission])
        placeholders = ','.join('?' * len(valid_perms))
        # Direct user permission
        perm = conn.execute(
            f"SELECT id FROM permissions WHERE resource_type=? AND resource_id=? "
            f"AND grantee_type='user' AND grantee_id=? AND permission IN ({placeholders})",
            (resource_type, resource_id, user['id'], *valid_perms)
        ).fetchone()
        if perm:
            return True
        # Team-based permission
        team_ids = get_user_team_ids(user['id'])
        for tid in team_ids:
            perm = conn.execute(
                f"SELECT id FROM permissions WHERE resource_type=? AND resource_id=? "
                f"AND grantee_type='team' AND grantee_id=? AND permission IN ({placeholders})",
                (resource_type, resource_id, tid, *valid_perms)
            ).fetchone()
            if perm:
                return True
    return False

def get_accessible_filter(user, table='pages'):
    """Return (WHERE clause, params) for filtering resources a user can access."""
    if user['role'] == 'admin':
        return "1=1", []
    resource_type = 'page' if table == 'pages' else 'database'
    team_ids = get_user_team_ids(user['id'])
    conditions = [f"({table}.owner_type='user' AND {table}.owner_id=?)"]
    params = [user['id']]
    for tid in team_ids:
        conditions.append(f"({table}.owner_type='team' AND {table}.owner_id=?)")
        params.append(tid)
    # Include resources with explicit read+ permission
    conditions.append(
        f"({table}.id IN (SELECT resource_id FROM permissions WHERE resource_type=? "
        f"AND grantee_type='user' AND grantee_id=? AND permission IN ('read','write','delete')))"
    )
    params.extend([resource_type, user['id']])
    for tid in team_ids:
        conditions.append(
            f"({table}.id IN (SELECT resource_id FROM permissions WHERE resource_type=? "
            f"AND grantee_type='team' AND grantee_id=? AND permission IN ('read','write','delete')))"
        )
        params.extend([resource_type, tid])
    return " OR ".join(conditions), params

# ── Auth Routes ────────────────────────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(force=True)
    username = data.get('username', '').strip()
    password = data.get('password', '')
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    session['user_id'] = user['id']
    session.permanent = True
    return jsonify({'id': user['id'], 'username': user['username'], 'display_name': user['display_name'], 'role': user['role']})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    return jsonify(user)

@app.route('/api/auth/password', methods=['PUT'])
@login_required
def change_password():
    data = request.get_json(force=True)
    old_pw = data.get('old_password', '')
    new_pw = data.get('new_password', '')
    if len(new_pw) < 4:
        return jsonify({'error': 'Password too short (min 4)'}), 400
    with get_db() as conn:
        user = conn.execute("SELECT password_hash FROM users WHERE id=?", (g.user['id'],)).fetchone()
        if not check_password_hash(user['password_hash'], old_pw):
            return jsonify({'error': 'Wrong current password'}), 401
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_pw), g.user['id']))
        conn.commit()
    return jsonify({'ok': True})

# ── Admin: User Management ─────────────────────────────────────────────────

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_list_users():
    with get_db() as conn:
        rows = conn.execute("SELECT id, username, email, display_name, role, created_at FROM users ORDER BY created_at").fetchall()
    return jsonify([dict_row(r) for r in rows])

@app.route('/api/admin/users', methods=['POST'])
@admin_required
def admin_create_user():
    data = request.get_json(force=True)
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'error': 'username and password required'}), 400
    user_id = gen_id()
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (id, username, email, password_hash, display_name, role) VALUES (?,?,?,?,?,?)",
                (user_id, username, data.get('email', ''), generate_password_hash(password),
                 data.get('display_name', username), data.get('role', 'user'))
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already exists'}), 409
    return jsonify({'id': user_id, 'username': username}), 201

@app.route('/api/admin/users/<user_id>', methods=['PUT'])
@admin_required
def admin_update_user(user_id):
    data = request.get_json(force=True)
    with get_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if 'display_name' in data:
            conn.execute("UPDATE users SET display_name=? WHERE id=?", (data['display_name'], user_id))
        if 'email' in data:
            conn.execute("UPDATE users SET email=? WHERE id=?", (data['email'], user_id))
        if 'role' in data and data['role'] in ('admin', 'user'):
            conn.execute("UPDATE users SET role=? WHERE id=?", (data['role'], user_id))
        if 'password' in data and data['password']:
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(data['password']), user_id))
        conn.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/users/<user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    if user_id == g.user['id']:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    with get_db() as conn:
        conn.execute("DELETE FROM team_members WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM permissions WHERE granted_by=? OR (grantee_type='user' AND grantee_id=?)", (user_id, user_id))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
    return jsonify({'ok': True})

# ── Teams ──────────────────────────────────────────────────────────────────

@app.route('/api/teams', methods=['GET'])
@login_required
def list_teams():
    with get_db() as conn:
        if g.user['role'] == 'admin':
            rows = conn.execute("SELECT * FROM teams ORDER BY name").fetchall()
        else:
            rows = conn.execute(
                "SELECT t.* FROM teams t JOIN team_members tm ON t.id=tm.team_id WHERE tm.user_id=? ORDER BY t.name",
                (g.user['id'],)
            ).fetchall()
    teams = []
    for r in rows:
        t = dict_row(r)
        with get_db() as conn:
            members = conn.execute(
                "SELECT u.id, u.username, u.display_name, tm.role FROM team_members tm "
                "JOIN users u ON u.id=tm.user_id WHERE tm.team_id=?", (t['id'],)
            ).fetchall()
        t['members'] = [dict_row(m) for m in members]
        teams.append(t)
    return jsonify(teams)

@app.route('/api/teams', methods=['POST'])
@login_required
def create_team():
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Team name required'}), 400
    team_id = gen_id()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO teams (id, name, description, created_by) VALUES (?,?,?,?)",
            (team_id, name, data.get('description', ''), g.user['id'])
        )
        conn.execute(
            "INSERT INTO team_members (team_id, user_id, role) VALUES (?,?,?)",
            (team_id, g.user['id'], 'owner')
        )
        conn.commit()
    return jsonify({'id': team_id, 'name': name}), 201

@app.route('/api/teams/<team_id>', methods=['PUT'])
@login_required
def update_team(team_id):
    data = request.get_json(force=True)
    with get_db() as conn:
        # Check: must be team owner/admin or app admin
        member = conn.execute(
            "SELECT role FROM team_members WHERE team_id=? AND user_id=?", (team_id, g.user['id'])
        ).fetchone()
        if not member and g.user['role'] != 'admin':
            return jsonify({'error': 'Not authorized'}), 403
        if member and member['role'] not in ('owner', 'admin') and g.user['role'] != 'admin':
            return jsonify({'error': 'Not authorized'}), 403
        if 'name' in data:
            conn.execute("UPDATE teams SET name=? WHERE id=?", (data['name'], team_id))
        if 'description' in data:
            conn.execute("UPDATE teams SET description=? WHERE id=?", (data['description'], team_id))
        conn.commit()
    return jsonify({'ok': True})

@app.route('/api/teams/<team_id>', methods=['DELETE'])
@login_required
def delete_team(team_id):
    with get_db() as conn:
        member = conn.execute(
            "SELECT role FROM team_members WHERE team_id=? AND user_id=?", (team_id, g.user['id'])
        ).fetchone()
        if (not member or member['role'] != 'owner') and g.user['role'] != 'admin':
            return jsonify({'error': 'Only team owner or admin can delete'}), 403
        conn.execute("DELETE FROM team_members WHERE team_id=?", (team_id,))
        conn.execute("DELETE FROM permissions WHERE grantee_type='team' AND grantee_id=?", (team_id,))
        conn.execute("DELETE FROM teams WHERE id=?", (team_id,))
        conn.commit()
    return jsonify({'ok': True})

@app.route('/api/teams/<team_id>/members', methods=['POST'])
@login_required
def add_team_member(team_id):
    data = request.get_json(force=True)
    with get_db() as conn:
        member = conn.execute(
            "SELECT role FROM team_members WHERE team_id=? AND user_id=?", (team_id, g.user['id'])
        ).fetchone()
        if (not member or member['role'] not in ('owner', 'admin')) and g.user['role'] != 'admin':
            return jsonify({'error': 'Not authorized'}), 403
        user_id = data.get('user_id', '')
        role = data.get('role', 'member')
        if role not in ('member', 'admin'):
            role = 'member'
        try:
            conn.execute(
                "INSERT INTO team_members (team_id, user_id, role) VALUES (?,?,?)",
                (team_id, user_id, role)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Already a member or invalid user'}), 409
    return jsonify({'ok': True}), 201

@app.route('/api/teams/<team_id>/members/<user_id>', methods=['PUT'])
@login_required
def update_team_member(team_id, user_id):
    data = request.get_json(force=True)
    with get_db() as conn:
        member = conn.execute(
            "SELECT role FROM team_members WHERE team_id=? AND user_id=?", (team_id, g.user['id'])
        ).fetchone()
        if (not member or member['role'] not in ('owner', 'admin')) and g.user['role'] != 'admin':
            return jsonify({'error': 'Not authorized'}), 403
        role = data.get('role', 'member')
        if role not in ('member', 'admin', 'owner'):
            role = 'member'
        conn.execute("UPDATE team_members SET role=? WHERE team_id=? AND user_id=?", (role, team_id, user_id))
        conn.commit()
    return jsonify({'ok': True})

@app.route('/api/teams/<team_id>/members/<user_id>', methods=['DELETE'])
@login_required
def remove_team_member(team_id, user_id):
    with get_db() as conn:
        member = conn.execute(
            "SELECT role FROM team_members WHERE team_id=? AND user_id=?", (team_id, g.user['id'])
        ).fetchone()
        if (not member or member['role'] not in ('owner', 'admin')) and g.user['role'] != 'admin':
            return jsonify({'error': 'Not authorized'}), 403
        conn.execute("DELETE FROM team_members WHERE team_id=? AND user_id=?", (team_id, user_id))
        conn.commit()
    return jsonify({'ok': True})

# ── Permissions (Sharing) ──────────────────────────────────────────────────

@app.route('/api/permissions/<resource_type>/<resource_id>', methods=['GET'])
@login_required
def get_permissions(resource_type, resource_id):
    if resource_type not in ('page', 'database'):
        return jsonify({'error': 'Invalid resource type'}), 400
    if not can_access_resource(g.user, resource_type, resource_id, 'read'):
        return jsonify({'error': 'Access denied'}), 403
    with get_db() as conn:
        rows = conn.execute(
            "SELECT p.*, u.username as granted_by_name FROM permissions p "
            "LEFT JOIN users u ON u.id=p.granted_by "
            "WHERE p.resource_type=? AND p.resource_id=?",
            (resource_type, resource_id)
        ).fetchall()
    return jsonify([dict_row(r) for r in rows])

@app.route('/api/permissions', methods=['POST'])
@login_required
def grant_permission():
    data = request.get_json(force=True)
    resource_type = data.get('resource_type', '')
    resource_id = data.get('resource_id', '')
    grantee_type = data.get('grantee_type', '')
    grantee_id = data.get('grantee_id', '')
    permission = data.get('permission', '')
    if resource_type not in ('page', 'database') or grantee_type not in ('user', 'team') or permission not in ('read', 'write', 'delete'):
        return jsonify({'error': 'Invalid parameters'}), 400
    # Must own the resource or be admin
    if not can_access_resource(g.user, resource_type, resource_id, 'delete'):
        return jsonify({'error': 'Only owner can share'}), 403
    perm_id = gen_id()
    with get_db() as conn:
        # Remove existing same-type permission first
        conn.execute(
            "DELETE FROM permissions WHERE resource_type=? AND resource_id=? AND grantee_type=? AND grantee_id=?",
            (resource_type, resource_id, grantee_type, grantee_id)
        )
        conn.execute(
            "INSERT INTO permissions (id, resource_type, resource_id, grantee_type, grantee_id, permission, granted_by) "
            "VALUES (?,?,?,?,?,?,?)",
            (perm_id, resource_type, resource_id, grantee_type, grantee_id, permission, g.user['id'])
        )
        conn.commit()
    return jsonify({'id': perm_id}), 201

@app.route('/api/permissions/<perm_id>', methods=['DELETE'])
@login_required
def revoke_permission(perm_id):
    with get_db() as conn:
        perm = conn.execute("SELECT * FROM permissions WHERE id=?", (perm_id,)).fetchone()
        if not perm:
            return jsonify({'error': 'Not found'}), 404
        # Must be owner of the resource or admin
        if perm['granted_by'] != g.user['id'] and g.user['role'] != 'admin':
            if not can_access_resource(g.user, perm['resource_type'], perm['resource_id'], 'delete'):
                return jsonify({'error': 'Not authorized'}), 403
        conn.execute("DELETE FROM permissions WHERE id=?", (perm_id,))
        conn.commit()
    return jsonify({'ok': True})

# ── Pages ──────────────────────────────────────────────────────────────────

@app.route('/login')
def login_page():
    return send_from_directory('static', 'login.html')

@app.route('/')
def index():
    user = get_current_user()
    if not user:
        return send_from_directory('static', 'login.html')
    return send_from_directory('static', 'index.html')

@app.route('/api/pages', methods=['GET'])
@login_required
def list_pages():
    workspace = request.args.get('workspace')
    owner = request.args.get('owner')  # optional: filter by team id
    access_filter, access_params = get_accessible_filter(g.user, 'pages')
    with get_db() as conn:
        where = [f"({access_filter})"]
        params = list(access_params)
        if workspace:
            where.append("pages.workspace=?")
            params.append(workspace)
        if owner:
            where.append("pages.owner_id=? AND pages.owner_type='team'")
            params.append(owner)
        sql = f"SELECT * FROM pages WHERE {' AND '.join(where)} ORDER BY is_favorite DESC, sort_order ASC, updated_at DESC"
        rows = conn.execute(sql, params).fetchall()
    return jsonify([dict_row(r) for r in rows])

@app.route('/api/pages', methods=['POST'])
@login_required
def create_page():
    data = request.get_json(force=True)
    page_id = data.get('id', gen_id())
    title = data.get('title', 'Untitled')
    parent_id = data.get('parent_id')
    icon = data.get('icon', '')
    workspace = data.get('workspace', 'docs')
    owner_id = data.get('owner_id', g.user['id'])
    owner_type = data.get('owner_type', 'user')
    # If creating in a team, verify membership
    if owner_type == 'team':
        team_ids = get_user_team_ids(g.user['id'])
        if owner_id not in team_ids and g.user['role'] != 'admin':
            return jsonify({'error': 'Not a member of this team'}), 403
    else:
        owner_id = g.user['id']
    
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
            "INSERT INTO pages (id, title, icon, parent_id, workspace, sort_order, owner_id, owner_type) VALUES (?,?,?,?,?,?,?,?)",
            (page_id, title, icon, parent_id, workspace, max_order + 1, owner_id, owner_type)
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
@login_required
def get_page(page_id):
    if not can_access_resource(g.user, 'page', page_id, 'read'):
        return jsonify({'error': 'Access denied'}), 403
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
@login_required
def update_page(page_id):
    if not can_access_resource(g.user, 'page', page_id, 'write'):
        return jsonify({'error': 'Access denied'}), 403
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
@login_required
def delete_page(page_id):
    if not can_access_resource(g.user, 'page', page_id, 'delete'):
        return jsonify({'error': 'Access denied'}), 403
    with get_db() as conn:
        children = conn.execute("SELECT id FROM pages WHERE parent_id=?", (page_id,)).fetchall()
        for child in children:
            delete_page_recursive(conn, child['id'])
        conn.execute("DELETE FROM blocks WHERE page_id=?", (page_id,))
        conn.execute("DELETE FROM permissions WHERE resource_type='page' AND resource_id=?", (page_id,))
        conn.execute("DELETE FROM pages WHERE id=?", (page_id,))
        conn.commit()
    return jsonify({'ok': True})

def delete_page_recursive(conn, page_id):
    children = conn.execute("SELECT id FROM pages WHERE parent_id=?", (page_id,)).fetchall()
    for child in children:
        delete_page_recursive(conn, child['id'])
    conn.execute("DELETE FROM blocks WHERE page_id=?", (page_id,))
    conn.execute("DELETE FROM permissions WHERE resource_type='page' AND resource_id=?", (page_id,))
    conn.execute("DELETE FROM pages WHERE id=?", (page_id,))

@app.route('/api/pages/reorder', methods=['PUT'])
@login_required
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
@login_required
def get_blocks(page_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM blocks WHERE page_id=? ORDER BY sort_order", (page_id,)
        ).fetchall()
    return jsonify([dict_row(r) for r in rows])

@app.route('/api/pages/<page_id>/blocks', methods=['POST'])
@login_required
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
@login_required
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
@login_required
def delete_block(block_id):
    with get_db() as conn:
        block = conn.execute("SELECT * FROM blocks WHERE id=?", (block_id,)).fetchone()
        if block:
            conn.execute("DELETE FROM blocks WHERE id=?", (block_id,))
            conn.execute("UPDATE pages SET updated_at=? WHERE id=?", (now(), block['page_id']))
            conn.commit()
    return jsonify({'ok': True})

@app.route('/api/pages/<page_id>/blocks/reorder', methods=['PUT'])
@login_required
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
@login_required
def list_databases():
    workspace = request.args.get('workspace')
    access_filter, access_params = get_accessible_filter(g.user, 'databases')
    with get_db() as conn:
        where = [f"({access_filter})"]
        params = list(access_params)
        if workspace:
            where.append("databases.workspace=?")
            params.append(workspace)
        rows = conn.execute(
            f"SELECT * FROM databases WHERE {' AND '.join(where)} ORDER BY updated_at DESC", params
        ).fetchall()
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
@login_required
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
        owner_id = data.get('owner_id', g.user['id'])
        owner_type = data.get('owner_type', 'user')
        if owner_type == 'team':
            team_ids = get_user_team_ids(g.user['id'])
            if owner_id not in team_ids and g.user['role'] != 'admin':
                return jsonify({'error': 'Not a member of this team'}), 403
        else:
            owner_id = g.user['id']
        conn.execute(
            "INSERT INTO databases (id, title, icon, workspace, description, properties_schema, default_view, owner_id, owner_type) VALUES (?,?,?,?,?,?,?,?,?)",
            (db_id, title, icon, workspace, description, json.dumps(schema), default_view, owner_id, owner_type)
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
@login_required
def get_database(db_id):
    if not can_access_resource(g.user, 'database', db_id, 'read'):
        return jsonify({'error': 'Access denied'}), 403
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
@login_required
def update_database(db_id):
    if not can_access_resource(g.user, 'database', db_id, 'write'):
        return jsonify({'error': 'Access denied'}), 403
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
@login_required
def delete_database(db_id):
    if not can_access_resource(g.user, 'database', db_id, 'delete'):
        return jsonify({'error': 'Access denied'}), 403
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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

# ── AI Inline & Block Actions ──────────────────────────────────────────────

@app.route('/api/ai/inline', methods=['POST'])
def ai_inline():
    """AI text transformation on selected text."""
    data = request.get_json(force=True)
    text = data.get('text', '').strip()
    action = data.get('action', '')
    language = data.get('language', 'English')
    custom_prompt = data.get('prompt', '')
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    
    prompts = {
        'improve': f'Improve the writing quality of this text. Make it clearer and more polished. Return ONLY the improved text, nothing else:\n\n{text}',
        'fix_grammar': f'Fix all grammar and spelling errors in this text. Return ONLY the corrected text, nothing else:\n\n{text}',
        'shorter': f'Make this text more concise while keeping the key meaning. Return ONLY the shortened text, nothing else:\n\n{text}',
        'longer': f'Expand this text with more detail and explanation. Return ONLY the expanded text, nothing else:\n\n{text}',
        'simplify': f'Simplify this text so it is easy to understand. Use simple words. Return ONLY the simplified text, nothing else:\n\n{text}',
        'professional': f'Rewrite this text in a professional, formal tone. Return ONLY the rewritten text, nothing else:\n\n{text}',
        'casual': f'Rewrite this text in a casual, friendly tone. Return ONLY the rewritten text, nothing else:\n\n{text}',
        'translate': f'Translate this text to {language}. Return ONLY the translation, nothing else:\n\n{text}',
        'explain': f'Explain this text clearly in simple terms:\n\n{text}',
        'summarize': f'Provide a concise summary of this text:\n\n{text}',
        'action_items': f'Extract action items from this text as a bullet list. Each item should start with "- ". Return ONLY the bullet list:\n\n{text}',
        'key_points': f'Extract the key points from this text as a bullet list. Each item should start with "- ". Return ONLY the bullet list:\n\n{text}',
        'continue': f'Continue writing from where this text leaves off. Match the style and tone. Return ONLY the continuation:\n\n{text}',
        'custom': f'{custom_prompt}\n\n{text}' if custom_prompt else text,
    }
    
    prompt = prompts.get(action, prompts.get('improve'))
    
    try:
        api_config = get_api_config()
        result = call_claude(api_config, 'You are a helpful writing assistant. Follow instructions precisely. Be concise.', 
                           [{"role": "user", "content": prompt}])
        
        response_text = ''
        for block in result.get('content', []):
            if block.get('type') == 'text':
                response_text += block['text']
        
        return jsonify({'result': response_text.strip(), 'action': action})
    except Exception as e:
        logger.error(f"AI inline error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/block', methods=['POST'])
def ai_block():
    """Generate AI content for a block based on page context."""
    data = request.get_json(force=True)
    action = data.get('action', '')
    page_id = data.get('page_id', '')
    block_id = data.get('block_id', '')
    prompt = data.get('prompt', '')
    language = data.get('language', 'English')
    selected_text = data.get('selected_text', '').strip()
    
    # Use selected text if provided, otherwise get full page context
    page_context = ''
    if selected_text:
        page_context = selected_text
    elif page_id:
        with get_db() as conn:
            page = conn.execute("SELECT title FROM pages WHERE id=?", (page_id,)).fetchone()
            blocks = conn.execute(
                "SELECT type, content FROM blocks WHERE page_id=? ORDER BY sort_order", (page_id,)
            ).fetchall()
            if page:
                page_context = f"Page: {page['title']}\n"
                page_context += '\n'.join(b['content'] for b in blocks if b['content'])
    
    prompts = {
        'summarize': f'Summarize the following page content concisely:\n\n{page_context}',
        'action_items': f'Extract action items from this page as a bullet list (each line starts with "- "):\n\n{page_context}',
        'key_points': f'Extract key points from this page as a bullet list (each line starts with "- "):\n\n{page_context}',
        'explain': f'Explain the content of this page in simple terms:\n\n{page_context}',
        'translate': f'Translate the following content to {language}:\n\n{page_context}',
        'continue': f'Continue writing based on this content. Match the style:\n\n{page_context}',
        'outline': f'Create a detailed outline for this topic:\n\n{prompt or page_context}',
        'brainstorm': f'Brainstorm ideas related to this topic. Return as a bullet list:\n\n{prompt or page_context}',
        'pros_cons': f'List pros and cons for this topic. Format as "Pros:" and "Cons:" sections with bullets:\n\n{prompt or page_context}',
        'custom': prompt,
    }
    
    ai_prompt = prompts.get(action, prompt or page_context)
    
    try:
        api_config = get_api_config()
        result = call_claude(api_config, 'You are a helpful writing assistant integrated into a note-taking app. Be concise and well-structured.',
                           [{"role": "user", "content": ai_prompt}])
        
        response_text = ''
        for block in result.get('content', []):
            if block.get('type') == 'text':
                response_text += block['text']
        
        return jsonify({'result': response_text.strip(), 'action': action})
    except Exception as e:
        logger.error(f"AI block error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/research', methods=['POST'])
def ai_research():
    """AI Research — generate a comprehensive research page on a topic."""
    data = request.get_json(force=True)
    topic = data.get('topic', '').strip()
    title = data.get('title', '').strip()
    
    if not topic:
        return jsonify({'error': 'No topic provided'}), 400
    
    try:
        api_config = get_api_config()
        prompt = f"""Research the following topic thoroughly and create a comprehensive, well-structured report.

Topic: {topic}

Create the report with:
1. An executive summary
2. Key findings organized by subtopics
3. Important details and data points
4. Conclusions or recommendations

Format your response as structured content that can be broken into blocks.
Use markdown headers (##, ###), bullet points, and clear paragraphs.
Be factual, thorough, and cite specific information where possible.

IMPORTANT: Start directly with the content. Do NOT include meta-commentary like "I will analyze...", "Let me research...", "Now I have enough data...", "Here is my report...", thinking-out-loud, or preambles. Just the report itself."""

        result = call_claude(api_config, 
                           'You are a research assistant. Provide thorough, well-structured research reports. Use your knowledge to be as comprehensive as possible.',
                           [{"role": "user", "content": prompt}])
        
        response_text = ''
        for block in result.get('content', []):
            if block.get('type') == 'text':
                response_text += block['text']
        
        # Strip meta-commentary lines from response
        filtered_lines = []
        skip_patterns = re.compile(
            r'^(I will |I\'ll |Let me |Now I |Here is |Here\'s |Below is |I have |'
            r'Ich werde |Lass mich |Hier ist |Jetzt habe |Nun werde |'
            r'I\'m going to |Allow me |I am now |Based on my |After analyzing)',
            re.IGNORECASE
        )
        for line in response_text.strip().split('\n'):
            if line.strip() and skip_patterns.match(line.strip()) and len(line.strip()) < 200:
                continue
            filtered_lines.append(line)
        response_text = '\n'.join(filtered_lines)
        
        # Parse markdown into blocks
        blocks = parse_markdown_to_blocks(response_text.strip())
        
        # Use provided title, or extract from first heading, or truncate topic
        short_title = title
        if not short_title:
            for block in blocks:
                if block['type'] in ('h1', 'h2') and block['content']:
                    t = re.sub(r'<[^>]+>', '', block['content']).strip()
                    if len(t) <= 80:
                        short_title = t
                        blocks = [b for b in blocks if b is not block]
                    break
        if not short_title:
            short_title = topic.split('.')[0].split('\n')[0][:60].strip()
        
        # Create page: short title, then prompt as subtitle, then research content
        page_id = gen_id()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO pages (id, title, icon, workspace, sort_order) VALUES (?,?,?,'docs',0)",
                (page_id, short_title, 'search')
            )
            # Insert prompt as first block (light text)
            prompt_bid = gen_id()
            conn.execute(
                "INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,?,?,?)",
                (prompt_bid, page_id, 'quote', md_inline(topic), 0)
            )
            # Insert divider
            div_bid = gen_id()
            conn.execute(
                "INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,?,?,?)",
                (div_bid, page_id, 'divider', '', 1)
            )
            # Insert research blocks
            for i, block in enumerate(blocks):
                bid = gen_id()
                conn.execute(
                    "INSERT INTO blocks (id, page_id, type, content, sort_order) VALUES (?,?,?,?,?)",
                    (bid, page_id, block['type'], block['content'], i + 2)
                )
            conn.commit()
        
        return jsonify({'page_id': page_id, 'title': short_title, 'blocks': len(blocks) + 2})
    except Exception as e:
        logger.error(f"AI research error: {e}")
        return jsonify({'error': str(e)}), 500


def md_inline(text):
    """Convert inline markdown to HTML."""
    if not text:
        return text
    import re as _re
    t = text
    t = _re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', t)
    t = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = _re.sub(r'__(.+?)__', r'<strong>\1</strong>', t)
    t = _re.sub(r'\*(.+?)\*', r'<em>\1</em>', t)
    t = _re.sub(r'_(.+?)_', r'<em>\1</em>', t)
    t = _re.sub(r'~~(.+?)~~', r'<s>\1</s>', t)
    t = _re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    t = _re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', t)
    return t


def parse_markdown_to_blocks(text):
    """Convert markdown text to block array."""
    blocks = []
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Code blocks
        if line.strip().startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            blocks.append({'type': 'code', 'content': '\n'.join(code_lines)})
            i += 1
            continue
        
        # Markdown tables
        if '|' in line and line.strip().startswith('|'):
            table_lines = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip().startswith('|'):
                stripped = lines[i].strip()
                # Skip separator rows (|---|---|)
                if not re.match(r'^\|[\s\-:]+\|$', stripped.replace('|', '|')):
                    if not all(c in '-| :' for c in stripped):
                        cells = [c.strip() for c in stripped.strip('|').split('|')]
                        table_lines.append(cells)
                i += 1
            if table_lines:
                # Apply inline markdown to cells
                table_lines = [[md_inline(c) for c in row] for row in table_lines]
                blocks.append({'type': 'table', 'content': json.dumps(table_lines)})
            continue
        
        # Headers
        if line.startswith('### '):
            blocks.append({'type': 'h3', 'content': md_inline(line[4:].strip())})
        elif line.startswith('## '):
            blocks.append({'type': 'h2', 'content': md_inline(line[3:].strip())})
        elif line.startswith('# '):
            blocks.append({'type': 'h1', 'content': md_inline(line[2:].strip())})
        # Bullets
        elif line.strip().startswith('- ') or line.strip().startswith('* '):
            content = line.strip()[2:]
            blocks.append({'type': 'bullet', 'content': md_inline(content)})
        # Numbered
        elif re.match(r'^\d+\.\s', line.strip()):
            content = re.sub(r'^\d+\.\s', '', line.strip())
            blocks.append({'type': 'numbered', 'content': md_inline(content)})
        # Blockquote
        elif line.strip().startswith('> '):
            blocks.append({'type': 'quote', 'content': md_inline(line.strip()[2:])})
        # Divider
        elif line.strip() in ('---', '***', '___'):
            blocks.append({'type': 'divider', 'content': ''})
        # Regular text (skip empty lines)
        elif line.strip():
            blocks.append({'type': 'text', 'content': md_inline(line.strip())})
        
        i += 1
    
    return blocks if blocks else [{'type': 'text', 'content': md_inline(text)}]


@app.route('/api/ai/translate-page', methods=['POST'])
def translate_page():
    """Translate entire page to a language and create a new page."""
    data = request.get_json(force=True)
    page_id = data.get('page_id', '')
    language = data.get('language', 'English')
    
    if not page_id:
        return jsonify({'error': 'No page_id'}), 400
    
    with get_db() as conn:
        page = conn.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()
        if not page:
            return jsonify({'error': 'Page not found'}), 404
        blocks = conn.execute(
            "SELECT * FROM blocks WHERE page_id=? ORDER BY sort_order", (page_id,)
        ).fetchall()
    
    # Collect all text content
    content_parts = []
    for b in blocks:
        if b['content']:
            content_parts.append(f"[{b['type']}] {b['content']}")
    
    try:
        api_config = get_api_config()
        prompt = f"""Translate the following content to {language}. 
Maintain the exact same structure. Each line starts with [type] prefix — keep those prefixes unchanged.
Return ONLY the translated lines, one per line, with the same [type] prefixes.

{chr(10).join(content_parts)}"""

        result = call_claude(api_config, 'You are a translator. Translate precisely, keeping structure markers intact.',
                           [{"role": "user", "content": prompt}])
        
        response_text = ''
        for block in result.get('content', []):
            if block.get('type') == 'text':
                response_text += block['text']
        
        # Parse response back to blocks
        new_page_id = gen_id()
        translated_title = f"{page['title']} ({language})"
        
        with get_db() as conn:
            conn.execute(
                "INSERT INTO pages (id, title, icon, workspace, sort_order) VALUES (?,?,?,?,0)",
                (new_page_id, translated_title, page['icon'], page['workspace'] or 'docs')
            )
            
            translated_lines = response_text.strip().split('\n')
            original_blocks = list(blocks)
            
            for i, ob in enumerate(original_blocks):
                bid = gen_id()
                # Try to match translated line
                content = ob['content']
                if i < len(translated_lines):
                    tl = translated_lines[i]
                    # Strip [type] prefix if present
                    m = re.match(r'\[(\w+)\]\s*(.*)', tl)
                    if m:
                        content = m.group(2)
                    else:
                        content = tl
                
                conn.execute(
                    "INSERT INTO blocks (id, page_id, type, content, properties, sort_order, indent_level) VALUES (?,?,?,?,?,?,?)",
                    (bid, new_page_id, ob['type'], content, ob['properties'], ob['sort_order'], ob['indent_level'])
                )
            conn.commit()
        
        return jsonify({'page_id': new_page_id, 'title': translated_title})
    except Exception as e:
        logger.error(f"AI translate page error: {e}")
        return jsonify({'error': str(e)}), 500


# ── AI Chat Agent ──────────────────────────────────────────────────────────

import httpx, re

# ── LLM Configuration (file-based, no OpenClaw dependency) ──────────────────
LLM_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'llm_config.json')
THINKING_LEVELS = ['off', 'minimal', 'low', 'medium', 'high']

def _load_llm_config():
    """Load LLM config from llm_config.json."""
    try:
        with open(LLM_CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"providers": [], "default_model": "", "default_thinking": "off", "max_tokens": 4096}

def _save_llm_config(config):
    """Save LLM config to llm_config.json."""
    with open(LLM_CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

def _get_available_models():
    """Build flat model list from all providers."""
    config = _load_llm_config()
    models = []
    for prov in config.get('providers', []):
        for m in prov.get('models', []):
            models.append({
                'id': f"{prov['id']}/{m['id']}",
                'name': m.get('name', m['id']),
                'group': prov.get('name', prov['id']),
                'provider_id': prov['id'],
            })
    return models

def get_api_config():
    """Get the API config for the currently selected model."""
    config = _load_llm_config()
    model_ref = CHAT_CONFIG.get('model', config.get('default_model', ''))
    # Parse provider_id/model_id
    if '/' in model_ref:
        provider_id, model_id = model_ref.split('/', 1)
    else:
        provider_id, model_id = '', model_ref
    # Find the provider
    for prov in config.get('providers', []):
        if prov['id'] == provider_id:
            return {
                'base_url': prov.get('base_url', ''),
                'api_key': prov.get('api_key', ''),
                'model': model_id,
                'api_type': prov.get('api_type', 'openai'),
            }
    # Fallback: use first provider
    if config.get('providers'):
        prov = config['providers'][0]
        return {
            'base_url': prov.get('base_url', ''),
            'api_key': prov.get('api_key', ''),
            'model': model_id or (prov['models'][0]['id'] if prov.get('models') else ''),
            'api_type': prov.get('api_type', 'openai'),
        }
    return {'base_url': '', 'api_key': '', 'model': '', 'api_type': 'openai'}

# Initialize runtime chat config from saved defaults
_init_config = _load_llm_config()
CHAT_CONFIG = {
    'model': _init_config.get('default_model', ''),
    'max_tokens': _init_config.get('max_tokens', 4096),
    'thinking': _init_config.get('default_thinking', 'off'),
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
    """Execute a tool call via the MCP server (stdio protocol).
    All tool logic lives in mcp_server.py → notes_tools.py."""
    from mcp_client import call_tool
    return call_tool(name, input_data)


# Chat history stored in memory (per-session, resets on restart)
chat_histories = {}

def _load_chat_history(session_id):
    """Load chat history from DB into memory cache."""
    if session_id not in chat_histories:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT role, content FROM chat_messages WHERE session_id=? ORDER BY id",
                (session_id,)
            ).fetchall()
            chat_histories[session_id] = [{"role": r['role'], "content": r['content']} for r in rows]
    return chat_histories[session_id]

def _save_chat_message(session_id, role, content):
    """Persist a single chat message to DB."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO chat_messages (session_id, role, content) VALUES (?,?,?)",
            (session_id, role, content)
        )
        conn.commit()

def _clear_chat_history(session_id):
    """Clear chat history from DB and memory."""
    with get_db() as conn:
        conn.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
        conn.commit()
    chat_histories.pop(session_id, None)

@app.route('/api/chat/config', methods=['GET'])
def get_chat_config():
    return jsonify({**CHAT_CONFIG, 'available_models': _get_available_models(), 'thinking_levels': THINKING_LEVELS})

@app.route('/api/chat/config', methods=['PUT'])
def update_chat_config():
    data = request.get_json(force=True)
    if 'model' in data:
        CHAT_CONFIG['model'] = data['model']
    if 'max_tokens' in data:
        CHAT_CONFIG['max_tokens'] = data['max_tokens']
    if 'thinking' in data and data['thinking'] in THINKING_LEVELS:
        CHAT_CONFIG['thinking'] = data['thinking']
    return jsonify({**CHAT_CONFIG, 'available_models': _get_available_models(), 'thinking_levels': THINKING_LEVELS})

# ── LLM Provider Management API ────────────────────────────────────────────

@app.route('/api/llm/config', methods=['GET'])
def get_llm_config():
    """Get full LLM config (providers, defaults)."""
    config = _load_llm_config()
    # Mask API keys for frontend display
    safe = json.loads(json.dumps(config))
    for prov in safe.get('providers', []):
        key = prov.get('api_key', '')
        if len(key) > 8:
            prov['api_key_masked'] = key[:4] + '•' * (len(key) - 8) + key[-4:]
        else:
            prov['api_key_masked'] = '•' * len(key)
    return jsonify(safe)

@app.route('/api/llm/config', methods=['PUT'])
def update_llm_config():
    """Update defaults (default_model, default_thinking, max_tokens)."""
    data = request.get_json(force=True)
    config = _load_llm_config()
    if 'default_model' in data:
        config['default_model'] = data['default_model']
        CHAT_CONFIG['model'] = data['default_model']
    if 'default_thinking' in data:
        config['default_thinking'] = data['default_thinking']
        CHAT_CONFIG['thinking'] = data['default_thinking']
    if 'max_tokens' in data:
        config['max_tokens'] = data['max_tokens']
        CHAT_CONFIG['max_tokens'] = data['max_tokens']
    _save_llm_config(config)
    return jsonify(config)

@app.route('/api/llm/providers', methods=['GET'])
def list_providers():
    config = _load_llm_config()
    return jsonify(config.get('providers', []))

@app.route('/api/llm/providers', methods=['POST'])
def add_provider():
    data = request.get_json(force=True)
    config = _load_llm_config()
    provider = {
        'id': data.get('id', '').strip(),
        'name': data.get('name', '').strip(),
        'base_url': data.get('base_url', '').strip(),
        'api_key': data.get('api_key', '').strip(),
        'api_type': data.get('api_type', 'openai'),
        'models': data.get('models', []),
    }
    if not provider['id'] or not provider['base_url']:
        return jsonify({'error': 'id and base_url are required'}), 400
    # Check for duplicate id
    if any(p['id'] == provider['id'] for p in config.get('providers', [])):
        return jsonify({'error': f"Provider '{provider['id']}' already exists"}), 409
    config.setdefault('providers', []).append(provider)
    _save_llm_config(config)
    return jsonify(provider), 201

@app.route('/api/llm/providers/<provider_id>', methods=['PUT'])
def update_provider(provider_id):
    data = request.get_json(force=True)
    config = _load_llm_config()
    for prov in config.get('providers', []):
        if prov['id'] == provider_id:
            if 'name' in data: prov['name'] = data['name']
            if 'base_url' in data: prov['base_url'] = data['base_url']
            if 'api_key' in data: prov['api_key'] = data['api_key']
            if 'api_type' in data: prov['api_type'] = data['api_type']
            if 'models' in data: prov['models'] = data['models']
            _save_llm_config(config)
            return jsonify(prov)
    return jsonify({'error': 'Provider not found'}), 404

@app.route('/api/llm/providers/<provider_id>', methods=['DELETE'])
def delete_provider(provider_id):
    config = _load_llm_config()
    config['providers'] = [p for p in config.get('providers', []) if p['id'] != provider_id]
    _save_llm_config(config)
    return jsonify({'ok': True})

@app.route('/api/llm/test', methods=['POST'])
def test_provider():
    """Test a provider connection by sending a simple chat completion."""
    data = request.get_json(force=True)
    base_url = data.get('base_url', '').rstrip('/')
    api_key = data.get('api_key', '')
    model = data.get('model', '')
    api_type = data.get('api_type', 'openai')
    try:
        if api_type == 'anthropic':
            url = f"{base_url}/v1/messages"
            headers = {'x-api-key': api_key, 'content-type': 'application/json', 'anthropic-version': '2023-06-01'}
            body = {'model': model, 'max_tokens': 20, 'messages': [{'role': 'user', 'content': 'Say "ok"'}]}
            with httpx.Client(timeout=15) as client:
                r = client.post(url, headers=headers, json=body)
                r.raise_for_status()
                resp = r.json()
            text = ' '.join(b.get('text', '') for b in resp.get('content', []) if b.get('type') == 'text')
        else:
            url = f"{base_url}/chat/completions"
            headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
            body = {'model': model, 'max_tokens': 20, 'messages': [{'role': 'user', 'content': 'Say "ok"'}]}
            with httpx.Client(timeout=15) as client:
                r = client.post(url, headers=headers, json=body)
                r.raise_for_status()
                resp = r.json()
            text = resp.get('choices', [{}])[0].get('message', {}).get('content', '')
        return jsonify({'ok': True, 'response': text[:100]})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json(force=True)
    message = data.get('message', '').strip()
    session_id = data.get('session_id', 'default')
    
    if not message:
        return jsonify({'error': 'Empty message'}), 400
    
    api_config = get_api_config()
    if not api_config['api_key']:
        return jsonify({'error': 'No API key configured'}), 500
    
    # Get or create chat history (loads from DB if not cached)
    history = _load_chat_history(session_id)
    
    # Build context
    all_content = gather_all_content()
    
    system_prompt = f"""You are Brain Notes AI — an intelligent assistant embedded in a note-taking application.
You have full access to all content in the app and can create, edit, search, and manage pages, projects, and knowledge base items.

## Current App Content
{all_content}

## How Actions Work (IMPORTANT!)
You DO have the ability to perform actions. Actions are NOT separate tools or function calls.
To perform an action, simply include a JSON block wrapped in ```action``` fenced code tags in your text response.
The backend will parse these blocks and execute them automatically. This IS your toolset — just write the JSON blocks.
You can include multiple action blocks. Always include a human-readable explanation alongside actions.

## Available Actions

### create_page — Create a new page
```action
{{"action":"create_page","title":"Page Title","icon":"lucide-icon-name","blocks":[{{"type":"h1","content":"Heading"}},{{"type":"bullet","content":"Item 1"}},{{"type":"todo","content":"Task 1"}}]}}
```
Block types: text, h1, h2, h3, bullet, numbered, todo, quote, callout, code, divider

### edit_page — Edit an existing page (change title, icon, replace or append blocks)
To REPLACE all content on a page (rewrite it):
```action
{{"action":"edit_page","page_id":"THE_PAGE_ID","title":"New Title","replace_blocks":[{{"type":"h1","content":"New Heading"}},{{"type":"text","content":"New content"}}]}}
```
To APPEND content at the end of a page:
```action
{{"action":"edit_page","page_id":"THE_PAGE_ID","append_blocks":[{{"type":"text","content":"Added text"}}]}}
```
You can set title, icon, replace_blocks, and/or append_blocks. Use the page_id from the content listing above.

### create_project_item — Add an item to a database/project
```action
{{"action":"create_project_item","database_id":"id","title":"Item Title","properties":{{"prop_id":"value"}}}}
```

### create_database — Create a new database
```action
{{"action":"create_database","title":"DB Title","workspace":"projects|wiki","description":"..."}}
```

### delete_page — Delete a page
```action
{{"action":"delete_page","page_id":"id"}}
```

## Guidelines
- Be concise and helpful
- When asked to edit or update a page, USE the edit_page action — don't say you can't
- When creating content, use appropriate block types
- Use Lucide icon names for page icons (e.g., 'target', 'lightbulb', 'bar-chart-3', 'flask-conical', 'clipboard-list')
- Always respond with a human-readable message. Put action blocks at the END of your response.
- For analysis tasks, create a well-structured page with the results
- NEVER say "I don't have that tool" — all actions listed above work by including the JSON block in your response
"""
    
    # Add user message to history (memory + DB)
    history.append({"role": "user", "content": message})
    _save_chat_message(session_id, "user", message)
    
    # Keep history manageable (last 20 messages)
    if len(history) > 20:
        history = history[-20:]
        chat_histories[session_id] = history
        # Trim DB too — keep only the last 20
        with get_db() as conn:
            conn.execute(
                "DELETE FROM chat_messages WHERE session_id=? AND id NOT IN "
                "(SELECT id FROM chat_messages WHERE session_id=? ORDER BY id DESC LIMIT 20)",
                (session_id, session_id)
            )
            conn.commit()
    
    # Call LLM — use native tool_use for Anthropic/MiniMax, fallback to gateway for others
    try:
        response = call_llm_with_tools(api_config, system_prompt, history)
    except Exception as e:
        logger.error(f"LLM API error: {e}")
        return jsonify({'error': str(e)}), 500
    
    # Extract text
    text_parts = []
    for block in response.get('content', []):
        if block.get('type') == 'text':
            text_parts.append(block['text'])
    
    full_response = '\n'.join(text_parts)
    
    # Get tool results from native tool-use loop (already executed)
    tool_results = response.get('tool_results', [])
    
    # Also parse any text-based action blocks (fallback for models that don't use native tools)
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
    _save_chat_message(session_id, "assistant", full_response)
    
    return jsonify({
        'response': assistant_message,
        'tool_results': tool_results,
        'model': CHAT_CONFIG['model'],
    })


@app.route('/api/chat/history', methods=['GET'])
@login_required
def get_chat_history():
    session_id = request.args.get('session_id', 'default')
    history = _load_chat_history(session_id)
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
@login_required
def clear_chat():
    session_id = request.get_json(force=True).get('session_id', 'default')
    _clear_chat_history(session_id)
    return jsonify({'ok': True})


# Tool definitions for LLM tool_use (Anthropic input_schema format, converted to OpenAI at call time)
NATIVE_TOOLS = [
    {
        "name": "search_notes",
        "description": "Search across all pages, blocks, and database items by keyword.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"]
        }
    },
    {
        "name": "list_pages",
        "description": "List all pages in the notes app.",
        "input_schema": {
            "type": "object",
            "properties": {"workspace": {"type": "string", "description": "Filter: 'docs', 'all' (default)", "default": "all"}},
        }
    },
    {
        "name": "get_page_content",
        "description": "Get the full content of a specific page.",
        "input_schema": {
            "type": "object",
            "properties": {"page_id": {"type": "string", "description": "Page ID"}},
            "required": ["page_id"]
        }
    },
    {
        "name": "create_page",
        "description": "Create a new page with content blocks. Block types: text, h1, h2, h3, bullet, numbered, todo, quote, callout, code, divider",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "icon": {"type": "string", "description": "Lucide icon name", "default": "file-text"},
                "blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "content": {"type": "string"}
                        }
                    }
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "edit_page",
        "description": "Edit an existing page. Can change title, icon, replace all blocks, or append blocks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
                "title": {"type": "string", "description": "New title (optional)"},
                "icon": {"type": "string", "description": "New icon (optional)"},
                "replace_blocks": {
                    "type": "array",
                    "description": "Replace ALL content with these blocks",
                    "items": {"type": "object", "properties": {"type": {"type": "string"}, "content": {"type": "string"}}}
                },
                "append_blocks": {
                    "type": "array",
                    "description": "Append these blocks at the end",
                    "items": {"type": "object", "properties": {"type": {"type": "string"}, "content": {"type": "string"}}}
                }
            },
            "required": ["page_id"]
        }
    },
    {
        "name": "delete_page",
        "description": "Delete a page and all its blocks.",
        "input_schema": {
            "type": "object",
            "properties": {"page_id": {"type": "string"}},
            "required": ["page_id"]
        }
    },
    {
        "name": "list_databases",
        "description": "List all databases (projects and knowledge bases) with schemas.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_database_items",
        "description": "Get all items in a database.",
        "input_schema": {
            "type": "object",
            "properties": {"database_id": {"type": "string"}},
            "required": ["database_id"]
        }
    },
    {
        "name": "create_project_item",
        "description": "Add an item to a database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database_id": {"type": "string"},
                "title": {"type": "string"},
                "properties": {"type": "object", "description": "Property ID to value mapping"}
            },
            "required": ["database_id", "title"]
        }
    },
    {
        "name": "create_database",
        "description": "Create a new database (project board or knowledge base).",
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
]


def call_llm_with_tools(api_config, system, messages, tools=None, max_loops=5):
    """Call LLM with tool-use loop. Supports OpenAI and Anthropic APIs."""
    api_type = api_config.get('api_type', 'openai')
    if api_type == 'anthropic':
        return _call_anthropic_with_tools(api_config, system, messages, tools, max_loops)
    else:
        return _call_openai_with_tools(api_config, system, messages, tools, max_loops)


def _call_openai_with_tools(api_config, system, messages, tools=None, max_loops=5):
    """Call LLM via OpenAI-compatible chat/completions API with tool-use loop."""
    import re as _re

    base_url = api_config['base_url'].rstrip('/')
    api_key = api_config['api_key']
    model = api_config.get('model', CHAT_CONFIG['model'])

    url = f"{base_url}/chat/completions"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    # Build OpenAI-format messages
    oai_messages = [{"role": "system", "content": system}]
    for msg in messages:
        if isinstance(msg.get('content'), str):
            oai_messages.append({"role": msg['role'], "content": msg['content']})

    # Convert tool schemas to OpenAI format
    oai_tools = []
    for t in (tools or NATIVE_TOOLS):
        oai_tools.append({
            "type": "function",
            "function": {
                "name": t['name'],
                "description": t.get('description', ''),
                "parameters": t.get('input_schema', {"type": "object", "properties": {}}),
            }
        })

    tool_results_all = []

    for loop in range(max_loops):
        body = {
            'model': model,
            'max_tokens': CHAT_CONFIG.get('max_tokens', 4096),
            'messages': oai_messages,
            'tools': oai_tools,
        }

        with httpx.Client(timeout=300) as client:
            r = client.post(url, headers=headers, json=body)
            r.raise_for_status()
            resp = r.json()

        choice = resp.get('choices', [{}])[0]
        msg = choice.get('message', {})
        finish_reason = choice.get('finish_reason', 'stop')

        if finish_reason != 'tool_calls' and not msg.get('tool_calls'):
            text = msg.get('content', '') or ''
            text = _re.sub(r'<think>.*?</think>\s*', '', text, flags=_re.DOTALL).strip()
            return {
                'content': [{"type": "text", "text": text}],
                'stop_reason': 'end_turn',
                'tool_results': tool_results_all,
            }

        tool_calls = msg.get('tool_calls', [])
        oai_messages.append(msg)

        for tc in tool_calls:
            func = tc.get('function', {})
            tool_name = func.get('name', '')
            try:
                tool_input = json.loads(func.get('arguments', '{}'))
            except json.JSONDecodeError:
                tool_input = {}
            tool_id = tc.get('id', '')

            logger.info(f"Tool call: {tool_name}({json.dumps(tool_input)[:200]})")
            result = execute_tool(tool_name, tool_input)
            tool_results_all.append({"tool": tool_name, "input": tool_input, "result": result})

            oai_messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": str(result),
            })

    return {
        'content': [{"type": "text", "text": "I performed several actions but reached the maximum number of steps."}],
        'stop_reason': 'max_loops',
        'tool_results': tool_results_all,
    }


def _call_anthropic_with_tools(api_config, system, messages, tools=None, max_loops=5):
    """Call LLM via Anthropic Messages API with native tool_use loop."""

    base_url = api_config['base_url'].rstrip('/')
    api_key = api_config['api_key']
    model = api_config.get('model', CHAT_CONFIG['model'])

    url = f"{base_url}/v1/messages"
    headers = {
        'x-api-key': api_key,
        'content-type': 'application/json',
        'anthropic-version': '2023-06-01',
    }

    # Anthropic tools use input_schema directly
    anthropic_tools = []
    for t in (tools or NATIVE_TOOLS):
        anthropic_tools.append({
            "name": t['name'],
            "description": t.get('description', ''),
            "input_schema": t.get('input_schema', {"type": "object", "properties": {}}),
        })

    # Convert messages to Anthropic format
    anthropic_messages = []
    for msg in messages:
        if isinstance(msg.get('content'), str):
            anthropic_messages.append({"role": msg['role'], "content": msg['content']})

    tool_results_all = []

    for loop in range(max_loops):
        body = {
            'model': model,
            'max_tokens': CHAT_CONFIG.get('max_tokens', 4096),
            'system': system,
            'messages': anthropic_messages,
            'tools': anthropic_tools,
        }

        # Add thinking if enabled
        thinking = CHAT_CONFIG.get('thinking', 'off')
        if thinking != 'off':
            thinking_budget = {'minimal': 1024, 'low': 2048, 'medium': 5000, 'high': 10000}.get(thinking, 5000)
            body['thinking'] = {'type': 'enabled', 'budget_tokens': thinking_budget}

        with httpx.Client(timeout=300) as client:
            r = client.post(url, headers=headers, json=body)
            r.raise_for_status()
            resp = r.json()

        content = resp.get('content', [])
        has_tool_use = any(b.get('type') == 'tool_use' for b in content)

        if not has_tool_use:
            text_parts = [b['text'] for b in content if b.get('type') == 'text']
            return {
                'content': [{"type": "text", "text": '\n'.join(text_parts)}],
                'stop_reason': resp.get('stop_reason', 'end_turn'),
                'tool_results': tool_results_all,
            }

        # Execute tool calls
        tool_use_results = []
        for block in content:
            if block.get('type') == 'tool_use':
                tool_name = block['name']
                tool_input = block['input']
                tool_id = block['id']

                logger.info(f"Tool call: {tool_name}({json.dumps(tool_input)[:200]})")
                result = execute_tool(tool_name, tool_input)
                tool_results_all.append({"tool": tool_name, "input": tool_input, "result": result})

                tool_use_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": str(result),
                })

        anthropic_messages.append({"role": "assistant", "content": content})
        anthropic_messages.append({"role": "user", "content": tool_use_results})

    return {
        'content': [{"type": "text", "text": "I performed several actions but reached the maximum number of steps."}],
        'stop_reason': 'max_loops',
        'tool_results': tool_results_all,
    }


# ── Run ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    logger.info("Starting Brain Notes on port 5006")
    app.run(host='0.0.0.0', port=5006, debug=False)
