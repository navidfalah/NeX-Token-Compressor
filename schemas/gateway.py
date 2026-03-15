from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "firma-ki-pipeline"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False
    domain: Optional[str] = ""

class ChatCompletionResponse(BaseModel):
    id: str = "chatcmpl-firmaki"
    object: str = "chat.completion"
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]
    firmaki_telemetry: Optional[Dict[str, Any]] = None
