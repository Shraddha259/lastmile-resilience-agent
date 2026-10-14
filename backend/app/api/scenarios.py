"""Scenario and incident commands: API-2 start, API-3 stop (kill switch), API-4 reset."""

from fastapi import APIRouter, Depends

from app.models import ScenarioRequest, StopRequest
from app.services import scenario
from app.util.auth import require_passcode

router = APIRouter(prefix="/api", tags=["scenarios"], dependencies=[Depends(require_passcode)])


@router.post("/scenarios", status_code=201)
async def start_scenario(body: ScenarioRequest) -> dict:
    """API-2: create an incident with ranked cases and start check-ins."""
    return {"incident_id": await scenario.start_scenario(body)}


@router.post("/incidents/{incident_id}/stop")
async def stop(incident_id: str, body: StopRequest | None = None) -> dict:
    """API-3: kill switch. Stops all calls and makes queued jobs no-ops."""
    return await scenario.stop_incident(incident_id, (body or StopRequest()).reason)


@router.post("/incidents/{incident_id}/reset")
async def reset(incident_id: str) -> dict:
    """API-4: stop if active, delete incident data, restore shelters and volunteers."""
    await scenario.reset_incident(incident_id)
    return {"status": "RESET"}
