# CLAUDE.md - AI Assistant Guide for nifty-bot-v4

## Project Overview

**nifty-bot-v4** is a privacy-focused chatbot web service built with Python FastAPI and Google's Gemini AI (gemini-2.5-flash-lite via Vertex AI). The bot is themed as a "White Rabbit from Alice in Wonderland" with a focus on rabbit-themed NFTs on Ethereum L1 and L2.

**Key Characteristics:**
- **Language:** Python 3.12
- **Framework:** FastAPI (async web framework)
- **AI Model:** Google Gemini 2.5 Flash Lite (via Vertex AI)
- **Deployment:** Google Cloud Run (serverless containers)
- **Architecture:** Single-file monolithic application
- **License:** MIT License (Copyright 2025 Stephen Oravec)

---

## Privacy-First Philosophy

**CRITICAL:** This project prioritizes user privacy above all else. When working on this codebase, always maintain these privacy principles:

1. **Never log message content** - Only log metadata (counts, lengths, hashes)
2. **Hash session IDs** - Use `hash_session_id()` for all logging (SHA-256 truncated to 8 chars)
3. **Ephemeral storage** - Database lives in `/tmp/sessions.db` (cleared on Cloud Run restarts)
4. **No training data** - Uses Vertex AI which doesn't use data for training
5. **Privacy-safe error handling** - Only log exception types, never details containing user data

**Example of privacy-safe logging:**
```python
# GOOD - Privacy-safe
session_hash = hash_session_id(session_id)
logger.info(f"Session {session_hash}: Loaded {len(messages)} messages")

# BAD - Privacy violation
logger.info(f"Session {session_id}: User said: {message}")
```

---

## Codebase Structure

### File Organization

```
/home/user/nifty-bot-v4/
├── .git/                    # Git repository
├── .gitignore              # Python-standard gitignore
├── Dockerfile              # Container definition for Cloud Run
├── LICENSE                 # MIT License
├── README.md               # Minimal documentation
├── main.py                 # Main application (264 lines, ALL logic here)
├── requirements.in         # Direct dependencies (3 packages)
└── requirements.txt        # Locked dependencies (pip-compile generated)
```

**Important:** This is a **single-file application**. All code lives in `main.py` - no subdirectories, no modules, no packages.

### main.py Structure (Lines Reference)

The file is organized into clearly commented sections:

1. **Lines 1-10:** Imports
2. **Lines 11-18:** Logging setup
3. **Lines 19-33:** Configuration (env vars, Vertex AI init)
4. **Lines 34-40:** Privacy helpers (`hash_session_id()`)
5. **Lines 41-98:** Session Manager class (SQLite)
6. **Lines 99-163:** Chat logic (`chat_with_gemini()`)
7. **Lines 164-230:** API routes (`/chat`, `/health`)
8. **Lines 231-264:** Lifecycle hooks (startup/shutdown)

**Section Separators:** Code sections are marked with `# ------` comment lines.

---

## Architecture & Design Patterns

### 1. Session Management Pattern

**Flow:**
1. Client sends `POST /chat` with optional `session_id` and `message`
2. If no `session_id`, generate new token: `secrets.token_urlsafe(32)` (256-bit entropy)
3. Load conversation history from SQLite (last 20 messages)
4. Send to Gemini with history context
5. Save user message + assistant response to SQLite
6. Return `{"response": "...", "session_id": "..."}`

**Storage Format:**
- **Database:** SQLite at `/tmp/sessions.db`
- **Schema:** `sessions(session_id TEXT PRIMARY KEY, messages TEXT)`
- **Messages:** Stored as JSON array: `[{"role": "user", "text": "..."}, ...]`
- **History Limit:** Last 20 messages kept in context

### 2. Async-First Architecture

**All routes and core functions use async/await:**
```python
async def chat_with_gemini(session_id: str, user_message: str) -> str:
    # ... async logic

@app.post("/chat")
async def chat(request: Request):
    # ... async route
```

**Why:** Non-blocking I/O for concurrent request handling.

### 3. Error Handling Strategy

