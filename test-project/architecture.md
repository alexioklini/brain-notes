# System Architecture

The application uses a three-tier architecture with a React frontend, Flask API backend, and PostgreSQL database. Authentication is handled via JWT tokens with refresh token rotation. The API gateway uses rate limiting and request validation middleware.

## Key Components
- **Frontend:** React 18 with TypeScript, Zustand for state management
- **Backend:** Flask with SQLAlchemy ORM
- **Database:** PostgreSQL 16 with pgvector extension for embeddings
- **Cache:** Redis for session management and API caching
