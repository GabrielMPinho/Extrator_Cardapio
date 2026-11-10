# Dicionário de dados

O pipeline gera dois CSVs em `output/`, ambos atualizados por **append** a cada cardápio processado.

## `output/menu_items.csv` — planilha consolidada de itens

Cada linha é um item do cardápio. Um item com várias variações de preço (P/M/G, meia/inteira, 300ml/500ml) vira uma linha por variação.

| Coluna | Tipo | Obrigatória | Descrição |
|---|---|---|---|
| `run_id` | texto (12 hex) | sim | ID da execução do pipeline. Chave para `pipeline_runs.csv` |
| `processed_at` | datetime ISO 8601 (UTC) | sim | Momento da estruturação |
| `source_file` | texto | sim | Nome do arquivo de imagem de origem |
| `restaurant_name` | texto | não | Nome do restaurante, se aparecer no cardápio |
| `currency` | texto (ISO 4217) | sim | Moeda: BRL, USD, EUR... |
| `category` | texto | **sim** | Seção do cardápio (ex.: "Pizzas", "Bebidas"). Recebe "Sem categoria" quando não há cabeçalho |
| `item_name` | texto | **sim** | Nome do prato/produto |
| `description` | texto | não | Descrição ou ingredientes |
| `variant_label` | texto | não | Rótulo da variação (ex.: "Grande"). Vazio se o item tiver preço único |
| `price` | decimal | **sim** | Preço numérico, sem símbolo de moeda. Vazio quando ilegível ou ausente na imagem |
| `attributes` | texto (separado por `; `) | não | Atributos extras: vegetariano, picante, sem glúten, serve 2... |
| `flag_missing_required` | booleano | sim | `True` se `category`, `item_name` ou `price` estiver nulo |
| `flag_price_unreasonable` | booleano | sim | `True` se o preço estiver fora da faixa razoável (padrão: 1 a 1500) |
| `flag_price_outlier` | booleano | sim | `True` se o preço for mais de 10x maior ou menor que a mediana da categoria (indício de alucinação ou erro de vírgula) |
| `flag_duplicate` | booleano | sim | `True` se houver outra linha com a mesma categoria, item e variação |
| `flag_item_equals_category` | booleano | sim | `True` se o nome do item for igual ao da categoria (cabeçalho lido como item) |
| `flag_variant_order` | booleano | sim | `True` se os preços das variações do item não seguirem a ordem dos tamanhos (ex.: G mais barato que M) |
| `menu_status` | `aprovado` \| `revisao_humana` | sim | Decisão dos guardrails para o cardápio inteiro |

**Campos obrigatórios** (usados no cálculo do % de missing data): `category`, `item_name` e `price`.

## `output/pipeline_runs.csv` — uma linha por cardápio processado

| Coluna | Tipo | Descrição |
|---|---|---|
| `run_id` | texto | ID da execução |
| `processed_at` | datetime ISO 8601 (UTC) | Início da execução |
| `source_file` | texto | Arquivo de imagem |
| `restaurant_name` | texto | Nome do restaurante identificado |
| `is_menu` | booleano | `False` se o modelo indicar que a imagem não é um cardápio |
| `legibility` | `boa` \| `media` \| `ruim` | Legibilidade da imagem, segundo o modelo |
| `n_categories` | inteiro | Número de categorias extraídas |
| `n_items` | inteiro | Número de linhas gravadas em `menu_items.csv` |
| `status` | `aprovado` \| `revisao_humana` \| `erro` | Resultado final. `erro` indica falha de extração (API, timeout, JSON inválido) |
| `gx_score` | decimal 0–1 | Fração das expectativas do Great Expectations aprovadas |
| `gx_passed` / `gx_total` | inteiro | Expectativas aprovadas / total |
| `latency_s` | decimal | Segundos do recebimento da imagem até a persistência no CSV |
| `extraction_s` | decimal | Segundos gastos só na chamada ao modelo multimodal |
| `model` | texto | Modelo que atendeu a requisição |
| `input_tokens` / `output_tokens` | inteiro | Tokens consumidos |
| `cost_usd` | decimal | Custo estimado: tokens × preço por milhão de tokens do modelo |
| `notes` | texto | Problemas relatados pelo modelo: corte, reflexo, trechos ilegíveis |
| `error` | texto | Mensagem de erro, quando `status = erro` |

## Regra de aprovação (guardrails)

O cardápio é **aprovado** quando pelo menos 85% das expectativas do GX passam (`REVIEW_THRESHOLD`) **e** ao menos um item foi extraído. Caso contrário, vai para **revisão humana**. Os dados são gravados nos dois casos, com o status marcado.