**Graceful Degradation:**
```python
try:
    reply = await chat_with_gemini(session_id, message)
except Exception as gemini_error:
    logger.exception(f"Session {session_hash}: Chat failed")
    return {
        "response": "Sorry, I encountered an error. Please try again!",
        "session_id": session_id
    }
```

**Principles:**
- Never expose technical errors to users
- Log exceptions with privacy-safe session hashes
- Return friendly error messages
- Use proper HTTP status codes (400 for validation, 500 for server errors)

### 4. Gemini Integration Pattern

**Building History for Gemini:**
```python
history = []
for msg in memory:
    if msg["role"] == "user":
        history.append(Content(role="user", parts=[Part.from_text(msg["text"])]))
    elif msg["role"] == "assistant":
        history.append(Content(role="model", parts=[Part.from_text(msg["text"])]))
```

**Key Points:**
- Use `Content` and `Part` objects from `vertexai.generative_models`
- User role = "user", Assistant role = "model" (Gemini convention)
- System instruction passed at model initialization (lines 115-119)

---

## Development Workflows

### Making Code Changes

**Current Limitations:**
- ❌ No automated tests
- ❌ No CI/CD pipeline
- ❌ No linting configuration
- ❌ No type checking (mypy/pyright)
- ✅ Privacy-safe logging throughout

**When modifying code:**

1. **Read the entire main.py file first** - It's only 264 lines
2. **Maintain section organization** - Keep the `# ------` separators
3. **Privacy check** - Never log user data or session IDs in plain text
4. **Test locally** before deploying:
   ```bash
   # Set required environment variable
   export GCP_PROJECT_ID="your-project-id"

   # Install dependencies
   pip install -r requirements.txt

   # Run server
   uvicorn main:app --reload

   # Test health endpoint
   curl http://localhost:8000/health

   # Test chat endpoint
   curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "Hello!"}'
   ```

### Adding Dependencies

**Process:**
1. Add to `requirements.in` (direct dependencies only)
2. Run `pip-compile requirements.in` to generate `requirements.txt`
3. Commit both files

**Example:**
```bash
# Add new dependency
echo "requests" >> requirements.in

# Regenerate locked dependencies
pip-compile requirements.in

# Verify
git diff requirements.txt
```

### Deployment Workflow

**Target:** Google Cloud Run

**Required Environment Variables:**
- `GCP_PROJECT_ID` (required) - Your GCP project ID
- `GCP_LOCATION` (optional) - Defaults to "us-central1"

**Deployment Steps:**
1. Build Docker image:
   ```bash
   docker build -t nifty-bot-v4 .
   ```

2. Tag for Google Container Registry:
   ```bash
   docker tag nifty-bot-v4 gcr.io/YOUR_PROJECT_ID/nifty-bot-v4
   ```

3. Push to GCR:
   ```bash
   docker push gcr.io/YOUR_PROJECT_ID/nifty-bot-v4
   ```

4. Deploy to Cloud Run:
   ```bash
   gcloud run deploy nifty-bot-v4 \
     --image gcr.io/YOUR_PROJECT_ID/nifty-bot-v4 \
     --platform managed \
     --region us-central1 \
     --set-env-vars GCP_PROJECT_ID=YOUR_PROJECT_ID
   ```

---

## Key Conventions & Style Guide

### Naming Conventions

**Files:** `lowercase-with-hyphens.py`
- Examples: `main.py`, `requirements.txt`

**Functions:** `snake_case`
- Examples: `chat_with_gemini()`, `hash_session_id()`, `save_message()`

**Classes:** `PascalCase`
- Examples: `SessionManager`, `GenerativeModel`

**Constants:** `UPPER_SNAKE_CASE`
- Examples: `PROJECT_ID`, `LOCATION`, `DB_PATH`

**Variables:** `snake_case`
- Examples: `session_id`, `user_message`, `reply`

### Code Organization

**Section Headers:**
```python
# ----------------------
# Section Name
# ----------------------
```

**Docstrings:**
- Functions: Triple-quoted strings explaining purpose
- Classes: Describe responsibility
- Routes: Document request/response format

**Example:**
```python
async def chat_with_gemini(session_id: str, user_message: str) -> str:
    """Chat with Gemini using session memory."""
    # Implementation...
```

