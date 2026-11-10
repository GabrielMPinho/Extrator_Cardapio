"""Camada de guardrails com Great Expectations.

Cada expectativa é marcada com o critério do enunciado que ela atende (meta["criterio"]).
"""
import threading

import great_expectations as gx
import pandas as pd

from . import config

CURRENCIES = ["BRL", "USD", "EUR", "GBP", "ARS", "CLP", "MXN", "COP", "PEN", "UYU", "CAD", "AUD", "JPY", "CHF"]

PRECO = "Preços válidos e positivos"
NULOS = "Campos obrigatórios preenchidos"
CONSIST = "Consistência entre categorias e itens"
TEXTO = "Formato do texto"
DUPLIC = "Duplicidades e inconsistências"
CRITERIOS = [PRECO, NULOS, CONSIST, TEXTO, DUPLIC]

E = gx.expectations
EXPECTATIONS = [
    # --- preços
    E.ExpectColumnValuesToBeBetween(column="price", min_value=0, strict_min=True,
                                    description="Preço positivo", meta={"criterio": PRECO}),
    E.ExpectColumnValuesToBeBetween(column="price", min_value=config.PRICE_MIN, max_value=config.PRICE_MAX,
                                    description=f"Preço razoável ({config.PRICE_MIN:g} a {config.PRICE_MAX:g})",
                                    meta={"criterio": PRECO}),
    # --- campos obrigatórios
    E.ExpectTableRowCountToBeBetween(min_value=1, description="Cardápio tem ao menos 1 item",
                                     meta={"criterio": NULOS}),
    E.ExpectColumnValuesToNotBeNull(column="item_name", description="Nome do item preenchido",
                                    meta={"criterio": NULOS}),
    E.ExpectColumnValuesToNotBeNull(column="category", description="Categoria preenchida",
                                    meta={"criterio": NULOS}),
    E.ExpectColumnValuesToNotBeNull(column="price", mostly=0.9,
                                    description="Preço preenchido em pelo menos 90% dos itens",
                                    meta={"criterio": NULOS}),
    # --- consistência entre categorias e itens
    E.ExpectColumnValuesToBeInSet(column="flag_price_outlier", value_set=[False], mostly=0.95,
                                  description="Preço compatível com o resto da categoria (até 10x a mediana)",
                                  meta={"criterio": CONSIST}),
    E.ExpectColumnValuesToBeInSet(column="flag_item_equals_category", value_set=[False],
                                  description="Nenhum item com o mesmo nome da categoria (cabeçalho lido como item)",
                                  meta={"criterio": CONSIST}),
    E.ExpectColumnValuesToBeInSet(column="flag_variant_order", value_set=[False], mostly=0.95,
                                  description="Preços das variações seguem a ordem dos tamanhos (P < M < G)",
                                  meta={"criterio": CONSIST}),
    E.ExpectColumnValuesToBeBetween(column="empty_categories", max_value=0,
                                    description="Nenhuma categoria vazia", meta={"criterio": CONSIST}),
    # --- formato do texto
    E.ExpectColumnValueLengthsToBeBetween(column="item_name", min_value=2, max_value=120,
                                          description="Nome do item com 2 a 120 caracteres",
                                          meta={"criterio": TEXTO}),
    E.ExpectColumnValuesToNotMatchRegex(column="item_name", regex=r"^[\W\d_]+$",
                                        description="Nome do item não é só números ou símbolos",
                                        meta={"criterio": TEXTO}),
    E.ExpectColumnValueLengthsToBeBetween(column="category", min_value=1, max_value=60,
                                          description="Nome da categoria com até 60 caracteres",
                                          meta={"criterio": TEXTO}),
    E.ExpectColumnValuesToBeInSet(column="currency", value_set=CURRENCIES,
                                  description="Moeda em código ISO (BRL, USD…)", meta={"criterio": TEXTO}),
    # --- duplicidades
    E.ExpectCompoundColumnsToBeUnique(column_list=["category", "item_name", "variant_key"],
                                      description="Nenhum item repetido na mesma categoria",
                                      meta={"criterio": DUPLIC}),
]

_lock = threading.Lock()
_batch_definition = None
_suite = None


