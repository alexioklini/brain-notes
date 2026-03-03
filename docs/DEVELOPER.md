# Developer Documentation

## API Reference

All API endpoints require authentication via session cookie unless noted otherwise. Send `Content-Type: application/json` for POST/PUT requests.

### Authentication

#### POST `/api/auth/login`
Login and create a session.

```json
// Request
{"username": "admin", "password": "admin"}

// Response 200
{"id": "52c0da91", "username": "admin", "role": "admin", "display_name": "Admin"}

// Response 401
{"error": "Invalid credentials"}
```

#### POST `/api/auth/logout`
Destroy session.

#### GET `/api/auth/me`
Get current authenticated user.

#### PUT `/api/auth/password`
Change password.
```json
{"current_password": "old", "new_password": "new"}
```

---

### Pages

#### GET `/api/pages?workspace=docs`
List pages filtered by workspace. Returns array of page objects.

Query params: `workspace` (docs, projects, wiki, all)

```json
// Response
[
  {
    "id": "abc123",
    "title": "My Page",
    "icon": "file-text",
    "workspace": "docs",
    "parent_id": null,
    "is_favorite": false,
    "sort_order": 0,
    "created_at": "2026-03-01 10:00:00",
    "updated_at": "2026-03-01 10:00:00"
  }
]
```

#### POST `/api/pages`
Create a page.

```json
// Request
{
  "title": "New Page",
  "icon": "file-text",
  "workspace": "docs",
  "parent_id": null,
  "blocks": [
    {"type": "h1", "content": "Heading"},
    {"type": "text", "content": "Body text"},
    {"type": "todo", "content": "Task item", "properties": {"checked": false}}
  ]
}

// Response 201
{"id": "new_page_id", "title": "New Page", ...}
```

#### GET `/api/pages/<page_id>`
Get page with all blocks.

#### PUT `/api/pages/<page_id>`
Update page metadata.
```json
{"title": "Updated Title", "icon": "star", "is_favorite": true}
```

#### DELETE `/api/pages/<page_id>`
Delete page and all blocks. Returns `{"deleted": "page_id"}`.

#### PUT `/api/pages/reorder`
Reorder pages.
```json
{"items": [{"id": "page1", "sort_order": 0}, {"id": "page2", "sort_order": 1}]}
```

---

### Blocks

#### GET `/api/pages/<page_id>/blocks`
List all blocks for a page, ordered by sort_order.

#### POST `/api/pages/<page_id>/blocks`
Add blocks to a page.
```json
{
  "blocks": [
    {"type": "text", "content": "New paragraph", "sort_order": 5}
  ]
}
```

#### PUT `/api/blocks/<block_id>`
Update a block.
```json
{"content": "Updated text", "type": "h2", "properties": {"language": "python"}}
```

#### DELETE `/api/blocks/<block_id>`
Delete a block.

#### PUT `/api/pages/<page_id>/blocks/reorder`
Reorder blocks within a page.

---

### Databases

#### GET `/api/databases?workspace=projects`
List databases. Filter by workspace.

```json
// Response
[
  {
    "id": "db123",
    "title": "Engineering Tasks",
    "workspace": "projects",
    "description": "Sprint tracker",
    "properties_schema": [...],
    "default_view": "board",
    "views": [...],
    "item_count": 15
  }
]
```

#### POST `/api/databases`
Create a database.
```json
{
  "title": "New Project",
  "workspace": "projects",
  "description": "Project description",
  "properties_schema": [
    {
      "id": "prop1",
      "name": "Status",
      "type": "select",
      "options": [
        {"id": "opt1", "name": "Todo", "color": "#6B7280"},
        {"id": "opt2", "name": "Done", "color": "#10B981"}
      ]
    }
  ]
}
```

#### GET `/api/databases/<db_id>`
Get database with schema, views, and all items.

#### PUT `/api/databases/<db_id>`
Update database metadata, schema, or description.

#### DELETE `/api/databases/<db_id>`
Delete database and all items.

---

### Database Items

#### POST `/api/databases/<db_id>/items`
Create an item.
```json
{
  "title": "New Task",
  "properties": {"prop_id_status": "Todo", "prop_id_priority": "High"}
}
```

#### PUT `/api/databases/<db_id>/items/<item_id>`
Update item title and/or properties.

#### DELETE `/api/databases/<db_id>/items/<item_id>`
Delete an item.

#### PUT `/api/databases/<db_id>/items/reorder`
Reorder items.

---

### Database Views

#### POST `/api/databases/<db_id>/views`
Create a view.
```json
{"name": "Sprint Board", "type": "board", "config": {"group_by": "status_prop_id"}}
```

#### PUT `/api/databases/<db_id>/views/<view_id>`
Update a view.

---

### Project Resources

#### GET `/api/databases/<db_id>/resources`
List all resources for a project.