### Import Order

1. Standard library (fastapi, os, sqlite3, etc.)
2. Third-party packages (vertexai)
3. Local imports (none in this project)

**Example:**
```python
from fastapi import FastAPI, Request, HTTPException
import os
import sqlite3
import secrets
import logging
import json
import hashlib
import vertexai
from vertexai.generative_models import GenerativeModel, Content, Part
```

---

## Configuration Management

### Environment Variables

**Required:**
- `GCP_PROJECT_ID` - Google Cloud Project ID for Vertex AI

**Optional:**
- `GCP_LOCATION` - Defaults to "us-central1"
- `PORT` - Server port (Cloud Run sets this, defaults to 8080 in Dockerfile)

**Loading Pattern:**
```python
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")

if not PROJECT_ID:
    logger.error("GCP_PROJECT_ID not set!")
    raise RuntimeError("GCP_PROJECT_ID environment variable is required")
```

**Runtime Validation:** Application fails fast if required config is missing.

---

## Dependencies & External Services

### Direct Dependencies (requirements.in)

```
fastapi              # Web framework
uvicorn[standard]    # ASGI server with performance extras
google-cloud-aiplatform  # Vertex AI SDK (Gemini)
```

### Key Transitive Dependencies

- **grpcio** (1.76.0) - gRPC communication with Google APIs
- **pydantic** (2.12.5) - Request/response validation
- **httpx** (0.28.1) - Async HTTP client
- **numpy** (2.3.5) - Scientific computing (via shapely)

### External Services

**Google Cloud Vertex AI:**
- **Model:** gemini-2.5-flash-lite
- **Authentication:** Application Default Credentials (ADC)
- **Privacy:** Data not used for training per Vertex AI policy
- **Initialization:** `vertexai.init(project=PROJECT_ID, location=LOCATION)`

**SQLite:**
- **Built-in:** No external dependency
- **Location:** `/tmp/sessions.db` (ephemeral)
- **Cleared:** On Cloud Run container restarts

---

## API Reference

### POST /chat

**Purpose:** Send a message to the chatbot and receive a response.

**Request:**
```json
{
  "session_id": "optional-session-id",
  "message": "user message"
}
```

**Response:**
```json
{
  "response": "bot response",
  "session_id": "session-id"
}
```

**Behavior:**
- If `session_id` is omitted, a new session is created
- Message is required (400 error if empty)
- Session history (last 20 messages) is included in Gemini context
- On Gemini errors, returns friendly message with same session_id

