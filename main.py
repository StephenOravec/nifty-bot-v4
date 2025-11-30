from fastapi import FastAPI, Request, HTTPException
import os
import sqlite3
import secrets
import logging
import json
import hashlib
import vertexai
from vertexai.generative_models import GenerativeModel

# ----------------------
# Logging Setup
# ----------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ----------------------
# Configuration
# ----------------------
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")

if not PROJECT_ID:
    logger.error("GCP_PROJECT_ID not set!")
    raise RuntimeError("GCP_PROJECT_ID environment variable is required")

# Initialize Vertex AI
vertexai.init(project=PROJECT_ID, location=LOCATION)

app = FastAPI()

# ----------------------
# Privacy Helpers
# ----------------------
def hash_session_id(session_id: str) -> str:
    """Create a short hash of session ID for privacy-safe logging."""
    return hashlib.sha256(session_id.encode()).hexdigest()[:8]

# ----------------------
# Session / Memory Setup
# ----------------------
DB_PATH = "/tmp/sessions.db"  # Ephemeral storage on Cloud Run


class SessionManager:
    """Handles ephemeral session memory using SQLite."""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    messages TEXT
                )
            """)
        logger.info("Database initialized")

    def get_messages(self, session_id: str, limit: int = 20):
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT messages FROM sessions WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            if row and row["messages"]:
                messages = json.loads(row["messages"])
                # Privacy-safe logging
                session_hash = hash_session_id(session_id)
                logger.info(f"Session {session_hash}: Loaded {len(messages)} messages")
                return messages[-limit:]
            return []

    def save_message(self, session_id: str, role: str, text: str):
        messages = self.get_messages(session_id)
        messages.append({"role": role, "text": text})
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions(session_id, messages) VALUES (?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET messages=?",
                (session_id, json.dumps(messages), json.dumps(messages))
            )
        # Privacy-safe logging
        session_hash = hash_session_id(session_id)
        logger.info(f"Session {session_hash}: Saved {role} message")


session_manager = SessionManager()


# ----------------------
# Chat with Gemini
# ----------------------
async def chat_with_gemini(session_id: str, user_message: str) -> str:
    """Chat with Gemini using session memory."""
    session_hash = hash_session_id(session_id)
    
    # Privacy-safe logging - no message content
    logger.info(f"Session {session_hash}: Processing request")
    
    # Load conversation history
    memory = session_manager.get_messages(session_id)
    
    # Build system instruction
    system_instruction = (
        "You are nifty-bot, a friendly AI agent inspired by the White Rabbit from "
        "Alice in Wonderland. You adore rabbit-themed NFTs on Ethereum L1 and L2. "
        "You often worry about the time. Be short, conversational, and rabbit-themed."
    )
    
    # Initialize Gemini model
    model = GenerativeModel(
        "gemini-1.5-flash-002",
        system_instruction=system_instruction
    )
    
    # Build chat history for Gemini
    history = []
    for msg in memory:
        if msg["role"] == "user":
            history.append({
                "role": "user",
                "parts": [{"text": msg["text"]}]
            })
        elif msg["role"] == "assistant":
            history.append({
                "role": "model",  # Gemini uses "model" not "assistant"
                "parts": [{"text": msg["text"]}]
            })
    
    # Privacy-safe logging - only metadata
    logger.info(f"Session {session_hash}: {len(history)} messages in context")
    
    try:
        # Create chat session
        chat = model.start_chat(history=history)
        
        # Send message
        response = chat.send_message(user_message)
        reply = response.text
        
        # Privacy-safe logging - only length
        logger.info(f"Session {session_hash}: Generated response ({len(reply)} chars)")
        return reply
        
    except Exception as e:
        # Privacy-safe error logging
        logger.exception(f"Session {session_hash}: Gemini error - {type(e).__name__}")
        raise


# ----------------------
# Routes
# ----------------------
@app.post("/chat")
async def chat(request: Request):
    """
    Chat endpoint for nifty-bot-v4.
    
    Expects JSON:
    {
        "session_id": "optional-session-id",
        "message": "user message"
    }
    
    Returns JSON:
    {
        "response": "bot response",
        "session_id": "session-id"
    }
    """
    try:
        data = await request.json()
        session_id = data.get("session_id")
        message = data.get("message", "").strip()

        # Validate message
        if not message:
            logger.warning("Empty message received")
            raise HTTPException(status_code=400, detail="message required")

        # Generate session_id if first request
        if not session_id:
            session_id = secrets.token_urlsafe(32)
            session_hash = hash_session_id(session_id)
            logger.info(f"Session {session_hash}: New session created")
        else:
            session_hash = hash_session_id(session_id)
            logger.info(f"Session {session_hash}: Continuing session")

        # Chat with Gemini
        try:
            reply = await chat_with_gemini(session_id, message)
        except Exception as gemini_error:
            session_hash = hash_session_id(session_id)
            logger.exception(f"Session {session_hash}: Chat failed")
            return {
                "response": "Sorry, I encountered an error. Please try again!",
                "session_id": session_id
            }

        # Save messages to SQLite
        session_manager.save_message(session_id, "user", message)
        session_manager.save_message(session_id, "assistant", reply)

        session_hash = hash_session_id(session_id)
        logger.info(f"Session {session_hash}: Request completed")
        return {"response": reply, "session_id": session_id}
    
    except HTTPException:
        raise
    except Exception as e:
        # Privacy-safe error logging
        logger.exception(f"Unexpected error: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "ok"}


# ----------------------
# Startup Event
# ----------------------
@app.on_event("startup")
async def startup_event():
    """Log startup information."""
    logger.info("=" * 50)
    logger.info("nifty-bot-v4 starting (privacy-first mode)")
    logger.info(f"Project: {PROJECT_ID}")
    logger.info(f"Location: {LOCATION}")
    logger.info(f"Model: gemini-1.5-flash-002")
    logger.info(f"Database: {DB_PATH} (ephemeral)")
    logger.info("Privacy features:")
    logger.info("  - Hashed session IDs in logs")
    logger.info("  - No message content logged")
    logger.info("  - Ephemeral database (/tmp)")
    logger.info("  - Data not used for training (Vertex AI)")
    logger.info("=" * 50)


# ----------------------
# Shutdown Event
# ----------------------
@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown information."""
    logger.info("nifty-bot-v4 shutting down")