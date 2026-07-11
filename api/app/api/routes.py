from fastapi import APIRouter, HTTPException
from ..schemas.payloads import (
    Esp32Payload,
    ConsolidatedResponse,
)
from ..services.data_service import data_service

router = APIRouter()

@router.post("/esp32/reading", response_model=ConsolidatedResponse, tags=["IoT"])
async def receive_reading(payload: Esp32Payload):
    """Recebe os dados reais do hardware ESP32 e processa anomalias."""
    return data_service.process_esp32_reading(payload)

@router.get("/dashboard/current", response_model=Optional[ConsolidatedResponse], tags=["Dashboard"])
async def get_current_data():
    state = data_service.get_latest_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Nenhum dado recebido do ESP32 ainda.")
    return state