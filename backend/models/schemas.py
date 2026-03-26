from typing import List, Optional, Dict, Any

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    answer: str
    cypher_query: Optional[str] = None
    highlight_nodes: List[str] = []
    new_nodes: List[Dict[str, Any]] = []
    new_links: List[Dict[str, Any]] = []