def _setup():
    global _batch_definition, _suite
    if _batch_definition is not None:
        return
    context = gx.get_context(mode="ephemeral")
    asset = context.data_sources.add_pandas("cardapios").add_dataframe_asset("itens")
    _batch_definition = asset.add_batch_definition_whole_dataframe("lote")
    _suite = context.suites.add(gx.ExpectationSuite(name="guardrails_cardapio"))
    for exp in EXPECTATIONS:
        _suite.add_expectation(exp)


SIZE_RANK = {
    "mini": 0, "broto": 1, "p": 1, "pequena": 1, "pequeno": 1, "meia": 1, "individual": 1,
    "m": 2, "média": 2, "media": 2, "médio": 2, "medio": 2,
    "g": 3, "grande": 3, "inteira": 3,
    "gg": 4, "gigante": 4, "família": 4, "familia": 4, "extra grande": 4,
}


def _size_rank(label) -> float | None:
    if not isinstance(label, str):
        return None
    s = label.strip().lower()
    if s in SIZE_RANK:
        return SIZE_RANK[s]
    num = pd.to_numeric(pd.Series([s]).str.extract(r"(\d+[.,]?\d*)")[0].str.replace(",", "."), errors="coerce")[0]
    return None if pd.isna(num) else float(num)  # 300ml, 500g, 8 pedaços...


def _variant_out_of_order(group: pd.DataFrame) -> bool:
    """True se um tamanho maior custar menos que um menor (ex.: Grande < Média)."""
    g = group.dropna(subset=["price"]).assign(_r=group["variant_label"].map(_size_rank))
    ranked = g.dropna(subset=["_r"])
    if len(ranked) >= 2:
        p = ranked.sort_values("_r", kind="stable")["price"].tolist()
        return p != sorted(p)
    p = g["price"].tolist()  # rótulos desconhecidos: exige ao menos ordem monotônica
    return len(p) > 1 and p != sorted(p) and p != sorted(p, reverse=True)


def add_row_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Flags por linha (vão para o CSV) — permitem calcular as métricas depois."""
    df = df.copy()
    name = df["item_name"].fillna("").str.lower()
    cat = df["category"].fillna("").str.lower()

    df["flag_missing_required"] = df[["category", "item_name", "price"]].isna().any(axis=1)
    df["flag_price_unreasonable"] = df["price"].notna() & ~df["price"].between(config.PRICE_MIN, config.PRICE_MAX)

    df["variant_key"] = df["variant_label"].fillna("")
    df["flag_duplicate"] = df.duplicated(subset=["category", "item_name", "variant_key"], keep=False)

    median = df.groupby("category")["price"].transform("median")
    df["flag_price_outlier"] = ((df["price"] > median * 10) | (df["price"] < median / 10)).fillna(False).astype(bool)

    df["flag_item_equals_category"] = (name != "") & (name == cat)

    # variações de um item cujos preços não são monotônicos na ordem impressa
    has_var = df["variant_label"].notna()
    df["flag_variant_order"] = False
    if has_var.any():
        for _, grp in df[has_var].groupby(["category", "item_name"], dropna=False):
            if _variant_out_of_order(grp):
                df.loc[grp.index, "flag_variant_order"] = True

    df["flag_variant_order"] = df["flag_variant_order"].astype(bool)
    return df


def validate(df: pd.DataFrame) -> dict:
    """Roda a suíte do GX e decide se o cardápio é aprovado ou vai para revisão humana."""
    with _lock:
        _setup()
        result = _batch_definition.get_batch(batch_parameters={"dataframe": df}).validate(_suite)

    checks = [
        {
            "check": r.expectation_config.description,
            "criterio": (r.expectation_config.meta or {}).get("criterio"),
            "expectation": r.expectation_config.type,
            "success": bool(r.success),
            "unexpected_count": (r.result or {}).get("unexpected_count"),
            "unexpected_percent": round(r.result["unexpected_percent"], 2)
            if (r.result or {}).get("unexpected_percent") is not None
            else None,
        }
        for r in result.results
    ]
    order = {d: i for i, d in enumerate(e.description for e in EXPECTATIONS)}
    checks.sort(key=lambda c: order.get(c["check"], 99))

    passed = sum(c["success"] for c in checks)
    score = passed / len(checks)
    critical_failed = len(df) == 0  # cardápio sem itens
    return {
        "success": bool(result.success),
        "score": round(score, 3),
        "passed": passed,
        "total": len(checks),
        "status": "aprovado" if score >= config.REVIEW_THRESHOLD and not critical_failed else "revisao_humana",
        "checks": checks,
    }
