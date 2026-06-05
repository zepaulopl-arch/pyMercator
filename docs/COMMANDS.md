# pyMercator Commands

Atualizado em 2026-06-05 a partir do parser real de `python -m pymercator --help`.

Este manual documenta os comandos vivos apos a limpeza de legado. A operacao
normal deve ficar concentrada nos tres scripts PowerShell principais; comandos
Python diretos sao para diagnostico, desenvolvimento ou execucao pontual.

## Comandos que o operador precisa decorar

1. `.\scripts\run_daily_signal.ps1`
2. `.\scripts\run_daily_review.ps1`
3. `.\scripts\run_daily_train.ps1`
4. `.\scripts\run_weekend_full.ps1`
5. `python -m pymercator diag`

## Operacao simplificada recomendada

| Rotina | Comando | Classe |
|---|---|---|
| Dia normal | `.\scripts\run_daily_signal.ps1` | ESSENCIAL |
| Fim da tarde | `.\scripts\run_daily_review.ps1` | UTIL |
| Treino eventual | `.\scripts\run_daily_train.ps1` | ESSENCIAL |
| Fim de semana | `.\scripts\run_weekend_full.ps1` | ESSENCIAL |
| Diagnostico rapido | `python -m pymercator diag` | DIAGNOSTICO |
| Auditoria de fontes | `python -m pymercator context sources` | DIAGNOSTICO |

## Scripts PowerShell

### `scripts/run_daily_signal.ps1`

Classe: ESSENCIAL.

Finalidade: atualiza dados, roda o perfil CON, observa o universo IBOV e mostra
o painel executivo `PYMERCATOR SIGNALS`.

Quando usar: todo dia operacional.

Parametros principais:

| Parametro | Default | Uso |
|---|---:|---|
| `-Color` | off | Usa cor apenas no terminal. Sem ele, passa `--no-color`. |
| `-PY` | auto | Python especifico, se necessario. |

Outputs principais:

| Arquivo | Descricao |
|---|---|
| `runtime/daily_signal_<timestamp>/report_CON.txt` | Relatorio terminal limpo |
| `runtime/daily_signal_<timestamp>/report_CON.json` | Fonte estruturada do resumo |
| `runtime/daily_signal_<timestamp>/basket_CON.csv` | Basket analysis-only |
| `runtime/daily_signal_<timestamp>/00_update_ibov.log` | Log completo de update |
| `runtime/daily_signal_<timestamp>/02_run_CON_basket.log` | Log completo do run |
| `runtime/daily_signal_<timestamp>/03_observe_ibov.log` | Log completo de observe |
| `runtime/daily_signal_<timestamp>/manifest.json` | Manifest do run |

Exemplos:

```powershell
.\scripts\run_daily_signal.ps1
.\scripts\run_daily_signal.ps1 -Color
```

### `scripts/run_daily_review.ps1`

Classe: UTIL.

Finalidade: no fim da tarde, compara observacoes, setups bloqueados e sinais
executaveis do `report_CON.json` contra os precos locais mais recentes. A
revisao e mark-to-market hipotetico; nao muda decisao, modelo, basket ou
execucao.

Quando usar: depois do pregao, para auditar se as observacoes long/short e os
bloqueios teriam gerado ganho ou perda.

Parametros principais:

| Parametro | Default | Uso |
|---|---:|---|
| `-RunDir` | ultimo `runtime/daily_signal_*` | Runtime do sinal diario a revisar. |
| `-Capital` | `100000` | Capital hipotetico para alocacao equal-weight por bloco. |
| `-Mode` | `observation` | Modo de revisao. |
| `-Profile` | `CON` | Perfil do report JSON. |
| `-PricesDir` | `data/prices` | Diretorio de precos locais. |
| `-SkipUpdate` | off | Nao tenta atualizar precos antes da revisao. |
| `-Color` | off | Mantem compatibilidade com a rotina de terminal. |

Outputs principais:

| Arquivo | Descricao |
|---|---|
| `runtime/daily_signal_<timestamp>/observation_review.txt` | Tela de revisao financeira |
| `runtime/daily_signal_<timestamp>/observation_review.csv` | Linhas avaliadas |
| `runtime/daily_signal_<timestamp>/observation_review.json` | Resultado estruturado |
| `runtime/daily_signal_<timestamp>/06_observation_review.log` | Log do comando `mtm` |

Exemplos:

