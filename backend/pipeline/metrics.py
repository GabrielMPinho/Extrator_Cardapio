"""Métricas consolidadas exigidas no relatório de qualidade."""
import pandas as pd

from . import config, storage


def _pct(num, den) -> float | None:
    return round(100 * num / den, 2) if den else None


def compute_metrics(items: pd.DataFrame | None = None, runs: pd.DataFrame | None = None) -> dict:
    items = storage.read_items() if items is None else items
    runs = storage.read_runs() if runs is None else runs

    required = ["category", "item_name", "price"]
    n_rows = len(items)
    n_cells = n_rows * len(required)
    missing_cells = int(items[required].isna().sum().sum()) if n_rows else 0
    prices = items["price"].dropna() if n_rows else pd.Series(dtype=float)
    reasonable = prices.between(config.PRICE_MIN, config.PRICE_MAX)

    ok_runs = runs[runs["status"] != "erro"] if len(runs) else runs
    return {
        "menus_processados": int(len(runs)),
        "menus_com_erro": int((runs["status"] == "erro").sum()) if len(runs) else 0,
        "menus_aprovados": int((runs["status"] == "aprovado").sum()) if len(runs) else 0,
        "menus_revisao_humana": int((runs["status"] == "revisao_humana").sum()) if len(runs) else 0,
        "itens_extraidos": n_rows,
        # 1) missing data
        "pct_missing_data": _pct(missing_cells, n_cells),
        "pct_missing_por_campo": {c: _pct(int(items[c].isna().sum()), n_rows) for c in required} if n_rows else {},
        "pct_linhas_com_campo_faltante": _pct(int(items[required].isna().any(axis=1).sum()), n_rows),
        # 2) preços razoáveis
        "pct_precos_razoaveis": _pct(int(reasonable.sum()), len(prices)),
        "precos_fora_da_faixa": int((~reasonable).sum()),
        "faixa_preco_razoavel": [config.PRICE_MIN, config.PRICE_MAX],
        # 3) latência
        "latencia_media_s": round(float(ok_runs["latency_s"].mean()), 2) if len(ok_runs) else None,
        "latencia_p50_s": round(float(ok_runs["latency_s"].median()), 2) if len(ok_runs) else None,
        "latencia_max_s": round(float(ok_runs["latency_s"].max()), 2) if len(ok_runs) else None,
        # 4) custo
        "tokens_input_medio": round(float(ok_runs["input_tokens"].mean()), 0) if len(ok_runs) else None,
        "tokens_output_medio": round(float(ok_runs["output_tokens"].mean()), 0) if len(ok_runs) else None,
        "custo_medio_usd": round(float(ok_runs["cost_usd"].mean()), 4) if len(ok_runs) else None,
        "custo_total_usd": round(float(ok_runs["cost_usd"].sum()), 4) if len(ok_runs) else None,
        "score_gx_medio": round(float(ok_runs["gx_score"].mean()), 3) if len(ok_runs) else None,
    }
