"""Persistência em CSV consolidado, por append."""
import threading
from pathlib import Path

import pandas as pd

from . import config

ITEM_COLUMNS = [
    "run_id", "processed_at", "source_file", "restaurant_name", "currency",
    "category", "item_name", "description", "variant_label", "price", "attributes",
    "flag_missing_required", "flag_price_unreasonable", "flag_price_outlier", "flag_duplicate",
    "flag_item_equals_category", "flag_variant_order",
    "menu_status",
]

RUN_COLUMNS = [
    "run_id", "processed_at", "source_file", "restaurant_name", "is_menu", "legibility",
    "n_categories", "n_items", "status", "gx_score", "gx_passed", "gx_total",
    "latency_s", "extraction_s", "model", "input_tokens", "output_tokens", "cost_usd",
    "notes", "error",
]

_lock = threading.Lock()


def _append(df: pd.DataFrame, path: Path, columns: list[str]) -> None:
    df = df.reindex(columns=columns)
    with _lock:
        if path.exists():
            header = path.read_text(encoding="utf-8").split("\n", 1)[0].strip().split(",")
            if header != columns:  # esquema mudou: reescreve o arquivo com as colunas novas
                pd.read_csv(path).reindex(columns=columns).to_csv(path, index=False, encoding="utf-8")
        df.to_csv(path, mode="a", header=not path.exists(), index=False, encoding="utf-8")


def append_items(df: pd.DataFrame) -> None:
    _append(df, config.ITEMS_CSV, ITEM_COLUMNS)


def append_run(run: dict) -> None:
    _append(pd.DataFrame([run]), config.RUNS_CSV, RUN_COLUMNS)


def read_items() -> pd.DataFrame:
    return pd.read_csv(config.ITEMS_CSV) if config.ITEMS_CSV.exists() else pd.DataFrame(columns=ITEM_COLUMNS)


def read_runs() -> pd.DataFrame:
    return pd.read_csv(config.RUNS_CSV) if config.RUNS_CSV.exists() else pd.DataFrame(columns=RUN_COLUMNS)
