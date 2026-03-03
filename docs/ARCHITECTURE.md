# Architecture Handbook

## Overview

Brain Notes is a self-hosted, single-server application following a monolithic architecture. All components run within a single Python process, with SQLite as the data store and QMD as the semantic search engine.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Brain Notes                              │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Frontend  │  │ REST API │  │ AI Engine│  │  MCP Server   │  │
│  │ (SPA)     │  │ (Flask)  │  │          │  │  (FastMCP)    │  │
│  └─────┬─────┘  └─────┬────┘  └─────┬────┘  └──────┬────────┘  │
│        │              │              │               │          │
│        └──────────────┼──────────────┘               │          │
│                       │                              │          │
│              ┌────────┴────────┐           ┌─────────┴───────┐  │
│              │  notes_tools.py │           │  notes_tools.py │  │
│              │  (shared logic) │           │  (shared logic) │  │
│              └────────┬────────┘           └─────────┬───────┘  │
│                       │                              │          │
│              ┌────────┴──────────────────────────────┘          │
│              │                                                  │
│     ┌────────┴────────┐     ┌──────────────┐                   │
│     │    SQLite        │     │     QMD      │                   │
│     │   (notes.db)     │     │ (embeddings) │                   │
│     └─────────────────┘     └──────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

## Design Principles

1. **Single-file frontend** — No build tools, no npm. The entire UI is one HTML file with inline CSS/JS.
2. **Shared business logic** — `notes_tools.py` is the single source of truth for all data operations, used by both the Flask API and the MCP server.
3. **SQLite-first** — No external database server. WAL mode for concurrent reads. Foreign keys enforced.
4. **QMD for search** — Vector embeddings for semantic search over project resources. SQLite FTS5 for keyword search over notes content.
5. **AI-agnostic** — LLM provider is configurable at runtime. No hard dependency on any specific AI service.

## Component Details

### Frontend (`static/index.html`)

Single-page application (SPA) built with vanilla JavaScript.

- **Routing:** Hash-based (no server-side routing needed)
- **State:** Global variables (`currentPage`, `currentDb`, `currentDbItems`, etc.)
- **Rendering:** DOM manipulation via `innerHTML` with template literals
- **API calls:** `fetch()` wrapper (`api()` function) with cookie-based auth
- **Icons:** Lucide Icons loaded from CDN
- **Styling:** CSS custom properties (design tokens) for consistent theming

### Backend (`app.py`)

Flask application serving both the API and static files.

**Key middleware:**
- `@login_required` — Session-based authentication decorator
- `@admin_required` — Admin role check
- `can_access_resource()` — Granular permission check (owner, team, explicit grants)
- `access_filter_sql()` — SQL WHERE clause generator for permission-filtered queries

**Request flow:**
```
Client → Flask Route → Permission Check → notes_tools.py / Direct SQL → Response
```

### Shared Logic (`notes_tools.py`)

Pure Python module with zero framework dependencies. Contains all business logic for:
- CRUD operations on pages, blocks, databases, items
- Search (keyword + semantic)
- Resource management (add, remove, index, search)

This separation ensures the MCP server can use the exact same logic without importing Flask.

### MCP Server (`mcp_server.py`)

Thin wrapper around `notes_tools.py` using FastMCP. Exposes 18 tools via the Model Context Protocol for external AI agents.

**Transport:** stdio (default) or HTTP (`--http` flag)

### AI Engine (embedded in `app.py`)

Handles AI-powered features:
- **Chat** — Multi-turn conversation with tool calling (function calling via OpenAI-compatible API)
- **Inline AI** — Single-shot text generation/transformation
- **Block AI** — Context-aware block operations
- **Research** — Web search integration for deep research
- **Translation** — Full page translation

**Tool calling flow:**
```
User Message → LLM → Tool Call → notes_tools.py → Result → LLM → Response
```

### QMD Integration

QMD (Quick Memory Database) provides semantic search for project resources.

