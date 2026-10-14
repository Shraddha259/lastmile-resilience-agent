"""Pydantic models and enums for every Firestore document (PRD §9).

These models are the single schema source: `make types` exports them to
`frontend/src/types.gen.ts`, so frontend and backend never drift.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- enums
class Language(StrEnum):
    zh = "zh"
    ms = "ms"
    ta = "ta"
    en = "en"
    yue = "yue"


class Mobility(StrEnum):
    independent = "independent"
    walker = "walker"
    wheelchair = "wheelchair"
    bedridden = "bedridden"


class MedicalFlag(StrEnum):
    hypertension = "hypertension"
    diabetes = "diabetes"
    dialysis = "dialysis"
    oxygen = "oxygen"
    dementia = "dementia"
    heart_condition = "heart_condition"
    recent_surgery = "recent_surgery"
    hearing_impaired = "hearing_impaired"


class Need(StrEnum):
    wheelchair = "wheelchair"
    walking_aid = "walking_aid"
    medication = "medication"
    oxygen = "oxygen"
    dialysis = "dialysis"
    pet = "pet"
    companion = "companion"
    slow_clear_speech = "slow_clear_speech"
    interpreter = "interpreter"


class CaseStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RINGING = "RINGING"
    CONTACTING = "CONTACTING"
    SAFE_IN_PLACE = "SAFE_IN_PLACE"
    NEEDS_EVACUATION = "NEEDS_EVACUATION"
    NEEDS_HELP = "NEEDS_HELP"
    MEDICAL = "MEDICAL"
    NO_ANSWER = "NO_ANSWER"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    NEXT_OF_KIN_CONTACTED = "NEXT_OF_KIN_CONTACTED"
    SHELTER_RESERVED = "SHELTER_RESERVED"
    VOLUNTEER_PENDING = "VOLUNTEER_PENDING"
    VOLUNTEER_EN_ROUTE = "VOLUNTEER_EN_ROUTE"
    AT_SHELTER = "AT_SHELTER"
    ESCALATED = "ESCALATED"
    CONFIRMED_SAFE = "CONFIRMED_SAFE"


TERMINAL_STATUSES = frozenset({CaseStatus.ESCALATED, CaseStatus.CONFIRMED_SAFE})

# Statuses after which the dispatcher must act (PRD §12.5).
ACTION_REQUIRED = frozenset(
    {
        CaseStatus.SAFE_IN_PLACE,
        CaseStatus.NEEDS_EVACUATION,
        CaseStatus.NEEDS_HELP,
        CaseStatus.MEDICAL,
        CaseStatus.NO_ANSWER,
        CaseStatus.NEXT_OF_KIN_CONTACTED,
        CaseStatus.SHELTER_RESERVED,
    }
)


class Actor(StrEnum):
    agent = "agent"
    policy = "policy"
    volunteer = "volunteer"
    coordinator = "coordinator"
    system = "system"


class Priority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Channel(StrEnum):
    live = "live"
    simulated = "simulated"
    phone = "phone"


class IncidentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"


class CheckinState(StrEnum):
    RINGING = "RINGING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    NO_ANSWER = "NO_ANSWER"
    FAILED = "FAILED"


class EndReason(StrEnum):
    agent_end_call = "agent_end_call"
    resident_hangup = "resident_hangup"
    max_duration = "max_duration"
    ring_timeout = "ring_timeout"
    error = "error"
    kill_switch = "kill_switch"


class TaskType(StrEnum):
    ESCORT_TO_SHELTER = "ESCORT_TO_SHELTER"
    WELFARE_CHECK = "WELFARE_CHECK"
    ASSIST_IN_PLACE = "ASSIST_IN_PLACE"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class Urgency(StrEnum):
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TaskStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACCEPTED = "ACCEPTED"
    PICKED_UP = "PICKED_UP"
    ARRIVED = "ARRIVED"
    DONE = "DONE"
    CANNOT_LOCATE = "CANNOT_LOCATE"
    CANCELLED = "CANCELLED"


OPEN_TASK_STATUSES = frozenset(
    {
        TaskStatus.PENDING_APPROVAL,
        TaskStatus.APPROVED,
        TaskStatus.ACCEPTED,
        TaskStatus.PICKED_UP,
        TaskStatus.ARRIVED,
    }
)


class LocationNow(StrEnum):
    home = "home"
    upper_floor = "upper_floor"
    relative = "relative"
    shelter = "shelter"
    unknown = "unknown"


class EventType(StrEnum):
    SCENARIO_STARTED = "SCENARIO_STARTED"
    CHECKIN_COMPLETED = "CHECKIN_COMPLETED"
    TIMER_FIRED = "TIMER_FIRED"
    VOLUNTEER_UPDATE = "VOLUNTEER_UPDATE"
    TASK_DECIDED = "TASK_DECIDED"
    COORDINATOR_OVERRIDE = "COORDINATOR_OVERRIDE"
    STATUS_CHANGE = "STATUS_CHANGE"


# ---------------------------------------------------------------- documents
class LatLng(BaseModel):
    lat: float
    lng: float


class Geometry(BaseModel):
    """Polygon or LineString as a list of points (Firestore can't nest arrays, D-007)."""

    type: str
    points: list[LatLng]


class NextOfKin(BaseModel):
    name: str
    relation: str
    phone_masked: str


class PersonaFacts(BaseModel):
    where: str
    with_: str = Field(alias="with")
    mobility_detail: str
    medical: str
    extra: str = ""

    model_config = {"populate_by_name": True}


class Persona(BaseModel):
    scripted_outcome: CaseStatus
    answers_on_attempt: int | None = 1
    facts: PersonaFacts
    speech_style: str
    ambiguous: bool = False
    volunteer_outcome: TaskStatus | None = None


class Resident(BaseModel):
    resident_id: str
    display_name: str
    synthetic: bool = True
    age: int
    gender: str
    languages: list[Language]
    dialect_hint: str | None = None
    preferred_language: Language
    location: LatLng
    address_label: str
    floor: int
    lives_alone: bool
    mobility: Mobility
    medical_flags: list[MedicalFlag] = []
    next_of_kin: NextOfKin
    is_live_demo: bool = False
    persona: Persona | None = None


class Shelter(BaseModel):
    shelter_id: str
    name: str
    location: LatLng
    capacity: int
    occupied: int = 0
    wheelchair_accessible: bool
    medical_support: bool
    open: bool = True


class Volunteer(BaseModel):
    volunteer_id: str
    display_name: str
    languages: list[Language]
    skills: list[str]
    location: LatLng
    available: bool = True
    synthetic: bool = True
    is_live_demo: bool = False


class Counters(BaseModel):
    total: int = 0
    confirmed_safe: int = 0
    escalated: int = 0
    in_progress: int = 0


class Incident(BaseModel):
    incident_id: str
    scenario_id: str
    type: str
    severity: str
    title: str
    polygon: Geometry
    river_line: Geometry
    official_text: dict[str, str]
    official_facts: list[str]
    status: IncidentStatus = IncidentStatus.ACTIVE
    auto_approve_dispatch: bool = False
    sim_time_scale: float = 10
    created_at: datetime | None = None
    ends_at: datetime | None = None
    counters: Counters = Counters()


class Case(BaseModel):
    resident_id: str
    status: CaseStatus = CaseStatus.PENDING
    version: int = 0
    risk_score: int = 0
    priority: Priority = Priority.P3
    risk_reasons: list[str] = []
    attempts: int = 0
    channel: Channel = Channel.simulated
    needs: list[str] = []
    assigned_shelter_id: str | None = None
    assigned_volunteer_id: str | None = None
    open_task_id: str | None = None
    human_review: bool = False
    last_summary_en: str | None = None
    confirmed_by: str | None = None
    # Denormalised for ordering and the console; written once at creation.
    age: int = 0
    rank: int = 0
    updated_at: datetime | None = None


class TranscriptLine(BaseModel):
    role: str
    text: str
    text_en: str | None = None
    t: float = 0.0


class Classification(BaseModel):
    """Post-call classifier output (PRD §14.1)."""

    status: CaseStatus
    confidence: float = Field(ge=0, le=1)
    needs: list[Need] = []
    household_others_at_risk: bool = False
    medical_flag: bool = False
    location_now: LocationNow = LocationNow.unknown
    language_detected: str = "other"
    summary_en: str = Field(default="", max_length=200)
    requires_human_review: bool = False
    review_reason: str | None = None


class Checkin(BaseModel):
    checkin_id: str
    resident_id: str
    attempt: int
    channel: Channel
    language: Language
    state: CheckinState
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_s: float | None = None
    transcript: list[TranscriptLine] = []
    live_status: CaseStatus | None = None
    classification: Classification | None = None
    end_reason: EndReason | None = None


class Task(BaseModel):
    task_id: str
    type: TaskType
    resident_id: str
    volunteer_id: str | None = None
    shelter_id: str | None = None
    urgency: Urgency
    status: TaskStatus
    briefing_en: str
    briefing_volunteer_lang: dict[str, str] = {}
    proposed_by: Actor
    decided_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentEvent(BaseModel):
    ts: datetime | None = None
    actor: Actor
    event_type: str
    resident_id: str | None = None
    tool: str | None = None
    args_summary: str | None = None
    result: str = "ok"
    reason: str = ""
    model: str | None = None
    latency_ms: int | None = None
    fallback_used: bool = False
    status_from: CaseStatus | None = None
    status_to: CaseStatus | None = None


# ---------------------------------------------------------------- API bodies
class ScenarioRequest(BaseModel):
    scenario_id: str = "flood_demo"
    auto_approve_dispatch: bool | None = None
    sim_time_scale: float | None = Field(default=None, gt=0, le=1000)


class StopRequest(BaseModel):
    reason: str = "kill switch"


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}
