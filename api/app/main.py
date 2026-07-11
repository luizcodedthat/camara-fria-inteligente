from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .api.routes import router

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

# Configuração de CORS para permitir requisições do frontend da Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Ajustar em produção para a URL da Dashboard
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")

@app.get("/")
def root():
    return {"message": "API do Sistema de Monitoramento da Câmara Fria online."}