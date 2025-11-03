import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import aiosqlite
from dataclasses import asdict

from config import config
from models.schemas import ChatMessage

logger = logging.getLogger(__name__)

class ConversationService:
    """Service for managing conversation history"""
    
    def __init__(self):
        self.db_path = config.DB_PATH
        self.storage_type = config.CONVERSATION_STORAGE
        self.memory_store = []  # In-memory fallback
    
    async def initialize(self):
        """Initialize storage backend"""
        if self.storage_type == "sqlite":
            await self._init_sqlite()
        else:
            logger.info("Using in-memory conversation storage")
    
    async def _init_sqlite(self):
        """Initialize SQLite database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        audio_file TEXT,
                        metadata TEXT
                    )
                """)
                await db.commit()
                logger.info(f"✅ SQLite database initialized: {self.db_path}")
                
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}")
            logger.info("Falling back to in-memory storage")
            self.storage_type = "memory"
    
    async def save_message(self, message: ChatMessage) -> int:
        """Save a message and return its ID"""
        if self.storage_type == "sqlite":
            return await self._save_to_sqlite(message)
        else:
            return self._save_to_memory(message)
    
    async def _save_to_sqlite(self, message: ChatMessage) -> int:
        """Save message to SQLite database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO conversations (role, content, timestamp, audio_file, metadata)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        message.role,
                        message.content,
                        message.timestamp.isoformat(),
                        message.audio_file,
                        json.dumps({}) if not hasattr(message, 'metadata') else json.dumps(message.metadata)
                    )
                )
                await db.commit()
                return cursor.lastrowid
                
        except Exception as e:
            logger.error(f"Failed to save message to SQLite: {e}")
            # Fallback to memory
            return self._save_to_memory(message)
    
    def _save_to_memory(self, message: ChatMessage) -> int:
        """Save message to memory"""
        message.id = len(self.memory_store) + 1
        self.memory_store.append(message)
        return message.id
    
    async def get_recent_messages(self, limit: int = 50) -> List[dict]:
        """Get recent messages"""
        if self.storage_type == "sqlite":
            return await self._get_from_sqlite(limit)
        else:
            return self._get_from_memory(limit)
    
    async def _get_from_sqlite(self, limit: int) -> List[dict]:
        """Get messages from SQLite database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    SELECT id, role, content, timestamp, audio_file, metadata
                    FROM conversations
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,)
                )
                rows = await cursor.fetchall()
                
                messages = []
                for row in reversed(rows):  # Reverse to get chronological order
                    messages.append({
                        "id": row[0],
                        "role": row[1],
                        "content": row[2],
                        "timestamp": row[3],
                        "audio_file": row[4],
                        "metadata": json.loads(row[5]) if row[5] else {}
                    })
                
                return messages
                
        except Exception as e:
            logger.error(f"Failed to get messages from SQLite: {e}")
            return self._get_from_memory(limit)
    
    def _get_from_memory(self, limit: int) -> List[dict]:
        """Get messages from memory"""
        recent_messages = self.memory_store[-limit:] if limit > 0 else self.memory_store
        return [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "audio_file": msg.audio_file,
                "metadata": getattr(msg, 'metadata', {})
            }
            for msg in recent_messages
        ]
    
    async def get_conversation_context(self, max_messages: int = 10) -> List[dict]:
        """Get conversation context for AI model"""
        messages = await self.get_recent_messages(max_messages)
        
        # Format for AI context (simple role/content pairs)
        context = []
        for msg in messages:
            context.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        return context
    
    async def clear_conversation(self) -> bool:
        """Clear all conversation history"""
        try:
            if self.storage_type == "sqlite":
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("DELETE FROM conversations")
                    await db.commit()
            
            self.memory_store.clear()
            logger.info("Conversation history cleared")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear conversation: {e}")
            return False
    
    async def delete_old_messages(self, days: int = 30) -> int:
        """Delete messages older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        try:
            if self.storage_type == "sqlite":
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        "DELETE FROM conversations WHERE timestamp < ?",
                        (cutoff_date.isoformat(),)
                    )
                    await db.commit()
                    deleted_count = cursor.rowcount
            else:
                initial_count = len(self.memory_store)
                self.memory_store = [
                    msg for msg in self.memory_store
                    if msg.timestamp > cutoff_date
                ]
                deleted_count = initial_count - len(self.memory_store)
            
            logger.info(f"Deleted {deleted_count} old messages")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete old messages: {e}")
            return 0
    
    async def get_message_by_id(self, message_id: int) -> Optional[dict]:
        """Get a specific message by ID"""
        try:
            if self.storage_type == "sqlite":
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        "SELECT id, role, content, timestamp, audio_file, metadata FROM conversations WHERE id = ?",
                        (message_id,)
                    )
                    row = await cursor.fetchone()
                    
                    if row:
                        return {
                            "id": row[0],
                            "role": row[1],
                            "content": row[2],
                            "timestamp": row[3],
                            "audio_file": row[4],
                            "metadata": json.loads(row[5]) if row[5] else {}
                        }
            else:
                for msg in self.memory_store:
                    if msg.id == message_id:
                        return {
                            "id": msg.id,
                            "role": msg.role,
                            "content": msg.content,
                            "timestamp": msg.timestamp.isoformat(),
                            "audio_file": msg.audio_file,
                            "metadata": getattr(msg, 'metadata', {})
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get message by ID: {e}")
            return None