```json
// Response
[
  {
    "id": "res123",
    "database_id": "db123",
    "name": "Project Specs",
    "path": "/home/user/specs",
    "resource_type": "directory",
    "qmd_collection": "notes-db123-res123",
    "indexed_at": "2026-03-03T16:00:00",
    "file_count": 42,
    "created_at": "2026-03-03T15:00:00"
  }
]
```

#### POST `/api/databases/<db_id>/resources`
Add a resource.
```json
{
  "path": "/absolute/path/to/directory",
  "name": "Display Name"
}
```

**Notes:**
- `path` must exist on the server filesystem
- `~` is expanded to the home directory
- `name` is auto-detected from the path basename if omitted
- `resource_type` is auto-detected (file or directory)

```json
// Response 200
{"id": "res_id", "name": "...", "path": "...", "resource_type": "directory", "database_id": "..."}

// Response 400
{"error": "Path does not exist: /invalid/path"}
```

#### DELETE `/api/databases/<db_id>/resources/<res_id>`
Delete a resource and its QMD collection.

#### POST `/api/databases/<db_id>/resources/<res_id>/index`
Index a resource with QMD. Creates a collection, indexes files, and generates vector embeddings.

```json
// Response 200
{
  "status": "indexed",
  "collection": "notes-db123-res123",
  "file_count": 42,
  "output": "Indexed: 42 new, 0 updated..."
}

// Response 500
{"error": "QMD indexing failed: ..."}
```

**What happens:**
1. Old QMD collection removed (if re-indexing)
2. New collection created: `qmd collection add <path> --name notes-<db_id>-<res_id> --mask <pattern>`
3. Embeddings generated: `qmd embed`
4. File count updated in database

#### GET `/api/databases/<db_id>/resources/search?q=<query>`
Semantic search across all indexed resources.

Query params: `q` (search query, required)

```json
// Response
{
  "results": [
    {
      "score": 0.93,
      "path": "security-report.md",
      "docid": "#46fac4",
      "snippet": "# Security Assessment Report\n\n## Findings...",
      "resource_name": "Project Specs",
      "resource_id": "res123"
    }
  ]
}
```

---

### Search

#### GET `/api/search?q=<query>`
Global keyword search across pages, blocks, and database items.

---

### AI Endpoints

#### POST `/api/ai/inline`
Inline text transformation.
```json
{
  "prompt": "Expand this paragraph with more detail",
  "content": "The system uses microservices.",
  "action": "expand"
}
```

Actions: `generate`, `expand`, `summarize`, `simplify`, `fix_grammar`, `translate`, `change_tone`

#### POST `/api/ai/block`
AI operation on a block.
```json
{
  "block_id": "block123",
  "action": "rewrite",
  "prompt": "Make it more concise"
}
```

#### POST `/api/ai/research`
Deep research with web search.
```json
{"query": "GDPR compliance requirements for SaaS"}
```

#### POST `/api/ai/translate-page`
Translate an entire page.
```json
{"page_id": "page123", "target_language": "German"}
```

#### POST `/api/chat`
Send a chat message to the AI assistant.
```json
{"message": "List all my projects", "session_id": "default"}
```

The AI can call tools (function calling) to interact with notes.

#### GET `/api/chat/history?session_id=default&limit=50`
Get chat history.

#### POST `/api/chat/clear`
Clear chat history.
```json
{"session_id": "default"}
```

#### GET `/api/chat/config`
Get chat configuration (system prompt, model).

#### PUT `/api/chat/config`
Update chat configuration.

---

### LLM Provider Management

#### GET `/api/llm/config`
Get LLM configuration (default provider, model, system prompt).

#### PUT `/api/llm/config`
Update default LLM settings.

#### GET `/api/llm/providers`
List configured LLM providers.

#### POST `/api/llm/providers`
Add a new LLM provider.
```json
{
  "name": "OpenAI",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "models": ["gpt-4", "gpt-3.5-turbo"]
}
```

#### PUT `/api/llm/providers/<provider_id>`
Update a provider.

#### DELETE `/api/llm/providers/<provider_id>`
Delete a provider.

#### POST `/api/llm/test`
Test a provider connection.
```json
{"provider_id": "minimax"}
```

---

### Admin Endpoints

All admin endpoints require `role: admin`.

#### GET/POST `/api/admin/users`
List or create users.

#### PUT/DELETE `/api/admin/users/<user_id>`
Update or delete users.

#### GET/POST `/api/teams`
List or create teams.

#### PUT/DELETE `/api/teams/<team_id>`
Update or delete teams.

#### POST/PUT/DELETE `/api/teams/<team_id>/members[/<user_id>]`
Manage team membership.

#### GET/POST/DELETE `/api/permissions[/<perm_id>]`
Manage granular permissions.

---

## MCP Server Reference

The MCP server exposes 18 tools via the Model Context Protocol. Start it with:

