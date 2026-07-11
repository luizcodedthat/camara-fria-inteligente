import time
import random
import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class Esp32Simulator:
    """
    Simula o ESP32 da câmara fria, enviando temperatura interna (DS18B20) e
    estado da porta (HC-SR04) direto para /esp32/reading
    """

    def __init__(self, base_url: str, device_id: str):
        self.base_url = base_url
        self.device_id = device_id

        # Faixa de operação real da câmara fria (mesma faixa usada no treino do
        # Isolation Forest: -4°C a 1°C)
        self.temp_min = -4.0
        self.temp_max = 1.0
        self.current_internal_temp = -1.5  # ponto médio de operação normal

        self.door_state = "closed"
        self.door_open_steps_remaining = 0

    def _maybe_toggle_door(self):
        """
        A cada leitura, há uma pequena chance de abrir a porta (evento realista
        de operação) e ela permanece aberta por alguns ciclos antes de fechar.
        """
        if self.door_state == "closed":
            if random.random() < 0.05:  # ~5% de chance por leitura
                self.door_state = "open"
                self.door_open_steps_remaining = random.randint(2, 5)
                logging.info("Porta aberta (simulação).")
        else:
            self.door_open_steps_remaining -= 1
            if self.door_open_steps_remaining <= 0:
                self.door_state = "closed"
                logging.info("Porta fechada (simulação).")

    def simulate_reading(self):
        """
        Gera flutuação de temperatura interna. Com a porta aberta, a
        temperatura sobe mais rápido (ganho térmico); com a porta fechada,
        oscila levemente dentro da faixa operacional.
        """
        self._maybe_toggle_door()

        if self.door_state == "open":
            temp_delta = random.uniform(0.15, 0.4)
        else:
            temp_delta = random.uniform(-0.2, 0.15)

        self.current_internal_temp += temp_delta
        self.current_internal_temp = max(self.temp_min - 1.5, min(self.temp_max + 3.0, self.current_internal_temp))

    def send_reading(self):
        """
        Envia o payload conforme o contrato atual da API (sem umidade,
        com door_state vindo do próprio ESP32).
        """
        url = f"{self.base_url}/esp32/reading"
        payload = {
            "device_id": self.device_id,
            "temperature_internal": round(self.current_internal_temp, 2),
            "door_state": self.door_state,
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            anomaly_label = data.get("anomaly", {}).get("label", "desconhecido")
            logging.info(f"Enviado: {payload} | Status da Anomalia: {anomaly_label.upper()}")
        except requests.RequestException as e:
            logging.error(f"Falha ao enviar leitura do ESP32: {e}")

    def run(self, interval_seconds: int = 5):
        logging.info("Iniciando simulador do ESP32...")

        try:
            while True:
                self.simulate_reading()
                self.send_reading()
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logging.info("Simulador encerrado pelo usuário.")


if __name__ == "__main__":
    API_BASE_URL = "http://localhost:8000/api/v1"

    simulator = Esp32Simulator(base_url=API_BASE_URL, device_id="esp32-camara-fria-01")
    simulator.run(interval_seconds=3)