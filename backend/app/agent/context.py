"""Incident scope for tools (FR-11). `incident_id` is never a tool parameter."""

from contextvars import ContextVar

current_incident: ContextVar[str] = ContextVar("current_incident")
