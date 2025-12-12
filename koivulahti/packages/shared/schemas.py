import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class Event(BaseModel):
    id: str
    ts: datetime
    sim_ts: datetime
    place_id: Optional[str]
    type: str
    actors: List[Any] = Field(default_factory=list)
    targets: List[Any] = Field(default_factory=list)
    publicness: float
    severity: float
    payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("actors", "targets", mode="before")
    @classmethod
    def parse_json_lists(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return v

    @field_validator("payload", mode="before")
    @classmethod
    def parse_payload(cls, v: Any) -> Any:
        if v is None:
            return {}
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v


class RenderJob(BaseModel):
    id: int
    created_at: datetime
    status: str = Field(description="queued|processing|done|failed")
    channel: str
    author_id: str
    source_event_id: str
    prompt_context: Dict[str, Any]
    result: Optional[Dict[str, Any]]
    error: Optional[str]


class Post(BaseModel):
    id: int
    created_at: datetime
    channel: str
    author_id: str
    source_event_id: str
    tone: str
    text: str
    tags: List[str] = Field(default_factory=list)
    safety_notes: Optional[str] = None

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return v


class Place(BaseModel):
    id: str
    name: str
    type: str


class NPCProfile(BaseModel):
    id: str
    name: str
    age: int
    role: str
    archetypes: List[str] = Field(default_factory=list)
    bio: Optional[str] = None
    traits: Dict[str, float] = Field(default_factory=dict)
    values: Dict[str, float] = Field(default_factory=dict)
    voice: Dict[str, Any] = Field(default_factory=dict)
    posting: Dict[str, Any] = Field(default_factory=dict)
    routine: Dict[str, Any] = Field(default_factory=dict)
    goals_seed: List[Dict[str, Any]] = Field(default_factory=list)
    triggers: List[Dict[str, Any]] = Field(default_factory=list)
    secrets: List[str] = Field(default_factory=list)

    class Config:
        extra = "allow"


class RelationshipEdge(BaseModel):
    from_npc: str = Field(alias="from")
    to_npc: str = Field(alias="to")
    mode: Optional[str] = None
    trust: int = 0
    respect: int = 0
    affection: int = 0
    jealousy: int = 0
    fear: int = 0
    grievances: List[str] = Field(default_factory=list)
    debts: List[Dict[str, Any]] = Field(default_factory=list)

    class Config:
        validate_by_name = True


class EventTypeItem(BaseModel):
    type: str
    category: str = "misc"
    description: Optional[str] = None
    payload_schema: Dict[str, Any] = Field(default_factory=dict)
    effects: Dict[str, Any] = Field(default_factory=dict)
    render: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"