```powershell
.\scripts\run_daily_review.ps1
.\scripts\run_daily_review.ps1 -RunDir runtime\daily_signal_20260605_160559 -Capital 100000
.\scripts\run_daily_review.ps1 -SkipUpdate
```

### `scripts/run_daily_train.ps1`

Classe: ESSENCIAL.

Finalidade: atualiza, treina, roda perfis CON/BAL/AGR/RLX, monta `PROFILE
SUMMARY`, `SYSTEM CHECKS`, `VERDICT` e `KEY FILES`.

Quando usar: treino eventual ou revisao operacional mais completa.

Parametros principais:

| Parametro | Default | Uso |
|---|---:|---|
| `-Color` | off | Usa cor apenas no terminal. |
| `-PY` | auto | Python especifico, se necessario. |

Exemplos:

```powershell
.\scripts\run_daily_train.ps1
.\scripts\run_daily_train.ps1 -Color
```

### `scripts/run_weekend_full.ps1`

Classe: ESSENCIAL.

Finalidade: fluxo completo de fim de semana, incluindo treino, scenario
positive, pytest e fechamento com arquivos-chave.

Quando usar: validacao semanal ou apos mudancas maiores.

Exemplos:

```powershell
.\scripts\run_weekend_full.ps1
.\scripts\run_weekend_full.ps1 -Color
```

### `scripts/ops_common.ps1`

Classe: UTIL.

Finalidade: biblioteca comum dos scripts. Nao deve ser chamada diretamente.
Centraliza inicializacao, execucao com logs, remocao de ANSI, manifest e
renderizacao final dos scripts.

### `scripts/dump_cli_help.ps1`

Classe: DIAGNOSTICO.

Finalidade: gera `runtime/cli_help_<timestamp>/help_index.txt` com `--help` dos
comandos vivos. Continua mesmo se algum comando futuro estiver indisponivel.

Exemplo:

```powershell
.\scripts\dump_cli_help.ps1
```

## CLI Python

Comando base:

```powershell
python -m pymercator [--color auto|always|never] [--no-color] <command> ...
```

Sem `-Color` nos scripts, a chamada usa `--no-color`. Arquivos JSON, CSV, TXT,
logs e manifests nao devem conter ANSI.

## Classificacao dos comandos Python

| Comando | Classe | Uso recomendado |
|---|---|---|
| `update` | ESSENCIAL | Atualizar dados, contexto, universo e features. |
| `train` | ESSENCIAL | Treinar ensemble D5/D20/D60 e benchmark de engines. |
| `run` | ESSENCIAL | Rodar decisao operacional por perfil. |
| `observe` | UTIL | Gerar ranking de observacao, sem compra automatica. |
| `basket` | UTIL | Criar ou mostrar basket analysis-only. |
| `mtm` | UTIL | Revisar observacoes e setups contra precos posteriores. |
| `review` | UTIL | Alias de `mtm`. |
| `context` | DIAGNOSTICO | Ver, auditar e atualizar contexto de mercado. |
| `db` | UTIL | Consultar historico SQLite local. |
| `diag` | DIAGNOSTICO | Verificar ambiente e configuracoes principais. |
| `scenario` | DIAGNOSTICO | Rodar cenarios sinteticos controlados. |
| `borrow` | UTIL | Ver/importar/diagnosticar dados de aluguel. |
| `pos` | UTIL | Utilitarios de posicoes. |
| `prices` | DESENVOLVIMENTO | Fetch/check/template de precos. |
| `universe` | DESENVOLVIMENTO | Check/build/diagnose de universo. |
| `features` | DESENVOLVIMENTO | Build/audit da Feature Factory v2. |
| `indices` | DESENVOLVIMENTO | Fetch/check/catalog de indices. |
| `sentiment` | DESENVOLVIMENTO | Check de diretorio de sentimento. |
| `predict` | DESENVOLVIMENTO | Dataset/evaluate/lab de predicao. |
| `execution` | DESENVOLVIMENTO | Template/check da politica de execucao. |
| `daily` | DESENVOLVIMENTO | Relatorio diario antigo e simples; preferir scripts. |
| `lab` | DESENVOLVIMENTO | Atalho para prediction lab. |
| `cfg` | DIAGNOSTICO | Mostrar configuracao efetiva. |
| `open` | DIAGNOSTICO | Abrir artefato recente no terminal. |

## Comandos principais

### `python -m pymercator update`

