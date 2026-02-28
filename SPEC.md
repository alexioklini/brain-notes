# Brain Notes — Obsidian-Clone Specification

## Overview
A self-hosted Obsidian-like notes app. Flask backend, SQLite, single-file HTML frontend.
Accessible at notes.alexklinsky.dev (Port 5006).

## Tech Stack
- **Backend:** Python 3.12 + Flask + flask-cors
- **Database:** SQLite (notes.db)
- **Frontend:** Single HTML file served by Flask (like nutrition-tracker pattern)
- **No npm, no build tools** — everything in vanilla JS/CSS

## Core Features

### 1. Markdown Editor
- Split-pane: Editor (left) + Live Preview (right)
- Use a lightweight JS markdown library (embed marked.js or similar via CDN)
- Syntax highlighting in editor (CodeMirror 6 via CDN)
- Auto-save on typing (debounced 1s)

### 2. Wiki-Links
- Support `[[note-name]]` syntax in markdown
- Clicking a wiki-link navigates to that note (creates it if it doesn't exist)
- Auto-complete suggestions when typing `[[`

### 3. Backlinks
- Show "Linked mentions" panel: which notes link to the current note
- Unlinked mentions: notes that contain the note's title but don't link it

### 4. Graph View
- Interactive force-directed graph (D3.js via CDN)
- Nodes = notes, Edges = links between them
- Click node to navigate to note
- Current note highlighted
- Zoom/pan support

### 5. File Explorer (Sidebar)
- Tree view with folders
- Create/rename/delete notes and folders
- Drag and drop to move
- Search/filter

### 6. Tags
- Support `#tag` syntax in notes
- Tag browser in sidebar
- Click tag to see all notes with that tag

### 7. Daily Notes
- Button to create/open today's daily note (YYYY-MM-DD format)
- Template support for daily notes

### 8. Full-Text Search
- Search across all notes
- Results show matching context snippets
- Keyboard shortcut (Ctrl+K or Cmd+K)

### 9. Dark Theme
- Obsidian-inspired dark theme (dark purple/gray)
- Clean, modern UI
- Responsive (works on mobile too)

## Database Schema

```sql
CREATE TABLE notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    folder TEXT DEFAULT '/',
    tags TEXT DEFAULT '[]',  -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_daily BOOLEAN DEFAULT 0,
    pinned BOOLEAN DEFAULT 0
);

CREATE TABLE links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES notes(id) ON DELETE CASCADE,
    target_id INTEGER REFERENCES notes(id) ON DELETE CASCADE,
    UNIQUE(source_id, target_id)
);

CREATE VIRTUAL TABLE notes_fts USING fts5(title, content, content=notes, content_rowid=id);
```

## API Endpoints

```
GET    /api/notes                — List all notes (with folder filter)
POST   /api/notes                — Create note
GET    /api/notes/<id>           — Get note
PUT    /api/notes/<id>           — Update note
DELETE /api/notes/<id>           — Delete note
GET    /api/notes/<id>/backlinks — Get backlinks for note
GET    /api/search?q=...         — Full-text search
GET    /api/graph                — Get graph data (nodes + edges)
GET    /api/tags                 — List all tags with counts
GET    /api/daily/<date>         — Get or create daily note
POST   /api/folders              — Create folder
DELETE /api/folders/<path>       — Delete folder
PUT    /api/notes/<id>/move      — Move note to folder
```

## File Structure
```
notes-app/
├── app.py          # Flask backend (ALL backend code here)
├── notes.db        # SQLite database
├── static/
│   └── index.html  # Single-page frontend (ALL frontend code here)
├── run.sh          # Startup script
└── SPEC.md         # This file
```

## UI Layout (Obsidian-inspired)
```
┌──────────┬────────────────────────────────────┐
│ Sidebar  │  Editor / Preview                  │
│          │                                    │
│ 📁 Files │  ┌─────────────┬──────────────────┐│
│ 🔍 Search│  │  Markdown   │  Live Preview    ││
│ 📊 Graph │  │  Editor     │                  ││
│ 🏷️ Tags  │  │             │                  ││
│ 📅 Daily │  │             │                  ││
│          │  │             │                  ││
│ ─────── │  │             │                  ││
│ Folders  │  │             │                  ││
│  📁 Work │  │             │                  ││
│  📁 Ideas│  └─────────────┴──────────────────┘│
│  📄 Note │  Backlinks panel (collapsible)     │
└──────────┴────────────────────────────────────┘
```

## UI Quality Requirements (CRITICAL — must look professional!)

### Visual Design
- **Catppuccin Mocha** color palette (the premium Obsidian look)
- Smooth transitions & animations everywhere (200-300ms ease)
- Subtle hover effects on all interactive elements
- Box shadows for depth (cards, modals, sidebar)
- Frosted glass / backdrop-blur effects for overlays
- Custom scrollbars (thin, matching theme)
- Proper typography: Inter or system font stack, good line-height (1.6)

### Editor Experience
- Line numbers in editor
- Active line highlighting
- Matching bracket highlighting
- Smooth cursor
- Minimap (optional toggle)
- Word count / character count in status bar

### Sidebar
- Smooth collapse/expand animations
- Active note highlighted with accent color + left border
- Hover states with subtle background change
- Collapsible folder sections with rotate animation on chevron
- Resize handle (drag to resize sidebar width)

### Graph View
- Animated node entrance (spring physics)
- Hover tooltip showing note title + link count
- Different node sizes based on connection count
- Color-coded: current note = accent, linked = secondary, others = muted
- Smooth zoom with mouse wheel
- Minimap in corner

### Search
- Modal overlay with backdrop blur (like Spotlight/Raycast)
- Results appear as you type (instant)
- Keyboard navigation (arrow keys + Enter)
- Result highlighting (matched text in bold)

### Status Bar
- Bottom bar with: word count, character count, last saved, current folder path
- Subtle, non-intrusive

### Responsive
- Mobile: sidebar becomes slide-out drawer
- Tablet: sidebar auto-collapses
- Touch-friendly button sizes

### Micro-interactions
- Save indicator (subtle pulse or checkmark)
- Note creation animation
- Smooth page transitions between notes
- Loading skeletons for graph view

## Important Notes
- Follow the same pattern as nutrition-tracker (Flask + single HTML)
- Use python3.12 specifically
- Port 5006
- Dark theme by default, Obsidian-style colors (#1e1e2e, #cdd6f4, #89b4fa)
- run.sh should be: `#!/bin/bash\ncd "$(dirname "$0")"\npython3.12 app.py`
- Include proper error handling and logging
- The app should work offline (CDN libs with fallback)