```bash
# stdio transport (for MCP clients like Claude)
python3.12 mcp_server.py

# HTTP transport (for remote access)
python3.12 -m mcp_server --http --port 8182
```

### Tools

#### Search & Read

| Tool | Parameters | Description |
|------|-----------|-------------|
| `search_notes` | `query: str` | Keyword search across all content |
| `list_pages` | `workspace: str = "all"` | List pages, filterable by workspace |
| `get_page` | `page_id: str` | Get full page content with blocks |
| `list_databases` | — | List all databases with schemas |
| `get_database_items` | `database_id: str` | Get all items in a database |
| `get_all_content` | — | Complete content overview (all pages, databases, items) |

#### Create

| Tool | Parameters | Description |
|------|-----------|-------------|
| `create_page` | `title, blocks, icon?, workspace?, parent_id?` | Create page with blocks (JSON array) |
| `create_database` | `title, workspace?, description?` | Create project or knowledge base |
| `create_database_item` | `database_id, title, properties?` | Add item to database |

#### Edit

| Tool | Parameters | Description |
|------|-----------|-------------|
| `edit_page` | `page_id, title?, icon?, replace_blocks?, append_blocks?` | Edit page content |
| `update_database_item` | `database_id, item_id, title?, properties?` | Update item |

#### Delete

| Tool | Parameters | Description |
|------|-----------|-------------|
| `delete_page` | `page_id: str` | Delete page and blocks |
| `delete_database_item` | `database_id, item_id` | Delete database item |

#### Resources (Project Files)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_resources` | `database_id: str` | List project resources |
| `add_resource` | `database_id, path, name?` | Link file/directory to project |
| `remove_resource` | `database_id, resource_id` | Remove resource + QMD index |
| `index_resource` | `database_id, resource_id` | Create QMD embeddings |
| `search_resources` | `database_id, query` | Semantic search across indexed files |

### MCP Configuration (for OpenClaw)

Add to your OpenClaw MCP config:

```json
{
  "mcpServers": {
    "brain-notes": {
      "command": "python3.12",
      "args": ["/path/to/brain-notes/mcp_server.py"],
      "cwd": "/path/to/brain-notes"
    }
  }
}
```

### Tool Usage Examples

**Search and summarize:**
```
1. search_notes("architecture") → find relevant pages
2. get_page("page_id") → read full content
3. Summarize in response
```

**Create a project with tasks:**
```
1. create_database("Sprint 42", "projects", "March sprint")
2. list_databases() → get database_id and property IDs
3. create_database_item(db_id, "Build login page", '{"status_prop": "In Progress"}')
```

**Index and search project files:**
```
1. add_resource(db_id, "~/projects/backend", "Backend Code")
2. index_resource(db_id, resource_id)
3. search_resources(db_id, "authentication middleware")
```

---

## Extending Brain Notes

### Adding a New Block Type

1. **Backend** (`app.py`): No changes needed — blocks are type-agnostic.
2. **Frontend** (`index.html`):
   - Add rendering in the block renderer function
   - Add to the `/` block type menu
   - Add CSS styles
3. **notes_tools.py**: Update `get_page()` prefix mapping if needed.

### Adding a New Property Type

1. **Frontend** (`index.html`):
   - Add rendering in `renderPropValue()`
   - Add editor in the property edit modal
   - Add to property type dropdown
2. **Backend**: Properties are stored as JSON — no schema changes needed.

### Adding a New API Endpoint

1. Add route in `app.py` with `@app.route`
2. Add `@login_required` decorator
3. Add permission check if resource-scoped
4. If it should be accessible to AI agents:
   - Add function to `notes_tools.py`
   - Add MCP tool wrapper in `mcp_server.py`
   - Update the AI system prompt's tool list

### Adding a New MCP Tool

1. Add business logic to `notes_tools.py`
2. Add thin wrapper in `mcp_server.py`:

```python
@mcp.tool()
def my_new_tool(param1: str, param2: int = 0) -> str:
    """Tool description for the AI model.
    
    Args:
        param1: Description of param1
        param2: Description of param2
    """
    return notes_tools.my_new_function(param1, param2)
```

### File Format Reference

**Block JSON:**
```json
{
  "type": "todo",
  "content": "Task description",
  "properties": {"checked": false},
  "sort_order": 0,
  "indent_level": 0
}
```

**Database properties JSON:**
```json
{
  "prop_id_1": "Selected Option",
  "prop_id_2": ["Tag1", "Tag2"],
  "prop_id_3": "2026-03-03",
  "prop_id_4": true
}
```

**LLM config JSON (`llm_config.json`):**
```json
{
  "default_provider": "provider_id",
  "default_model": "model-name",
  "system_prompt": "You are...",
  "providers": {
    "provider_id": {
      "name": "Display Name",
      "base_url": "https://api.example.com/v1",
      "api_key": "sk-...",
      "models": ["model-1", "model-2"]
    }
  }
}
```
