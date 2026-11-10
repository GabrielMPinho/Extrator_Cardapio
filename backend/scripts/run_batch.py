"""Avaliação em larga escala: processa todos os cardápios em data/ e gera o relatório de qualidade.

Uso (a partir da pasta backend/):
    python -m scripts.run_batch                # processa os que ainda não foram processados
    python -m scripts.run_batch --force        # reprocessa tudo
    python -m scripts.run_batch --report-only  # só regenera o relatório a partir dos CSVs
"""
import argparse
import json
from datetime import datetime

import sys

from pipeline import config, storage
from pipeline.flow import menu_pipeline
from pipeline.metrics import compute_metrics

EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def run_batch(force: bool) -> None:
    files = sorted(p for p in config.DATA_DIR.iterdir() if p.suffix.lower() in EXTS)
    runs = storage.read_runs()
    done = set(runs.loc[runs["status"] != "erro", "source_file"]) if len(runs) else set()
    todo = [p for p in files if force or p.name not in done]
    print(f"{len(files)} imagens em data/, {len(todo)} a processar")

    for i, path in enumerate(todo, 1):
        print(f"\n[{i}/{len(todo)}] {path.name}")
        try:
            out = menu_pipeline(path.read_bytes(), path.name)
            r = out["run"]
            print(f"  -> {r['status']} | {r['n_items']} itens | {r['latency_s']}s | US$ {r['cost_usd']:.4f}")
        except Exception as exc:
            print(f"  -> ERRO: {exc}")


def write_report() -> None:
    m = compute_metrics()
    runs = storage.read_runs()
    (config.REPORTS_DIR / "metrics.json").write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")

    def fmt(v, suf=""):
        return "—" if v is None else f"{v}{suf}"

    lines = [
        "# Relatório de Qualidade — Pipeline de Cardápios",
        f"_Gerado em {datetime.now():%d/%m/%Y %H:%M}_  ",
        f"Modelo: `{config.OPENAI_MODEL}` (reasoning effort `{config.OPENAI_REASONING_EFFORT or 'n/a'}`)",
        "",
        "## Métricas consolidadas",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Cardápios processados | {m['menus_processados']} (erros: {m['menus_com_erro']}) |",
        f"| Aprovados / revisão humana | {m['menus_aprovados']} / {m['menus_revisao_humana']} |",
        f"| Itens extraídos | {m['itens_extraidos']} |",
        f"| **% missing data** (campos obrigatórios nulos) | **{fmt(m['pct_missing_data'], '%')}** |",
        f"| % linhas com algum campo obrigatório faltante | {fmt(m['pct_linhas_com_campo_faltante'], '%')} |",
        f"| **% preços razoáveis** ({m['faixa_preco_razoavel'][0]:g}–{m['faixa_preco_razoavel'][1]:g}) | **{fmt(m['pct_precos_razoaveis'], '%')}** |",
        f"| **Latência média** por cardápio | **{fmt(m['latencia_media_s'], ' s')}** (p50 {fmt(m['latencia_p50_s'], ' s')}, máx {fmt(m['latencia_max_s'], ' s')}) |",
        f"| Tokens médios (input / output) | {fmt(m['tokens_input_medio'])} / {fmt(m['tokens_output_medio'])} |",
        f"| **Custo médio** por cardápio | **US$ {fmt(m['custo_medio_usd'])}** (total US$ {fmt(m['custo_total_usd'])}) |",
        f"| Score médio dos guardrails (GX) | {fmt(m['score_gx_medio'])} |",
        "",
        "Missing data por campo: " + ", ".join(f"`{k}` {v}%" for k, v in m["pct_missing_por_campo"].items()),
        "",
        "## Resultado por cardápio",
        "| Arquivo | Status | Itens | GX | Legibilidade | Latência (s) | Custo (US$) | Observações |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in runs.iterrows():
        notes = str(r.get("error") if r["status"] == "erro" else r.get("notes") or "").replace("|", "/").replace("\n", " ")
        if notes == "nan":
            notes = ""
        lines.append(
            f"| {r['source_file']} | {r['status']} | {fmt(r.get('n_items'))} | "
            f"{r.get('gx_passed', '')}/{r.get('gx_total', '')} | {r.get('legibility', '')} | "
            f"{r.get('latency_s', '')} | {r.get('cost_usd', '')} | {notes[:150]} |".replace("nan", "—")
        )
    lines += ["", "## Discussão de falhas", "", "_Preencher após analisar os casos em revisão humana e com erro: layout, ruído, alucinação._"]
    (config.REPORTS_DIR / "quality_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(m, indent=2, ensure_ascii=False))
    print(f"\nRelatório salvo em {config.REPORTS_DIR / 'quality_report.md'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    if not args.report_only:
        run_batch(args.force)
    write_report()
