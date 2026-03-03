# Brain Notes 🧠📝

A self-hosted, Notion-inspired notes application with AI-powered features, semantic search, and MCP (Model Context Protocol) integration.

## Features

### 📄 Documents
- Rich block-based editor (headings, lists, todos, quotes, code, callouts)
- Wiki-links with `[[page-name]]` syntax and backlinks
- Nested pages with drag-and-drop reordering
- Full-text search across all content
- Favorites and workspace organization

### 📊 Projects & Knowledge Bases
- **Projects** — Kanban boards with customizable properties (status, priority, dates, tags)
- **Knowledge Bases** — Table/list views for structured information
- Multiple views per database (Table, Board, List)
- Drag-and-drop card management

### 📁 Project Resources (NEW)
- Link files and directories to projects
- **QMD-powered semantic search** across project files
- Automatic vector embedding for intelligent retrieval
- Supports Markdown, text, PDF, and more
- Index, re-index, and manage resources through UI or API

### 🤖 AI Integration
- **Chat assistant** — conversational AI that can read/write notes, manage projects
- **Inline AI** — generate, expand, summarize, translate content in-place
- **Block AI** — AI-powered block operations (rewrite, continue, explain)
- **Research mode** — deep research with web search integration
- **Page translation** — translate entire pages to any language
- **Configurable LLM providers** — MiniMax, OpenAI-compatible, or any provider

### 🔐 Multi-User & Permissions
- User management with roles (admin, user)
- Team-based collaboration
- Granular permissions (read, write, admin) per page/database
- Session-based authentication

### 🔌 MCP Server
- Full MCP integration for external AI agents
- 18 tools for complete CRUD + search + resource management
- Compatible with Claude, OpenClaw, and any MCP client

## Quick Start

```bash
# Clone
git clone https://github.com/alexioklini/brain-notes.git
cd brain-notes

# Install dependencies
python3.12 -m venv .venv
source .venv/bin/activate
pip install flask flask-cors mcp

# Run
python3.12 app.py
# → http://localhost:5006

# Default login: admin / admin
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12 + Flask |
| Database | SQLite (WAL mode) |
| Frontend | Vanilla JS/CSS (single HTML file) |
| Search | QMD (vector embeddings + BM25) |
| AI | OpenAI-compatible API (configurable) |
| MCP | FastMCP (Python) |
| Icons | Lucide Icons (CDN) |
| Fonts | Inter + JetBrains Mono (Google Fonts) |

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture Handbook](docs/ARCHITECTURE.md) | System design, data model, component overview |
| [Deployment & Administration](docs/DEPLOYMENT.md) | Installation, configuration, maintenance |
| [User Manual](docs/USER_MANUAL.md) | How to use Brain Notes |
| [Developer Documentation](docs/DEVELOPER.md) | API reference, MCP tools, extending the app |

## Project Structure

```
brain-notes/
├── app.py              # Flask backend (API + static serving)
├── notes_tools.py      # Shared business logic (used by app.py + MCP)
├── mcp_server.py       # MCP Server (FastMCP wrapper)
├── mcp_client.py       # MCP client utilities
├── llm_config.json     # LLM provider configuration
├── notes.db            # SQLite database
├── run.sh              # Start script
├── static/
│   ├── index.html      # Main application (SPA)
│   └── login.html      # Login page
├── docs/               # Documentation
├── test-project/       # Sample project resources
└── SPEC.md             # Original specification
```

## License

Private project. All rights reserved.