Sintaxe:

```powershell
python -m pymercator update [--list IBOV] [--start 2000-01-01] [--end YYYY-MM-DD] [--no-cache] [--json]
```

Defaults importantes:

| Opcao | Default |
|---|---|
| `--list` | `IBOV` |
| `--prices-dir` | `data/prices` |
| `--indices-catalog` | `config/indices_catalog.json` |
| `--indices-dir` | `data/indices` |
| `--context-output` | `storage/context/latest_market_context.json` |
| `--universe-output` | `data/universes/ibov_live.csv` |
| `--features-config` | `config/features.json` |
| `--matrix-output` | `storage/features/latest_feature_matrix.csv` |

Arquivos gerados: contexto consolidado, universo, matriz Feature Factory v2,
auditoria de features e logs quando chamado pelos scripts.

Quando nao usar: para tomada de decisao isolada; use `run_daily_signal.ps1`.

### `python -m pymercator train`

Sintaxe:

```powershell
python -m pymercator train [benchmark-engines] [--details] [--full] [--engines extratrees,randomforest,gradientboosting]
```

Defaults importantes:

| Opcao | Default |
|---|---|
| `--config` | `config/prediction.json` |
| `--horizons` | `5,20,60` |
| `--matrix` | `storage/features/latest_feature_matrix.csv` |
| `--dataset-output` | `storage/prediction/latest_dataset.csv` |
| `--evaluation-output` | `storage/prediction/latest_evaluation.json` |
| `--n-jobs` | `4` |
| `--calibration-method` | `sigmoid` |
| `--threshold-metric` | `balanced_accuracy` |
| `--benchmark-output` | `storage/prediction/latest_engine_benchmark.json` |

Subacao:

| Subacao | Uso |
|---|---|
| `benchmark-engines` | Compara extratrees, randomforest, gradientboosting, histgradientboosting, logistic_elasticnet, sgd_logloss_calibrated e adaboost sem alterar a config operacional. |

Exemplos:

```powershell
python -m pymercator train --details
python -m pymercator train benchmark-engines
python -m pymercator train --engines extratrees,randomforest,gradientboosting,histgradientboosting --details
```

### `python -m pymercator run`

Sintaxe:

```powershell
python -m pymercator run [--profile CON] [--list IBOV] [--basket|--no-basket] [--json]
```

Defaults importantes:

| Opcao | Default |
|---|---|
| `--profile` | `CON` |
| `--list` | `IBOV` |
| `--basket` | enabled |
| `--policy` | config padrao do projeto |
| `--context` | contexto mais recente |
| `--matrix` | matriz Feature Factory v2 mais recente |
| `--evaluation` | avaliacao mais recente |
| `--db` | `data/aurum.db` |

Arquivos gerados quando os scripts chamam: `report_<PROFILE>.txt`,
`report_<PROFILE>.json`, `basket_<PROFILE>.csv/json` e manifest.

Regra operacional: `run` nunca deve transformar observacao em compra automatica;
basket continua analysis-only.

### `python -m pymercator observe`

Sintaxe:

```powershell
python -m pymercator observe [--list IBOV] [--limit N] [--cluster] [--json]
python -m pymercator observe calibrate ...
```

Uso: ranking de observacao long; nao e sinal executavel.

### `python -m pymercator basket`

Subcomandos:

| Subcomando | Uso |
|---|---|
| `daily` | Cria basket diario analysis-only. |
| `show` | Mostra o ultimo basket disponivel. |

Exemplo:

```powershell
python -m pymercator basket show
```

### `python -m pymercator mtm`

Alias: `python -m pymercator review`.

Sintaxe:

```powershell
python -m pymercator mtm --run-dir runtime\daily_signal_<timestamp> [--capital 100000] [--mode observation]
```

Uso: revisao financeira pos-sinal. Le `report_CON.json`, compara observacoes,
sinais executaveis e setups bloqueados contra os precos locais mais recentes e
salva `observation_review.txt`, `observation_review.csv` e
`observation_review.json` dentro do proprio runtime.

Defaults importantes:

| Opcao | Default |
|---|---|
| `--capital` | `100000` |
| `--mode` | `observation` |
| `--prices-dir` | `data/prices` |
| `--profile` | `CON` |
| `--relevance-pct` | `0.5` |

Quando usar: no fim da tarde, de preferencia via
`.\scripts\run_daily_review.ps1`.

