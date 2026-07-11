from datetime import datetime, timezone
from ..schemas.payloads import Esp32Payload, ConsolidatedResponse, Thresholds
from ..services.ml_service import ml_service


class DataService:
    def __init__(self):
        self.last_internal_reading = {}
        self.history = []

        self.door_opened_at: datetime | None = None
        self.door_open_count: int = 0
        self.last_door_state: str = "closed"

        self.thresholds = Thresholds()

    def process_esp32_reading(self, payload: Esp32Payload) -> ConsolidatedResponse:
        self.last_internal_reading = payload.model_dump()

        # Detecta transição de estado da porta a partir do próprio payload do ESP32
        if self.last_door_state == "closed" and payload.door_state == "open":
            self.door_opened_at = datetime.now(timezone.utc)
            self.door_open_count += 1
        elif payload.door_state == "closed":
            self.door_opened_at = None

        self.last_door_state = payload.door_state

        porta_aberta_flag = 1 if payload.door_state == "open" else 0

        porta_aberta_min = 0.0
        if payload.door_state == "open" and self.door_opened_at:
            delta = datetime.now(timezone.utc) - self.door_opened_at
            porta_aberta_min = delta.total_seconds() / 60.0

        current_context = {
            "temperature_internal": payload.temperature_internal,
            "door_state": payload.door_state,
            "door_open_duration_minutes": round(porta_aberta_min, 2),
            "door_open_count_total": self.door_open_count,
            "timestamp": payload.timestamp.isoformat(),
        }

        anomaly = ml_service.evaluate_reading(
            internal_temp=current_context["temperature_internal"],
            porta_aberta=porta_aberta_flag
        )

        record = ConsolidatedResponse(
            current=current_context,
            anomaly=anomaly,
            thresholds=self.thresholds
        )

        self.history.append(record.model_dump())
        if len(self.history) > 100:
            self.history.pop(0)

        return record

    def get_latest_state(self) -> dict | None:
        if not self.history:
            return None
        return self.history[-1]


data_service = DataService()