**Example:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me about rabbit NFTs!"}'
```

### GET /health

**Purpose:** Health check endpoint for Cloud Run.

**Response:**
```json
{
  "status": "ok"
}
```

**Use Case:** Cloud Run uses this to verify service health.

---

## Testing Guidelines

**Current State:** ❌ **No testing infrastructure exists**

### If Adding Tests (Recommendations)

1. **Create test directory:**
   ```
   tests/
   ├── __init__.py
   ├── test_main.py
   ├── test_privacy.py
   └── conftest.py
   ```

2. **Add pytest to requirements.in:**
   ```
   pytest
   pytest-asyncio
   httpx  # For testing FastAPI
   ```

3. **Key areas to test:**
   - Privacy: Verify no session IDs or messages in logs
   - Session management: CRUD operations
   - API routes: Request/response validation
   - Error handling: Graceful degradation
   - Gemini integration: Mock responses

4. **Example test structure:**
   ```python
   import pytest
   from fastapi.testclient import TestClient
   from main import app, hash_session_id

   client = TestClient(app)

   def test_health_endpoint():
       response = client.get("/health")
       assert response.status_code == 200
       assert response.json() == {"status": "ok"}

   def test_privacy_session_hash():
       session_id = "test-session-123"
       hashed = hash_session_id(session_id)
       assert len(hashed) == 8
       assert session_id not in hashed
   ```

---

## Security Considerations

### Strengths

✅ **Privacy-focused logging** - No PII in logs
✅ **Secure token generation** - `secrets.token_urlsafe(32)`
✅ **Input validation** - FastAPI/Pydantic automatic validation
✅ **No hardcoded credentials** - Environment-based config
✅ **Parameterized queries** - SQLite injection protection

### Known Gaps (Potential Improvements)

⚠️ **No rate limiting** - Endpoint can be spammed
⚠️ **No authentication** - /chat is completely public
⚠️ **No session expiration** - Old sessions persist until container restart
⚠️ **No input sanitization** - Messages passed directly to Gemini (relies on Gemini's safety)
⚠️ **Session hijacking risk** - Anyone with a session_id can access that conversation

**If Adding Security Features:**

1. **Rate limiting:**
   ```python
   from slowapi import Limiter, _rate_limit_exceeded_handler
   from slowapi.util import get_remote_address

   limiter = Limiter(key_func=get_remote_address)
   app.state.limiter = limiter

   @app.post("/chat")
   @limiter.limit("10/minute")
   async def chat(request: Request):
       # ...
   ```

2. **Authentication:**
   ```python
   from fastapi import Header, HTTPException

   async def verify_api_key(x_api_key: str = Header(...)):
       if x_api_key != os.getenv("API_KEY"):
           raise HTTPException(status_code=403, detail="Invalid API key")
   ```

---

## Common Tasks & How-To Guide

### Task: Modify the Bot's Personality

**File:** `main.py` (lines 115-119)

**Steps:**
1. Locate the `system_instruction` variable in `chat_with_gemini()`
2. Modify the instruction text
3. Test locally before deploying

**Example:**
```python
system_instruction = (
    "You are a friendly AI assistant specializing in cryptocurrency. "
    "Keep responses concise and educational."
)
```

### Task: Change the Gemini Model

**File:** `main.py` (line 123)

**Steps:**
1. Find `GenerativeModel("gemini-2.5-flash-lite", ...)`
2. Replace with desired model (e.g., "gemini-1.5-pro")
3. Update startup log message (line 248)

**Available Models:**
- `gemini-2.5-flash-lite` (current, fastest)
- `gemini-2.0-flash-exp` (experimental)
- `gemini-1.5-pro` (more capable, slower)
- `gemini-1.5-flash` (balanced)

### Task: Adjust Conversation History Limit

**File:** `main.py` (line 70)

**Current:** Last 20 messages kept in context

**Steps:**
1. Locate `get_messages(self, session_id: str, limit: int = 20)`
2. Change default `limit` value
3. Consider Gemini token limits (varies by model)

### Task: Add a New API Endpoint

**File:** `main.py` (after line 235, before startup event)

**Pattern:**
```python
@app.get("/new-endpoint")
async def new_endpoint():
    """Description of endpoint."""
    return {"key": "value"}
```

**Best Practices:**
- Use appropriate HTTP method decorator (@app.get, @app.post, etc.)
- Add docstring with request/response format
- Return JSON-serializable dictionaries
- Add privacy-safe logging if needed

### Task: Change Database Location

**File:** `main.py` (line 45)

**Current:** `/tmp/sessions.db` (ephemeral on Cloud Run)

**Steps:**
1. Change `DB_PATH` constant
2. Ensure new location is writable
3. Update startup log message (line 249)

**Note:** Cloud Run only supports writing to `/tmp`. For persistent storage, use Cloud SQL or Firestore.

### Task: Add Request Logging

**File:** `main.py` (in `/chat` route)

**Pattern:**
```python
@app.post("/chat")
async def chat(request: Request):
    # Privacy-safe logging only
    logger.info(f"Received request from {request.client.host}")
    # ... rest of function
```

**Remember:** NEVER log message content or unhashed session IDs.

---

## Troubleshooting

### Issue: "GCP_PROJECT_ID not set!" Error

**Cause:** Missing required environment variable

**Solution:**
```bash
export GCP_PROJECT_ID="your-project-id"
# or
echo 'export GCP_PROJECT_ID="your-project-id"' >> ~/.bashrc
```

### Issue: Vertex AI Authentication Errors

**Cause:** Application Default Credentials not configured

**Solution:**
```bash
# Login to gcloud
gcloud auth login

# Set application default credentials
gcloud auth application-default login

# Or use service account key
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

### Issue: Database Locked Errors

