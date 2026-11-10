"""Configurações centrais do projeto (lidas do .env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / "backend" / ".env")

DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"
UPLOADS_DIR = OUTPUT_DIR / "uploads"
REPORTS_DIR = ROOT_DIR / "reports"

ITEMS_CSV = OUTPUT_DIR / "menu_items.csv"  # planilha consolidada (1 linha por item/variante)
RUNS_CSV = OUTPUT_DIR / "pipeline_runs.csv"  # 1 linha por cardápio processado (latência, custo, status)

for d in (OUTPUT_DIR, UPLOADS_DIR, REPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- Modelo multimodal (Abordagem 2) — OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "low")  # vazio para modelos sem raciocínio (ex.: gpt-4.1)
MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "32000"))

# Preço em US$ por 1M de tokens do modelo escolhido — confira em https://openai.com/api/pricing
PRICE_INPUT_PER_1M = float(os.getenv("PRICE_INPUT_PER_1M", "0"))
PRICE_OUTPUT_PER_1M = float(os.getenv("PRICE_OUTPUT_PER_1M", "0"))

# --- Pré-processamento da imagem ---
MAX_IMAGE_SIDE = int(os.getenv("MAX_IMAGE_SIDE", "2000"))

# --- Guardrails ---
PRICE_MIN = float(os.getenv("PRICE_MIN", "1.0"))  # preço razoável mínimo
PRICE_MAX = float(os.getenv("PRICE_MAX", "1500.0"))  # preço razoável máximo
# Fração mínima de expectativas aprovadas para o cardápio não ir para revisão humana
REVIEW_THRESHOLD = float(os.getenv("REVIEW_THRESHOLD", "0.85"))
