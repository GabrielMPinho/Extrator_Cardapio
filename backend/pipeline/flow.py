"""Pipeline de ETL de cardápios orquestrado com Prefect.

ingestão/pré-processamento -> extração multimodal -> estruturação -> validação (GX) -> armazenamento
"""
import io
import json
import time
import uuid
from datetime import datetime, timezone

import pandas as pd
from PIL import Image, ImageOps
from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE

from . import config, extractor, storage, validation
from .schemas import MenuExtraction

# A interface pode registrar uma função aqui para acompanhar as etapas do flow.
progress_hook = None


def _notify(step: str) -> None:
    if progress_hook is not None:
        try:
            progress_hook(step)
        except Exception:
            pass


@task(name="pre-processar-imagem", cache_policy=NO_CACHE)
def preprocess_image(image_bytes: bytes, filename: str) -> tuple[bytes, str]:
    """Corrige rotação (EXIF de celular), converte para RGB e reduz a resolução."""
    logger = get_run_logger()
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img).convert("RGB")
    original = img.size
    img.thumbnail((config.MAX_IMAGE_SIDE, config.MAX_IMAGE_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    logger.info(f"{filename}: {original} -> {img.size}, {len(buf.getvalue()) / 1024:.0f} KB")
    return buf.getvalue(), "image/jpeg"


@task(name="extrair-com-modelo-multimodal", retries=2, retry_delay_seconds=5, cache_policy=NO_CACHE)
def extract(image_bytes: bytes, media_type: str) -> tuple[MenuExtraction, dict, float]:
    logger = get_run_logger()
    t0 = time.perf_counter()
    menu, usage = extractor.extract_menu(image_bytes, media_type)
    elapsed = time.perf_counter() - t0
    n_items = sum(len(c.items) for c in menu.categories)
    logger.info(
        f"Extração: {len(menu.categories)} categorias, {n_items} itens em {elapsed:.1f}s | "
        f"tokens in={usage['input_tokens']} out={usage['output_tokens']} | US$ {usage['cost_usd']:.4f}"
    )
    return menu, usage, elapsed


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    text = " ".join(text.split()).strip(" .-–:")
    return text or None


@task(name="estruturar-e-normalizar", cache_policy=NO_CACHE)
def structure(menu: MenuExtraction, run_id: str, source_file: str) -> pd.DataFrame:
    """Achata a árvore categoria -> item -> variação em linhas tabulares e normaliza textos."""
    processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = {
        "run_id": run_id,
        "processed_at": processed_at,
        "source_file": source_file,
        "restaurant_name": _clean(menu.restaurant_name),
        "currency": (menu.currency or "").upper().strip() or None,
    }
    rows = []
    for cat in menu.categories:
        for item in cat.items:
            common = {
                **base,
                "category": _clean(cat.name),
                "item_name": _clean(item.name),
                "description": _clean(item.description),
                "attributes": "; ".join(a.strip().lower() for a in item.attributes if a.strip()) or None,
            }
            variants = [v for v in item.variants if v.label or v.price is not None]
            if variants:
                for v in variants:
                    rows.append({**common, "variant_label": _clean(v.label), "price": v.price})
            else:
                rows.append({**common, "variant_label": None, "price": item.price})

    df = pd.DataFrame(rows, columns=[
        "run_id", "processed_at", "source_file", "restaurant_name", "currency",
        "category", "item_name", "description", "variant_label", "price", "attributes",
    ])
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["empty_categories"] = sum(1 for c in menu.categories if not c.items)
    get_run_logger().info(f"Estruturação: {len(df)} linhas")
    return df


@task(name="validar-com-great-expectations", cache_policy=NO_CACHE)
def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    logger = get_run_logger()
    df = validation.add_row_flags(df)
    report = validation.validate(df)
    for c in report["checks"]:
        logger.info(f"[{'OK' if c['success'] else 'FALHOU'}] {c['check']}")
    logger.info(f"Guardrails: {report['passed']}/{report['total']} -> {report['status']}")
    df["menu_status"] = report["status"]
    return df, report


@task(name="persistir-csv", cache_policy=NO_CACHE)
def persist(df: pd.DataFrame, run: dict) -> None:
    storage.append_items(df)
    storage.append_run(run)
    get_run_logger().info(f"Append de {len(df)} linhas em {config.ITEMS_CSV.name}")


@flow(name="pipeline-cardapios", log_prints=True)
def menu_pipeline(image_bytes: bytes, filename: str) -> dict:
    t0 = time.perf_counter()
    run_id = uuid.uuid4().hex[:12]
    run = {"run_id": run_id, "source_file": filename,
           "processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    try:
        _notify("preprocess")
        img, media_type = preprocess_image(image_bytes, filename)
        _notify("extract")
        menu, usage, extraction_s = extract(img, media_type)
        _notify("structure")
        df = structure(menu, run_id, filename)
        _notify("validate")
        df, report = validate(df)
    except Exception as exc:  # registra a falha também, para entrar nas métricas
        run.update(status="erro", error=str(exc)[:500], latency_s=round(time.perf_counter() - t0, 2))
        storage.append_run(run)
        raise

    run.update(
        restaurant_name=menu.restaurant_name, is_menu=menu.is_menu, legibility=menu.legibility,
        n_categories=len(menu.categories), n_items=len(df), status=report["status"],
        gx_score=report["score"], gx_passed=report["passed"], gx_total=report["total"],
        extraction_s=round(extraction_s, 2), notes=menu.notes, **usage,
    )
    # latência = do recebimento da imagem até a persistência
    run["latency_s"] = round(time.perf_counter() - t0, 2)
    _notify("persist")
    persist(df, run)
    run["latency_s"] = round(time.perf_counter() - t0, 2)

    return {
        "run": run,
        "validation": report,
        "menu": menu.model_dump(),
        "items": json.loads(df.drop(columns=["variant_key", "empty_categories"], errors="ignore").to_json(orient="records", force_ascii=False)),
    }
