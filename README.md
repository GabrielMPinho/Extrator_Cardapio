# Cardápios ETL — POC inspirada no pipeline da DoorDash

Este projeto extrai dados estruturados de fotos de cardápios usando um **modelo multimodal** (OpenAI GPT, Abordagem 2), aplica **guardrails com Great Expectations** e persiste o resultado em um **CSV consolidado**. Todo o fluxo é orquestrado com **Prefect**. A interface gráfica é em **Streamlit**.

```
foto ──► [pre-processar-imagem] ──► [extrair-com-modelo-multimodal] ──► [estruturar-e-normalizar]
                                                                              │
         output/menu_items.csv ◄── [persistir-csv] ◄── [validar-com-great-expectations]
         output/pipeline_runs.csv
```

| Task do Prefect | O que faz |
|---|---|
| `pre-processar-imagem` | Corrige a rotação EXIF de fotos de celular, converte para RGB e limita o tamanho a 2000 px |
| `extrair-com-modelo-multimodal` | Envia imagem + prompt ao GPT (Responses API, Structured Outputs), com saída validada por um schema Pydantic (`pipeline/schemas.py`). Faz 2 retries |
| `estruturar-e-normalizar` | Achata a hierarquia categoria → item → variação em linhas e limpa os textos |
| `validar-com-great-expectations` | Roda 15 expectativas (preços, nulos, consistência, formato, duplicidade) e decide entre aprovado e revisão humana |
| `persistir-csv` | Faz append em `menu_items.csv` e `pipeline_runs.csv` |

## Estrutura

```
backend/
  pipeline/config.py        configurações (.env)
  pipeline/schemas.py       schema de saída do modelo
  pipeline/extractor.py     chamada ao modelo multimodal + custo
  pipeline/validation.py    suíte do Great Expectations (guardrails)
  pipeline/flow.py          @tasks e @flow do Prefect
  pipeline/storage.py       append nos CSVs
  pipeline/metrics.py       métricas do relatório
  app.py     interface gráfica
  scripts/run_batch.py avaliação em larga escala + relatório
data/                  imagens dos cardápios (entrada do lote)
output/                CSVs gerados
reports/               quality_report.md + metrics.json
docs/DICIONARIO_DE_DADOS.md
```

## Como rodar

Os comandos abaixo são para o terminal do Windows (PowerShell ou o terminal do VS Code) e partem da raiz do projeto. Eles chamam o Python do ambiente virtual direto (`.venv\Scripts\python`), então não é preciso ativar o ambiente.

### Primeira instalação (só uma vez)
```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```
Depois, abra `backend/.env` e preencha:
- `OPENAI_API_KEY`: a sua chave da OpenAI;
- `PRICE_INPUT_PER_1M` e `PRICE_OUTPUT_PER_1M`: os preços do modelo, usados no cálculo de custo.

### Iniciar a aplicação
```powershell
cd backend
.venv\Scripts\python -m streamlit run app.py
```
A interface abre em http://localhost:8501. Com uma foto, você acompanha cada etapa do pipeline. Com várias, elas são processadas em lote, com barra de progresso e uma tabela de resultados.

### Processar o lote de cardápios (relatório de qualidade)
Coloque as imagens em `data/` e rode:
```powershell
cd backend
.venv\Scripts\python -m scripts.run_batch                # processa os que ainda não foram processados
.venv\Scripts\python -m scripts.run_batch --force        # reprocessa todos
.venv\Scripts\python -m scripts.run_batch --report-only  # só regenera o relatório a partir dos CSVs
```
O comando gera `reports/quality_report.md` e `reports/metrics.json` com:
- % de missing data;
- % de preços razoáveis;
- latência média;
- custo médio por cardápio.

### (Opcional) Acompanhar os flows na interface do Prefect
Sem servidor configurado, o Prefect sobe um servidor temporário a cada execução. Para ver o histórico dos flows na interface web:
```powershell
# terminal 1
cd backend
.venv\Scripts\prefect server start                                    # http://127.0.0.1:4200

# terminal 2 (uma vez), depois inicie a aplicação normalmente
cd backend
.venv\Scripts\prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
```

## Configuração (`backend/.env`)
| Variável | Padrão | Descrição |
|---|---|---|
| `OPENAI_API_KEY` | — | Chave da API da OpenAI |
| `OPENAI_MODEL` | `gpt-5-mini` | Modelo multimodal. `gpt-5-mini` foi o mais barato que extraiu os cardápios completos nos testes; o `gpt-5-nano` é ~5x mais barato, mas pulou itens |
| `OPENAI_REASONING_EFFORT` | `low` | `low`/`medium`/`high`. Deixe vazio para modelos sem raciocínio (ex.: `gpt-4.1`) |
| `PRICE_INPUT_PER_1M` / `PRICE_OUTPUT_PER_1M` | `0.25` / `2.00` | Preço do modelo em US$ por 1M de tokens, usado no cálculo de custo |
| `PRICE_MIN` / `PRICE_MAX` | `1` / `1500` | Faixa de preço considerada razoável |
| `REVIEW_THRESHOLD` | `0.85` | Fração mínima de expectativas aprovadas para não ir à revisão humana |
