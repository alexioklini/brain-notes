# User Manual

## Getting Started

### Login

Navigate to `https://notes.yourdomain.com` (or `http://localhost:5006`). Enter your username and password.

Default credentials: `admin` / `admin` — change your password immediately via the user menu (top-right).

### Interface Overview

```
┌──────────────┬──────────────────────────────────────────────┐
│              │  Breadcrumbs                         🔍 ⚙️ 💬 │
│   Sidebar    ├──────────────────────────────────────────────┤
│              │                                              │
│  🔍 Search   │              Content Area                    │
│              │                                              │
│  📄 Docs     │    (Page editor, Database view,              │
│  📊 Projects │     or Welcome screen)                       │
│  📚 Wiki     │                                              │
│              │                                              │
│  ⭐ Favorites │                                              │
│              │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

### Workspaces

Brain Notes has three workspaces, accessible via tabs in the sidebar:

| Workspace | Purpose | Content Type |
|-----------|---------|-------------|
| **Docs** | Free-form notes and documents | Pages with blocks |
| **Projects** | Task and project management | Databases with kanban boards |
| **Wiki** | Structured knowledge | Databases with table views |

## Working with Pages (Docs)

### Creating a Page

1. Click **+ New page** in the Docs section of the sidebar
2. A new untitled page opens in the editor
3. Click the title to rename it
4. Start typing to add content

### Block Types

Click on an empty block or press `/` to see available block types:

| Block | Shortcut | Description |
|-------|----------|-------------|
| Text | (default) | Plain paragraph |
| Heading 1 | `# ` | Large heading |
| Heading 2 | `## ` | Medium heading |
| Heading 3 | `### ` | Small heading |
| Bullet List | `- ` | Unordered list item |
| Numbered List | `1. ` | Ordered list item |
| To-Do | `[] ` | Checkbox item |
| Quote | `> ` | Blockquote |
| Code | ` ``` ` | Code block |
| Callout | | Info/warning/tip box |
| Divider | `---` | Horizontal separator |

### Editing Blocks

- **Click** a block to select and edit it
- **Enter** creates a new block below
- **Backspace** on empty block deletes it and merges with previous
- **Tab** indents a block (nested lists)
- **Shift+Tab** outdents a block
- **Drag handle** (left side) to reorder blocks

### Page Operations

- **Rename** — Click the title at the top
- **Change icon** — Click the icon next to the title
- **Favorite** — Star icon in the page header
- **Nest pages** — Drag a page onto another in the sidebar
- **Delete** — Right-click menu or `...` menu on the page

### Search

Use the search bar at the top of the sidebar to find pages by title or content. Results show matching pages and content snippets.

## Working with Projects

### Creating a Project

1. Switch to the **Projects** tab in the sidebar
2. Click **+ New project**
3. A new project board opens with default properties (Status, Priority, Due Date)

### Views

Each project supports multiple views:

| View | Best For |
|------|---------|
| **Board** (Kanban) | Visual task management, drag between columns |
| **Table** | Spreadsheet-like overview of all items |
| **List** | Compact list with key properties |

Switch views using the tabs above the content area. Click **+** to add a new view.

### Managing Items

- **Add item** — Click "+ New" at the bottom of a table/list, or in a board column
- **Edit item** — Click on any item to open the detail editor
- **Change properties** — Click on a property cell to edit inline
- **Drag & drop** — In board view, drag cards between columns to change status
- **Delete** — Open item detail → Delete button

### Custom Properties

Projects come with default properties. To customize:

1. Open the project
2. Click **+ Property** in the table header
3. Choose a property type:
   - **Text** — Free text
   - **Number** — Numeric value
   - **Date** — Date picker
   - **Select** — Single choice from options
   - **Multi-Select** — Multiple tags
   - **Checkbox** — Boolean toggle
   - **URL** — Clickable link
   - **Email** — Email address
   - **Phone** — Phone number

### Project Resources

Link files and directories to your project for AI-powered semantic search:

1. Open a project
2. Click the **Resources** tab (right side of the view tabs)
3. Enter a file or directory path (e.g., `~/Documents/project-specs`)
4. Optionally give it a name
5. Click **Add**
6. Click **Index** to create searchable vector embeddings
7. Use the **semantic search bar** to search across all indexed files

**Supported file types:** Markdown, text, PDF (text-based), code files

## Working with Knowledge Bases (Wiki)

### Creating a Knowledge Base

1. Switch to the **Wiki** tab in the sidebar
2. Click **+ New knowledge base**
3. A new table view opens with default properties (Status, Category)

Knowledge bases work like projects but default to table view and are intended for structured reference material.

## AI Features

### Chat Assistant 💬

Click the chat icon (💬) in the top-right corner to open the AI assistant.

**What it can do:**
- Answer questions about your notes
- Create new pages and projects
- Search and summarize content
- Modify existing pages
- Manage database items

**Example prompts:**
- "What pages do I have about architecture?"
- "Create a new page called Meeting Notes with today's agenda"
- "Summarize all items in the Project Alpha database"
- "Add a task called 'Review PR' to the Engineering project with high priority"

### Inline AI ✨

Select text in the editor and use the AI toolbar to:

- **Generate** — Create new content from a prompt
- **Expand** — Add more detail to selected text
- **Summarize** — Condense selected text
- **Simplify** — Make text easier to understand
- **Translate** — Convert to another language
- **Fix grammar** — Correct spelling and grammar
- **Change tone** — Professional, casual, technical, etc.

### Research Mode 🔬

In the chat, ask research-oriented questions to trigger deep research with web search:

- "Research the latest developments in quantum computing"
- "Find information about GDPR compliance requirements"

### Page Translation 🌐

Translate entire pages: Open the `...` menu on a page → Translate → Choose target language.

## Settings

### LLM Configuration ⚙️

Click the gear icon → **LLM Settings** to configure AI providers:

- **Default Provider** — Which AI service to use
- **Default Model** — Which model from that provider
- **System Prompt** — Customize the AI assistant's behavior
- **Add Provider** — Connect to OpenAI, MiniMax, Ollama, or any OpenAI-compatible API

### User Settings

Click your username (top-right) → **Change Password** to update your credentials.

### Admin Panel (Admin only)

Click your username → **Admin Panel** to manage:

- **Users** — Create, edit, delete user accounts
- **Teams** — Create teams and manage membership

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl/Cmd + K` | Quick search |
| `Enter` | New block |
| `Backspace` (empty) | Delete block |
| `Tab` | Indent block |
| `Shift + Tab` | Outdent block |
| `/` | Block type menu |
| `Ctrl/Cmd + B` | Bold |
| `Ctrl/Cmd + I` | Italic |

## Tips & Tricks

1. **Wiki-links** — Type `[[` to create a link to another page. Auto-complete suggests existing pages.
2. **Drag to nest** — Drag pages in the sidebar to create a hierarchy.
3. **Favorites** — Star frequently used pages for quick access.
4. **Board grouping** — Board views can group by any Select property.
5. **Search resources** — After indexing project files, use natural language queries like "authentication implementation" instead of exact keywords.