**Architecture:**
```
Project Resource (path) → QMD Collection → Chunks → Vector Embeddings
                                                          ↓
                                              QMD Query → Ranked Results
```

**Collection naming:** `notes-{database_id}-{resource_id}`

**Embedding model:** `embeddinggemma` (local, ~500MB RAM)

**Search pipeline:**
1. Query expansion (lexical + vector + HyDE)
2. Multi-query search across chunks
3. Reranking
4. Score-based result ordering

## Data Model

### Entity Relationship

```
users ──────┐
            │ owns
teams ──┐   ↓
        │  pages ←──── blocks
        │   ↑
        │   │ parent_id (self-reference for nesting)
        │   │
        │  databases ←── db_items ←── db_views
        │   ↑
        │   │
        │  project_resources → QMD Collections
        │
permissions (resource_type + resource_id → any entity)
```

### Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `pages` | Documents and content pages | id, title, icon, workspace, parent_id, owner_id |
| `blocks` | Content blocks within pages | id, page_id, type, content, sort_order, indent_level |
| `databases` | Project boards and knowledge bases | id, title, workspace, properties_schema, default_view |
| `db_items` | Rows/cards in databases | id, database_id, title, properties, page_id |
| `db_views` | View configurations (table/board/list) | id, database_id, type, config |
| `project_resources` | Linked files/directories | id, database_id, path, qmd_collection, file_count |
| `users` | User accounts | id, username, password_hash, role |
| `teams` | User groups | id, name, created_by |
| `team_members` | Team membership | team_id, user_id, role |
| `permissions` | Granular access control | resource_type, resource_id, grantee_type, grantee_id, permission |
| `chat_messages` | AI chat history | session_id, role, content, user_id |

### Block Types

| Type | Rendering | Notes |
|------|-----------|-------|
| `text` | Plain paragraph | Default type |
| `h1`, `h2`, `h3` | Headings | Level 1-3 |
| `bullet` | Unordered list item | Supports nesting via indent_level |
| `numbered` | Ordered list item | Supports nesting |
| `todo` | Checkbox item | `properties.checked` boolean |
| `quote` | Blockquote | Styled with left border |
| `callout` | Callout box | `properties.type`: info, warning, tip, danger |
| `code` | Code block | `properties.language` for syntax highlighting |
| `divider` | Horizontal rule | No content |

### Workspace Types

| Workspace | Purpose | Default View |
|-----------|---------|-------------|
| `docs` | Standard document pages | Page editor |
| `projects` | Project management boards | Kanban board |
| `wiki` | Knowledge base articles | Table |
| `_db_item` | Internal (database item pages) | Hidden |

### Properties Schema (databases)

Stored as JSON array in `databases.properties_schema`:

```json
[
  {
    "id": "unique_id",
    "name": "Status",
    "type": "select",
    "options": [
      {"id": "opt_id", "name": "In Progress", "color": "#3B82F6"}
    ]
  }
]
```

**Property types:** `text`, `number`, `date`, `select`, `multi_select`, `checkbox`, `url`, `email`, `phone`

## Security Model

### Authentication
- Session-based (Flask `session` with `secret_key`)
- Password hashing via `werkzeug.security`
- Login required for all API endpoints except `/login` and `/api/auth/login`

### Authorization
Three-tier permission model:

1. **Owner** — Creator of the resource (full access)
2. **Team** — Members of teams with explicit grants
3. **Permission** — Individual permission grants (read, write, admin)

Admin users bypass all permission checks.

### API Security
- CSRF: Not implemented (SPA with same-origin cookies)
- Rate limiting: Not implemented (single-user deployment)
- Input validation: Basic (trusts authenticated users)

## Performance Considerations

- **SQLite WAL mode** — Allows concurrent readers with single writer
- **No ORM** — Direct SQL for minimal overhead
- **Single HTML file** — No bundle splitting, loads everything upfront (~200KB)
- **QMD embedding** — Local model, no API latency for search indexing
- **Lazy resource indexing** — Resources indexed on-demand, not at add time
