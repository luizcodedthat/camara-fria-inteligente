import joblib
import pandas as pd
from pathlib import Path
from datetime import datetime
from collections import deque
from ..schemas.payloads import AnomalyResult
import logging

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "temp_interna",
    "media_movel_2min",
    "desvio_padrao_5min",
    "taxa_variacao_min",
    "porta_aberta",
]

# Configuração do filtro de duração
N_PERSISTENCIA = 6  # N leituras consecutivas anômalas/suspeitas para disparar alerta
INTERVALO_LEITURA_SEG = 5  # leitura a cada 5 segundos


class MLService:
    def __init__(self):
        model_path = Path(__file__).resolve().parent.parent / "model" / "isolation_forest_model.joblib"

        try:
            self.model = joblib.load(model_path)
            logger.info(f"Modelo carregado de: {model_path}")
        except FileNotFoundError:
            logger.warning(f"Modelo não encontrado em {model_path}. Usando fallback.")
            self.model = None

        # Histórico de temperaturas internas para calcular janelas deslizantes
        # 2 min = 24 leituras (5s cada), 5 min = 60 leituras
        self._temp_history: deque[float] = deque(maxlen=60)

        # Histórico de estados da porta (0/1)
        self._porta_history: deque[int] = deque(maxlen=60)

        # Histórico de labels do modelo para filtro de duração
        self._label_history: deque[str] = deque(maxlen=N_PERSISTENCIA)

    def _build_features(
        self,
        internal_temp: float,
        porta_aberta: int,  # 0 = fechada, 1 = aberta
    ) -> list[float]:
        self._temp_history.append(internal_temp)
        self._porta_history.append(porta_aberta)

        # Média móvel de 2 minutos (24 leituras de 5s)
        window_2min = 24
        if len(self._temp_history) >= window_2min:
            media_movel_2min = sum(list(self._temp_history)[-window_2min:]) / window_2min
        else:
            media_movel_2min = internal_temp  # fallback

        # Desvio padrão de 5 minutos (60 leituras de 5s)
        window_5min = 60
        if len(self._temp_history) >= window_5min:
            slice_5min = list(self._temp_history)[-window_5min:]
            desvio_padrao_5min = pd.Series(slice_5min).std()
        else:
            desvio_padrao_5min = 0.0  # fallback

        # Taxa de variação por minuto (diferença entre leituras espaçadas de 1 min = 12 leituras)
        window_var = 12
        if len(self._temp_history) >= window_var:
            temp_atual = self._temp_history[-1]
            temp_passada = self._temp_history[-window_var]
            taxa_variacao_min = (temp_atual - temp_passada) / (window_var * INTERVALO_LEITURA_SEG / 60.0)
        else:
            taxa_variacao_min = 0.0  # fallback

        # Ordem obrigatória — deve espelhar FEATURE_NAMES
        return [
            internal_temp,          # temp_interna
            media_movel_2min,      # media_movel_2min
            desvio_padrao_5min,    # desvio_padrao_5min
            taxa_variacao_min,     # taxa_variacao_min
            porta_aberta,          # porta_aberta
        ]

    def evaluate_reading(
        self,
        internal_temp: float,
        porta_aberta: int,  # 0 = fechada, 1 = aberta
    ) -> AnomalyResult:

        if self.model is None:
            return self._mock_evaluation(internal_temp, porta_aberta)

        features = self._build_features(internal_temp, porta_aberta)

        df_input = pd.DataFrame([features], columns=FEATURE_NAMES)

        prediction = self.model.predict(df_input)[0]
        anomaly_score = float(self.model.decision_function(df_input)[0])

        # Classificação básica
        if prediction == -1:
            label = "anômala" if anomaly_score < -0.1 else "suspeita"
        else:
            label = "normal"

        # Atualiza histórico de labels para filtro de duração
        self._label_history.append(label)

        # Filtro de duração: só dispara alerta se N leituras consecutivas forem anômalas/suspeitas
        if len(self._label_history) == N_PERSISTENCIA:
            if all(l in ("anômala", "suspeita") for l in self._label_history):
                logger.info(f"Alerta disparado após {N_PERSISTENCIA} leituras consecutivas anômalas/suspeitas")

        return AnomalyResult(label=label, score=anomaly_score)

    def _mock_evaluation(self, internal_temp: float, porta_aberta: int) -> AnomalyResult:
        if porta_aberta == 1 and internal_temp > 8.0:
            return AnomalyResult(label="anômala", score=-0.85)
        return AnomalyResult(label="normal", score=0.15)


ml_service = MLService()