Quando nao usar: como entrada de execucao automatica. P&L de observacao e
hipotetico; bloqueio operacional mantem `real_pnl = 0`.

## Contexto e banco

### `python -m pymercator context`

Subcomandos:

| Subcomando | Uso |
|---|---|
| `auto` | Gera contexto automatico. |
| `calibrate` | Calibra thresholds por historico de indices. |
| `template` | Escreve template de contexto manual. |
| `presets` | Lista presets conhecidos. |
| `check` | Valida arquivo de contexto. |
| `sources` | Mostra diagnostico de fontes AUTO/MARKET/BCB/B3/CVM/MANUAL. |
| `show` | Mostra contexto consolidado atual. |
| `refresh` | Atualiza diagnostico de fonte especifica ou todas. |

Exemplos:

```powershell
python -m pymercator context sources
python -m pymercator context show
python -m pymercator context refresh --all
python -m pymercator context refresh --source BCB
```

### `python -m pymercator db`

Subcomandos:

| Subcomando | Uso |
|---|---|
| `status` | Mostra status do banco SQLite. |
| `last-run` | Mostra ultimo run salvo. |
| `signal` | Consulta historico por ticker. |
| `rank-last` | Mostra ultimo ranking salvo. |
| `sim-last` | Mostra ultima simulacao salva. |

Default: `--db data/aurum.db`. Erro de banco nao deve impedir geracao de sinal.

## Dados, features e diagnostico

| Comando | Subcomandos | Quando usar |
|---|---|---|
| `prices` | `fetch`, `fetch-list`, `tickers-template`, `tickers-check`, `check` | Manutencao de precos. |
| `universe` | `check`, `summary`, `template`, `build`, `diagnose` | Validar ou reconstruir universo. |
| `indices` | `fetch`, `prices-check`, `catalog`, `check` | Manutencao de indices de mercado. |
| `features` | `check`, `catalog`, `build`, `audit` | Feature Factory v2. |
| `predict` | `dataset`, `evaluate`, `lab` | Pesquisa e auditoria de predicao. |
| `borrow` | `show`, `import`, `diagnose` | Dados de aluguel para short. |
| `pos` | ver `--help` | Posicoes e exit book. |
| `execution` | `template`, `check` | Politica de execucao. |
| `scenario` | `run` | Scenario positive e cenarios sinteticos. |

Exemplos:

```powershell
python -m pymercator features build --list IBOV
python -m pymercator features audit
python -m pymercator universe diagnose --file data/universes/ibov_live.csv
python -m pymercator borrow diagnose
python -m pymercator scenario run --preset positive_risk_on --basket
```

## Atalhos de diagnostico

| Comando | Uso |
|---|---|
| `diag` | Diagnostico rapido do sistema. |
| `cfg` | Configuracao efetiva por perfil. |
| `open` | Abre artefato recente (`eval`, `matrix`, `dataset`). |
| `lab` | Atalho de desenvolvimento para prediction lab. |

## Comandos removidos nesta refatoracao

Estes comandos nao existem mais no parser atual:

| Comando removido | Motivo |
|---|---|
| `legacy` e subcomandos | Migradores e classificadores antigos sem papel operacional atual. |
| `daily-real` | Sobreposto pelos scripts principais e por `update/run`. |
| `real-pack` | Variante redundante de pack operacional antigo. |
| `scenario-pack` | Sobreposto por `scenario run` e pelos scripts. |
| `daily-auto` | Workflow antigo redundante com `run_daily_signal.ps1`. |
| `packs` | Listagem de artefatos do ecossistema pack removido. |
| `board` | Dashboard do ecossistema pack removido. |
| `confirm --pack` | Registro antigo em pack; a exigencia de confirmacao humana continua na politica operacional. |
| `features matrix` | Substituido por Feature Factory v2: `features build`. |

## Comandos que deveriam virar defaults

Ja aplicados:

| Comando | Default atual |
|---|---|
| `run` | profile CON, list IBOV, basket ligado. |
| `train` | le `config/prediction.json` e usa matriz v2 mais recente. |
| `observe` | list IBOV. |
| `basket show` | ultimo basket conhecido. |

## Regra final

Use os scripts para operar. Use comandos Python diretos para diagnosticar,
validar, auditar ou desenvolver. Se um comando nao aparece neste documento nem
em `python -m pymercator --help`, ele nao faz parte da superficie suportada.