**Cause:** SQLite single-writer limitation (rare with async)

**Solution:**
- This shouldn't happen on Cloud Run (single instance per container)
- If it occurs, consider connection pooling or switch to Cloud SQL

### Issue: Sessions Lost After Restart

**Expected Behavior:** `/tmp/sessions.db` is ephemeral on Cloud Run

**Solution:**
- If persistence needed, migrate to Cloud SQL, Firestore, or Cloud Memorystore
- Current design prioritizes privacy over persistence

---

## Future Improvements (If Requested)

### Testing Infrastructure
- Add pytest, pytest-asyncio, httpx
- Create `tests/` directory
- Implement unit tests for SessionManager
- Add integration tests for API endpoints
- Mock Gemini responses for testing

### Observability
- Add structured logging (JSON format)
- Integrate Cloud Logging
- Add metrics (Prometheus/Cloud Monitoring)
- Track: request count, latency, error rate, session count

### Security Enhancements
- Implement rate limiting (slowapi or Cloud Armor)
- Add API key authentication
- Session expiration (TTL in database)
- Input sanitization (content moderation)
- CORS configuration for web clients

### Scalability
- Migrate to Cloud SQL for persistent sessions
- Add Redis/Memorystore for caching
- Implement connection pooling
- Multi-file organization as codebase grows

### Code Quality
- Add type hints throughout
- Configure mypy or pyright
- Add Ruff or Black for formatting
- Pre-commit hooks for linting
- Docstring coverage enforcement

---

## AI Assistant Guidelines

### When Working on This Codebase

1. **Always read main.py first** - It's the entire application (264 lines)

2. **Privacy is paramount:**
   - Never log session IDs in plain text
   - Never log message content
   - Always use `hash_session_id()` for logging

3. **Maintain simplicity:**
   - Don't over-engineer solutions
   - Keep the single-file structure unless explicitly asked to refactor
   - Avoid adding unnecessary dependencies

4. **Test changes locally:**
   - Set `GCP_PROJECT_ID` environment variable
   - Run with `uvicorn main:app --reload`
   - Verify privacy-safe logging

5. **Follow existing patterns:**
   - Use section comment separators
   - Maintain async/await for routes
   - Keep error handling graceful
   - Follow naming conventions

6. **Document changes:**
   - Update docstrings if modifying functions
   - Update this CLAUDE.md if architecture changes
   - Add comments for complex logic

7. **Security mindset:**
   - Consider rate limiting implications
   - Think about authentication needs
   - Validate all user inputs
   - Never expose technical errors to users

8. **Git workflow:**
   - Work on feature branches (claude/*)
   - Write clear commit messages
   - Push to designated branch only

---

## Quick Reference

### File Locations
- Main application: `/home/user/nifty-bot-v4/main.py`
- Dependencies: `/home/user/nifty-bot-v4/requirements.in`
- Locked deps: `/home/user/nifty-bot-v4/requirements.txt`
- Docker config: `/home/user/nifty-bot-v4/Dockerfile`
- This guide: `/home/user/nifty-bot-v4/CLAUDE.md`

### Key Functions
- `hash_session_id(session_id)` - Privacy-safe logging (line 38)
- `chat_with_gemini(session_id, user_message)` - AI interaction (line 104)
- `SessionManager.get_messages(session_id, limit=20)` - Load history (line 70)
- `SessionManager.save_message(session_id, role, text)` - Save message (line 84)

### Environment Variables
- `GCP_PROJECT_ID` (required) - GCP project for Vertex AI
- `GCP_LOCATION` (optional, default: "us-central1")
- `PORT` (optional, default: 8080)

### API Endpoints
- `POST /chat` - Main chatbot endpoint
- `GET /health` - Health check for Cloud Run

### Running Locally
```bash
export GCP_PROJECT_ID="your-project-id"
pip install -r requirements.txt
uvicorn main:app --reload
```

### Testing Endpoints
```bash
# Health check
curl http://localhost:8000/health

# Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!"}'
```

---

**Last Updated:** 2025-12-03
**Codebase Version:** main.py (264 lines), gemini-2.5-flash-lite model
**Deployment Target:** Google Cloud Run
