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


# --- Decision Service Schemas ---


class MemorySummary(BaseModel):
    """A memory relevant to decision-making."""
    event_id: str
    summary: Optional[str] = None
    importance: float = 0.1
    created_at: datetime
    event_type: Optional[str] = None


class RelationshipSummary(BaseModel):
    """Relationship data for decision context."""
    npc_id: str
    name: str
    trust: int = 0
    respect: int = 0
    affection: int = 0
    jealousy: int = 0
    fear: int = 0
    grievances: List[str] = Field(default_factory=list)


class GoalSummary(BaseModel):
    """Active goal for decision context."""
    goal_type: str
    description: Optional[str] = None
    priority: float = 0.5
    horizon: str = "short"  # short | long


class Stimulus(BaseModel):
    """The event/trigger that NPC is reacting to."""
    event_id: str
    event_type: str  # AMBIENT_SEEN, POST_SEEN, ROUTINE, etc.
    payload: Dict[str, Any] = Field(default_factory=dict)
    actors: List[str] = Field(default_factory=list)
    targets: List[str] = Field(default_factory=list)
    # For POST_SEEN
    original_text: Optional[str] = None
    original_author: Optional[str] = None
    # For AMBIENT_SEEN
    topic: Optional[str] = None
    summary_fi: Optional[str] = None


class DecisionContext(BaseModel):
    """Full context for NPC decision-making."""
    # NPC identity
    npc_id: str
    name: str
    role: str
    archetypes: List[str] = Field(default_factory=list)
    bio: Optional[str] = None
    traits: Dict[str, float] = Field(default_factory=dict)
    values: Dict[str, float] = Field(default_factory=dict)
    voice: Dict[str, Any] = Field(default_factory=dict)

    # Memories
    recent_memories: List[MemorySummary] = Field(default_factory=list)
    important_memories: List[MemorySummary] = Field(default_factory=list)
    related_memories: List[MemorySummary] = Field(default_factory=list)

    # Relationships with involved actors
    relationships: Dict[str, RelationshipSummary] = Field(default_factory=dict)

    # Active goals
    active_goals: List[GoalSummary] = Field(default_factory=list)

    # The stimulus to react to
    stimulus: Stimulus


class DecisionResult(BaseModel):
    """Output from Decision LLM."""
    action: str  # IGNORE, POST_FEED, POST_CHAT, REPLY
    intent: str = "neutral"  # spread_info, agree, disagree, joke, worry, practical, emotional
    emotion: str = "neutral"  # curious, happy, annoyed, worried, neutral, amused
    draft: str = ""  # English draft of what to say
    reasoning: str = ""  # Why this decision
    confidence: float = 0.5  # 0-1
    target_channel: Optional[str] = None  # FEED, CHAT
    target_actor: Optional[str] = None  # For REPLY


class DecisionJob(BaseModel):
    """Job sent from Engine to Decision Service."""
    job_id: str
    npc_id: str
    stimulus: Stimulus
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RenderJobV2(BaseModel):
    """Job sent from Decision Service to Worker."""
    job_id: str
    decision_job_id: str
    author_id: str
    channel: str  # FEED, CHAT, NEWS
    source_event_id: str
    decision: DecisionResult
    # For replies
    parent_post_id: Optional[int] = None
    reply_type: Optional[str] = None
