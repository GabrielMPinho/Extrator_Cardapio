"""Extração + estruturação com modelo multimodal (OpenAI GPT) — Abordagem 2."""
import base64

from openai import OpenAI

from . import config
from .schemas import MenuExtraction

SYSTEM_PROMPT = """Você é um especialista em transcrever cardápios de restaurantes a partir de fotos.
Sua tarefa é converter a imagem em dados estruturados, fielmente ao que está escrito.

Regras:
- Transcreva SOMENTE o que está visível. Nunca invente itens, descrições ou preços.
- Se um preço estiver ilegível ou ausente, use null — não chute.
- Preços são números (ex.: "R$ 32,90" -> 32.9). Ignore símbolos de moeda e separadores de milhar.
- Respeite a hierarquia do layout: cardápios com várias colunas devem ser lidos coluna a coluna,
  associando cada item à categoria (cabeçalho) sob a qual ele aparece.
- Itens com vários tamanhos/porções (P/M/G, 300ml/500ml, inteira/meia) vão em `variants`,
  cada um com seu preço; nesse caso `price` fica null.
- Adicionais, combos e bebidas também são itens, cada um em sua categoria.
- Mantenha o idioma original dos nomes. Corrija apenas quebras de linha e hifenização do layout.
- Registre em `notes` qualquer problema (corte, reflexo, baixa resolução, trechos ilegíveis).
- Se a imagem não for um cardápio, retorne is_menu=false e categories vazio."""

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.OPENAI_API_KEY or config.OPENAI_API_KEY.startswith("cole-sua"):
            raise RuntimeError("OPENAI_API_KEY não configurada em backend/.env")
        _client = OpenAI(api_key=config.OPENAI_API_KEY, max_retries=3, timeout=180)
    return _client


def extract_menu(image_bytes: bytes, media_type: str) -> tuple[MenuExtraction, dict]:
    """Chama o modelo multimodal e devolve (estrutura validada pelo Pydantic, uso de tokens)."""
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    kwargs = {}
    if config.OPENAI_REASONING_EFFORT:  # só modelos de raciocínio (gpt-5.x) aceitam
        kwargs["reasoning"] = {"effort": config.OPENAI_REASONING_EFFORT}

    response = get_client().responses.parse(
        model=config.OPENAI_MODEL,
        instructions=SYSTEM_PROMPT,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": f"data:{media_type};base64,{image_b64}",
                        "detail": "high",
                    },
                    {"type": "input_text", "text": "Transcreva este cardápio no formato estruturado."},
                ],
            }
        ],
        text_format=MenuExtraction,  # Structured Outputs: JSON garantido no schema
        max_output_tokens=config.MAX_OUTPUT_TOKENS,
        **kwargs,
    )

    if response.status == "incomplete":
        reason = getattr(response.incomplete_details, "reason", "desconhecido")
        raise RuntimeError(f"Resposta incompleta ({reason}). Aumente OPENAI_MAX_OUTPUT_TOKENS.")
    for item in response.output:
        for part in getattr(item, "content", None) or []:
            if part.type == "refusal":
                raise RuntimeError(f"O modelo recusou: {part.refusal}")
    if response.output_parsed is None:
        raise RuntimeError("O modelo não retornou JSON válido.")

    usage = {
        "model": response.model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    usage["cost_usd"] = estimate_cost(usage)
    return response.output_parsed, usage


def estimate_cost(usage: dict) -> float:
    return round(
        usage["input_tokens"] / 1e6 * config.PRICE_INPUT_PER_1M
        + usage["output_tokens"] / 1e6 * config.PRICE_OUTPUT_PER_1M,
        6,
    )
