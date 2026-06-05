# pyMercator Command Manual

Generated from real argparse parser at `2026-06-04T23:58:00+00:00`.
Help dump: `runtime\cli_help_20260604_210030\help_index.txt`.

## Operacao simplificada recomendada

Use apenas estes scripts na rotina normal:

| Rotina | Comando | Classificacao |
| --- | --- | --- |
| Dia normal | `.\scripts\run_daily_signal.ps1` | ESSENCIAL |
| Treino eventual | `.\scripts\run_daily_train.ps1` | ESSENCIAL |
| Fim de semana | `.\scripts\run_weekend_full.ps1` | ESSENCIAL |

## Comandos que o usuario precisa decorar

1. `.\scripts\run_daily_signal.ps1`
2. `.\scripts\run_daily_train.ps1`
3. `.\scripts\run_weekend_full.ps1`
4. `python -m pymercator diag`
5. `python -m pymercator context sources`

## Scripts PowerShell

### `scripts/run_daily_signal.ps1`

- Classificacao: **ESSENCIAL**
- Finalidade: Rotina normal do dia: update, diag, run CON com basket, observe, basket show e tela final PYMERCATOR SIGNALS.
- Quando usar: Use em dia operacional normal para ver compra/long, venda/short, observacao, hedge/defesa, basket e decisao final.
- Parametros: `-PY <path>` opcional; `-Color` ativa cor no terminal. Sem `-Color`, chama pymercator com `--no-color`.
- Outputs: `report_CON.txt`, `report_CON.json`, `basket_CON.csv/json`, `run_CON`, manifest e logs por etapa.
- Logs: `00_update_ibov.log`, `01_diag.log`, `02_run_CON_basket.log`, `03_observe_ibov.log`, `04_basket_show.log`.
- Runtime: `runtime/daily_signal_<timestamp>`.
- Exemplos:
  - `.\scripts\run_daily_signal.ps1`
  - `.\scripts\run_daily_signal.ps1 -Color`

### `scripts/run_daily_train.ps1`

- Classificacao: **ESSENCIAL**
- Finalidade: Treino operacional eventual com update, diag, universe diagnose, train details, perfis CON/BAL/AGR/RLX, profile summary e fechamento informativo.
- Quando usar: Use quando precisar renovar modelo/relatorios operacionais durante a semana.
- Parametros: `-PY <path>` opcional; `-Color` ativa cor no terminal. Sem `-Color`, chama pymercator com `--no-color`.
- Outputs: `storage/prediction/latest_train_detail_report.txt`, reports/baskets por perfil, manifest.
- Logs: `00_update_ibov.log`, `00_diag.log`, `01_universe_diagnose.log`, `02_train_details.log`, `run_<PROFILE>.log`, `07_basket_show_CON.log`.
- Runtime: `runtime/daily_train_<timestamp>`.
- Exemplos:
  - `.\scripts\run_daily_train.ps1`
  - `.\scripts\run_daily_train.ps1 -Color`

### `scripts/run_weekend_full.ps1`

- Classificacao: **ESSENCIAL**
- Finalidade: Rotina completa de fim de semana: install editable, diag, update, universe, train autotune details, run perfis, scenario positive e pytest.
- Quando usar: Use no fim de semana ou em validacao completa antes de confiar no ciclo operacional.
- Parametros: `-PY <path>` opcional; `-Color` ativa cor no terminal. Sem `-Color`, chama pymercator com `--no-color`.
- Outputs: Train detail, reports/baskets por perfil, scenario positive report/basket, pytest log, manifest.
- Logs: `00_pip_install_editable.log` ate `10_pytest.log`.
- Runtime: `runtime/weekend_full_<timestamp>`.
- Exemplos:
  - `.\scripts\run_weekend_full.ps1`
  - `.\scripts\run_weekend_full.ps1 -Color`

### `scripts/ops_common.ps1`

- Classificacao: **ÚTIL**
- Finalidade: Biblioteca comum dos scripts: resolve Python/runtime, cor, manifest, steps, limpeza ANSI, profile summary, system checks e PYMERCATOR SIGNALS.
- Quando usar: Dot-source pelos scripts principais; nao e entrada operacional direta.
- Parametros: Funcoes internas; sem parametros de script publico.
- Outputs: Manifest runtime, logs limpos, tela final dos scripts.
- Logs: Nao gera log sozinho; usado por `Invoke-PyMercatorStep` e `Invoke-NativeStep`.
- Runtime: Usa o diretorio criado por `New-PyMercatorLogDir`.
- Exemplos:
  - `. .\scripts\ops_common.ps1`

### `scripts/dump_cli_help.ps1`

- Classificacao: **DIAGNÓSTICO**
- Finalidade: Inventariar help real do CLI e continuar se algum comando nao existir.
- Quando usar: Use antes de atualizar documentacao de comandos.
- Parametros: `-PY <path>` opcional.
- Outputs: `runtime/cli_help_<timestamp>/help_index.txt`.
- Logs: Nao usa Tee-Object; grava um indice limpo sem ANSI.
- Runtime: `runtime/cli_help_<timestamp>`.
- Exemplos:
  - `.\scripts\dump_cli_help.ps1`

## CLI pymercator

Classificacoes usadas: ESSENCIAL, ÚTIL, DIAGNÓSTICO, DESENVOLVIMENTO, LEGADO, REMOVER/UNIFICAR.
Comandos DESENVOLVIMENTO/LEGADO/REMOVER sao avancados: existem por compatibilidade, pesquisa ou auditoria; nao fazem parte da operacao simplificada.

### Indice de comandos reais

| Comando | Classificacao | Help |
| --- | --- | --- |
| `python -m pymercator update` | ESSENCIAL | pymercator update |
| `python -m pymercator train` | ESSENCIAL | Train multi-horizon prediction ensemble. Profile-independent. |
| `python -m pymercator run` | ESSENCIAL | Run daily decision using an operational profile. |
| `python -m pymercator observe` | ÚTIL | Rank assets for observation without generating trade signals. |
| `python -m pymercator observe calibrate` | ÚTIL | pymercator observe calibrate |
| `python -m pymercator pos` | ÚTIL | pymercator pos |
| `python -m pymercator pos show` | ÚTIL | pymercator pos show |
| `python -m pymercator pos import` | ÚTIL | pymercator pos import |
| `python -m pymercator borrow` | ÚTIL | pymercator borrow |
| `python -m pymercator borrow show` | ÚTIL | pymercator borrow show |
| `python -m pymercator borrow import` | ÚTIL | pymercator borrow import |
| `python -m pymercator borrow diagnose` | ÚTIL | pymercator borrow diagnose |
| `python -m pymercator lab` | DESENVOLVIMENTO | pymercator lab |
| `python -m pymercator cfg` | DESENVOLVIMENTO | pymercator cfg |
| `python -m pymercator board` | DESENVOLVIMENTO | pymercator board |
| `python -m pymercator open` | DESENVOLVIMENTO | pymercator open |
| `python -m pymercator diag` | DIAGNÓSTICO | pymercator diag |
| `python -m pymercator basket` | ÚTIL | pymercator basket |
| `python -m pymercator basket daily` | ÚTIL | pymercator basket daily |
| `python -m pymercator basket show` | ÚTIL | pymercator basket show |
| `python -m pymercator daily` | REMOVER/UNIFICAR | pymercator daily |
| `python -m pymercator daily-real` | REMOVER/UNIFICAR | pymercator daily-real |
| `python -m pymercator real-pack` | DESENVOLVIMENTO | pymercator real-pack |
| `python -m pymercator scenario-pack` | REMOVER/UNIFICAR | pymercator scenario-pack |
| `python -m pymercator scenario` | DESENVOLVIMENTO | pymercator scenario |
| `python -m pymercator scenario run` | DESENVOLVIMENTO | pymercator scenario run |
| `python -m pymercator daily-auto` | DESENVOLVIMENTO | pymercator daily-auto |
| `python -m pymercator context` | DIAGNÓSTICO | pymercator context |
| `python -m pymercator context auto` | DIAGNÓSTICO | pymercator context auto |
| `python -m pymercator context calibrate` | DIAGNÓSTICO | pymercator context calibrate |
| `python -m pymercator context template` | DIAGNÓSTICO | pymercator context template |
| `python -m pymercator context presets` | DIAGNÓSTICO | pymercator context presets |
| `python -m pymercator context check` | DIAGNÓSTICO | pymercator context check |
| `python -m pymercator context sources` | DIAGNÓSTICO | pymercator context sources |
| `python -m pymercator context show` | DIAGNÓSTICO | pymercator context show |
| `python -m pymercator context refresh` | ÚTIL | pymercator context refresh |
| `python -m pymercator execution` | DESENVOLVIMENTO | pymercator execution |
| `python -m pymercator execution template` | DESENVOLVIMENTO | pymercator execution template |
| `python -m pymercator execution check` | DESENVOLVIMENTO | pymercator execution check |
| `python -m pymercator indices` | DIAGNÓSTICO | pymercator indices |
| `python -m pymercator indices fetch` | DIAGNÓSTICO | pymercator indices fetch |
| `python -m pymercator indices prices-check` | DIAGNÓSTICO | pymercator indices prices-check |
| `python -m pymercator indices catalog` | DIAGNÓSTICO | pymercator indices catalog |
| `python -m pymercator indices check` | DIAGNÓSTICO | pymercator indices check |
| `python -m pymercator sentiment` | DIAGNÓSTICO | pymercator sentiment |
| `python -m pymercator sentiment check` | DIAGNÓSTICO | pymercator sentiment check |
| `python -m pymercator predict` | DESENVOLVIMENTO | pymercator predict |
| `python -m pymercator predict dataset` | DESENVOLVIMENTO | pymercator predict dataset |
| `python -m pymercator predict evaluate` | DESENVOLVIMENTO | pymercator predict evaluate |
| `python -m pymercator predict lab` | DESENVOLVIMENTO | pymercator predict lab |
| `python -m pymercator features` | DESENVOLVIMENTO | pymercator features |
| `python -m pymercator features check` | DESENVOLVIMENTO | pymercator features check |
| `python -m pymercator features catalog` | DESENVOLVIMENTO | pymercator features catalog |
| `python -m pymercator features matrix` | DESENVOLVIMENTO | pymercator features matrix |
| `python -m pymercator confirm` | ÚTIL | pymercator confirm |
| `python -m pymercator legacy` | LEGADO | pymercator legacy |
| `python -m pymercator legacy classify` | LEGADO | pymercator legacy classify |
| `python -m pymercator legacy migrate-sentiment` | LEGADO | pymercator legacy migrate-sentiment |
| `python -m pymercator legacy migrate-features` | LEGADO | pymercator legacy migrate-features |
| `python -m pymercator legacy migrate-indices` | LEGADO | pymercator legacy migrate-indices |
| `python -m pymercator legacy migrate-universe` | LEGADO | pymercator legacy migrate-universe |
| `python -m pymercator legacy scan` | LEGADO | pymercator legacy scan |
| `python -m pymercator packs` | ÚTIL | pymercator packs |
| `python -m pymercator prices` | DIAGNÓSTICO | pymercator prices |
| `python -m pymercator prices fetch` | DIAGNÓSTICO | pymercator prices fetch |
| `python -m pymercator prices fetch-list` | DIAGNÓSTICO | pymercator prices fetch-list |
| `python -m pymercator prices tickers-template` | DIAGNÓSTICO | pymercator prices tickers-template |
| `python -m pymercator prices tickers-check` | DIAGNÓSTICO | pymercator prices tickers-check |
| `python -m pymercator prices check` | DIAGNÓSTICO | pymercator prices check |
| `python -m pymercator universe` | DIAGNÓSTICO | pymercator universe |
| `python -m pymercator universe check` | DIAGNÓSTICO | pymercator universe check |
| `python -m pymercator universe summary` | DIAGNÓSTICO | pymercator universe summary |
| `python -m pymercator universe template` | DIAGNÓSTICO | pymercator universe template |
| `python -m pymercator universe build` | DIAGNÓSTICO | pymercator universe build |
| `python -m pymercator universe diagnose` | DIAGNÓSTICO | pymercator universe diagnose |

### `python -m pymercator update`

- Classificacao: **ESSENCIAL**
- Sintaxe: `python -m pymercator update [opcoes]`
- Quando usar: Atualizar precos, indices, universo, features e contexto antes de operar.
- Quando nao usar: Nao use como substituto de `run_daily_signal.ps1` no dia normal; o script ja chama update.
- Arquivos lidos: config/indices_catalog.json, config/features_catalog.json, config/market_context*.json, listas de tickers
- Arquivos gerados: data/prices, data/indices, data/universes/ibov_live.csv, storage/features/latest_feature_matrix.csv, storage/context/latest_market_context.json, storage/context/latest_update_status.json

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--list` | `list` | `'IBOV'` | no | `-` | - |
| `--start` | `start` | `'2000-01-01'` | no | `-` | - |
| `--end` | `end` | `''` | no | `-` | - |
| `--no-cache` | `no_cache` | `False` | no | `-` | - |
| `--tickers-file` | `tickers_file` | `''` | no | `-` | - |
| `--prices-dir` | `prices_dir` | `'data/prices'` | no | `-` | - |
| `--indices-catalog` | `indices_catalog` | `'config/indices_catalog.json'` | no | `-` | - |
| `--indices-dir` | `indices_dir` | `'data/indices'` | no | `-` | - |
| `--context-output` | `context_output` | `'storage/context/latest_market_context.json'` | no | `-` | - |
| `--context-config` | `context_config` | `'config/market_context.json'` | no | `-` | - |
| `--context-thresholds` | `context_thresholds` | `'config/market_context_thresholds.json'` | no | `-` | - |
| `--universe-output` | `universe_output` | `'data/universes/ibov_live.csv'` | no | `-` | - |
| `--features-catalog` | `features_catalog` | `'config/features_catalog.json'` | no | `-` | - |
| `--matrix-output` | `matrix_output` | `'storage/features/latest_feature_matrix.csv'` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator update --help`

### `python -m pymercator train`

- Classificacao: **ESSENCIAL**
- Sintaxe: `python -m pymercator train [opcoes]`
- Quando usar: Treinar ou auditar o modelo multi-horizon. `train benchmark-engines` e laboraterio.
- Quando nao usar: Nao use para trocar defaults operacionais sem `--experimental` e validacao.
- Arquivos lidos: config/prediction.json, storage/features/latest_feature_matrix.csv, data/prices
- Arquivos gerados: storage/prediction/latest_dataset.csv, storage/prediction/latest_evaluation.json, storage/prediction/latest_multi_horizon_evaluation.json, storage/prediction/latest_engine_benchmark.json
- Acao avancada: `python -m pymercator train benchmark-engines` compara engines e grava `storage/prediction/latest_engine_benchmark.json` sem alterar config operacional.

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `train_action` | `train_action` | `None` | no | `benchmark-engines` | Advanced train action. Use benchmark-engines to compare engines. |
| `--details` | `details` | `False` | no | `-` | Print operational training detail report. |
| `--prob-dist` | `prob_dist` | `False` | no | `-` | Include probability distribution buckets in --details. |
| `--full` | `full` | `False` | no | `-` | Include all detail report sections. |
| `--output` | `output` | `''` | no | `-` | Write detailed training report TXT. Used with --details. |
| `--config` | `config` | `'config/prediction.json'` | no | `-` | Prediction config file. Default: config/prediction.json |
| `--horizons` | `horizons` | `''` | no | `-` | Prediction horizons in trading days. Default: 5,20,60 |
| `--matrix` | `matrix` | `'storage/features/latest_feature_matrix.csv'` | no | `-` | - |
| `--universe` | `universe` | `'data/universes/ibov_live.csv'` | no | `-` | - |
| `--prices-dir` | `prices_dir` | `'data/prices'` | no | `-` | - |
| `--dataset-output` | `dataset_output` | `'storage/prediction/latest_dataset.csv'` | no | `-` | - |
| `--evaluation-output` | `evaluation_output` | `'storage/prediction/latest_evaluation.json'` | no | `-` | - |
| `--min-history` | `min_history` | `None` | no | `-` | Minimum price history. Default: 120 |
| `--min-train-rows` | `min_train_rows` | `None` | no | `-` | Minimum training rows. Default: 100 |
| `--engines` | `engines` | `''` | no | `-` | Base engines for multi_horizon_ridge. Valid: extratrees, randomforest, gradientboosting. Baseline: rolling_majority With --details, a bare --engines includes complete base engine metrics. |
| `--meta` | `meta` | `''` | no | `-` | Meta model. Default: ridge |
| `--observer` | `observer` | `''` | no | `-` | Horizon observer mode. Default: weighted |
| `--weights` | `weights` | `''` | no | `-` | Horizon weights, e.g. D5=0.25,D20=0.35,D60=0.4 |
| `--independent-horizons` | `independent_horizons` | `False` | no | `-` | - |
| `--combined-horizons` | `combined_horizons` | `False` | no | `-` | - |
| `--n-jobs` | `n_jobs` | `None` | no | `-` | Parallel workers. Default: 4 |
| `--autotune` | `autotune` | `None` | no | `-` | - |
| `--autotune-iter` | `autotune_iter` | `None` | no | `-` | Autotune iterations. Default: 20 |
| `--autotune-cv` | `autotune_cv` | `None` | no | `-` | Autotune CV folds. Default: 3 |
| `--calibration-method` | `calibration_method` | `''` | no | `sigmoid,isotonic` | Probability calibration method. Valid: sigmoid, isotonic. Default: sigmoid |
| `--calibration-cv` | `calibration_cv` | `None` | no | `-` | Probability calibration CV folds. Default: 3 |
| `--threshold-metric` | `threshold_metric` | `''` | no | `balanced_accuracy,accuracy,f1,youden` | Threshold tuning metric. Valid: balanced_accuracy, accuracy, f1, youden. Default: balanced_accuracy |
| `--disable-calibration` | `disable_calibration` | `False` | no | `-` | Disable probability calibration for base engines. |
| `--experimental` | `experimental` | `False` | no | `-` | Allow non-operational train settings and mark the evaluation experimental. |
| `--allow-small-universe` | `allow_small_universe` | `False` | no | `-` | Allow assets below operational min_assets; requires --experimental. |
| `--benchmark-output` | `benchmark_output` | `'storage/prediction/latest_engine_benchmark.json'` | no | `-` | Engine benchmark JSON output. |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator train --help`
- `python -m pymercator train`
- `python -m pymercator train --details`
- `python -m pymercator train benchmark-engines`

### `python -m pymercator run`

- Classificacao: **ESSENCIAL**
- Sintaxe: `python -m pymercator run [opcoes]`
- Quando usar: Gerar decisao diaria, relaterio e basket long para um perfil.
- Quando nao usar: Nao use para executar ordens automaticamente; a saida exige revisao humana.
- Arquivos lidos: config/policy.json, config/observation.json, storage/context/latest_market_context.json, storage/features/latest_feature_matrix.csv, storage/prediction/latest_evaluation.json, storage/positions/current_positions.csv, storage/borrow/latest_borrow_data.csv
- Arquivos gerados: storage/reports/latest_daily_report.txt/json, storage/runs/latest, storage/baskets/latest_daily_basket.csv/json

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--profile` | `profile` | `'CON'` | no | `-` | - |
| `--list` | `list` | `'IBOV'` | no | `-` | - |
| `--policy` | `policy` | `'config/policy.json'` | no | `-` | - |
| `--universe` | `universe` | `'data/universes/ibov_live.csv'` | no | `-` | - |
| `--context` | `context` | `'storage/context/latest_market_context.json'` | no | `-` | - |
| `--matrix` | `matrix` | `'storage/features/latest_feature_matrix.csv'` | no | `-` | - |
| `--evaluation` | `evaluation` | `'storage/prediction/latest_evaluation.json'` | no | `-` | - |
| `--observation-config` | `observation_config` | `'config/observation.json'` | no | `-` | - |
| `--positions` | `positions` | `'storage/positions/current_positions.csv'` | no | `-` | - |
| `--borrow-data` | `borrow_data` | `'storage/borrow/latest_borrow_data.csv'` | no | `-` | - |
| `--prices-dir` | `prices_dir` | `'data/prices'` | no | `-` | - |
| `--limit` | `limit` | `20` | no | `-` | - |
| `--run-dir` | `run_dir` | `'storage/runs/latest'` | no | `-` | - |
| `--report-output` | `report_output` | `'storage/reports/latest_daily_report.txt'` | no | `-` | - |
| `--json-output` | `json_output` | `'storage/reports/latest_daily_report.json'` | no | `-` | - |
| `--basket, --no-basket` | `basket` | `True` | no | `-` | Generate basket output. Default: enabled. Use --no-basket to disable. |
| `--slots` | `slots` | `5` | no | `-` | - |
| `--min-sectors` | `min_sectors` | `3` | no | `-` | - |
| `--min-weight` | `min_weight` | `0.1` | no | `-` | - |
| `--capital` | `capital` | `100000.0` | no | `-` | - |
| `--risk-per-trade` | `risk_per_trade` | `0.005` | no | `-` | - |
| `--targets` | `targets` | `2` | no | `-` | - |
| `--stop` | `stop` | `'progressive'` | no | `progressive` | - |
| `--basket-output` | `basket_output` | `'storage/baskets/latest_daily_basket.csv'` | no | `-` | - |
| `--allow-experimental-model` | `allow_experimental_model` | `False` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator run --help`
- `python -m pymercator run`
- `python -m pymercator run --no-basket`

### `python -m pymercator observe`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator observe [opcoes]`
- Quando usar: Listar ativos para observacao sem transformar observacao em compra.
- Quando nao usar: Nao use como sinal de compra.
- Arquivos lidos: data/universes/ibov_live.csv, config/observation.json
- Arquivos gerados: terminal/JSON quando `--json`, storage/calibration/latest_observation_calibration.json em calibrate
- Subcomandos reais: `calibrate`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--list` | `list` | `'IBOV'` | no | `-` | - |
| `--universe` | `universe` | `'data/universes/ibov_live.csv'` | no | `-` | - |
| `--config` | `config` | `'config/observation.json'` | no | `-` | - |
| `--limit` | `limit` | `20` | no | `-` | - |
| `--cluster` | `cluster` | `False` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator observe --help`
- `python -m pymercator observe`

### `python -m pymercator observe calibrate`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator observe calibrate [opcoes]`
- Quando usar: Listar ativos para observacao sem transformar observacao em compra.
- Quando nao usar: Nao use como sinal de compra.
- Arquivos lidos: data/universes/ibov_live.csv, config/observation.json
- Arquivos gerados: terminal/JSON quando `--json`, storage/calibration/latest_observation_calibration.json em calibrate

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--list` | `list` | `'IBOV'` | no | `-` | - |
| `--universe` | `universe` | `'data/universes/ibov_live.csv'` | no | `-` | - |
| `--config` | `config` | `'config/observation.json'` | no | `-` | - |
| `--output` | `output` | `'storage/calibration/latest_observation_calibration.json'` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator observe calibrate --help`

### `python -m pymercator pos`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator pos [opcoes]`
- Quando usar: Mostrar ou importar posicoes abertas.
- Quando nao usar: Nao use para decisao long sem rodar run/signal.
- Arquivos lidos: storage/positions/current_positions.csv
- Arquivos gerados: storage/positions/current_positions.csv
- Subcomandos reais: `import`, `show`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--json` | `pos_json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator pos --help`

### `python -m pymercator pos show`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator pos show [opcoes]`
- Quando usar: Mostrar ou importar posicoes abertas.
- Quando nao usar: Nao use para decisao long sem rodar run/signal.
- Arquivos lidos: storage/positions/current_positions.csv
- Arquivos gerados: storage/positions/current_positions.csv

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `'storage/positions/current_positions.csv'` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator pos show --help`

### `python -m pymercator pos import`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator pos import [opcoes]`
- Quando usar: Mostrar ou importar posicoes abertas.
- Quando nao usar: Nao use para decisao long sem rodar run/signal.
- Arquivos lidos: storage/positions/current_positions.csv
- Arquivos gerados: storage/positions/current_positions.csv

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |
| `--output` | `output` | `'storage/positions/current_positions.csv'` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator pos import --help`

### `python -m pymercator borrow`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator borrow [opcoes]`
- Quando usar: Importar, mostrar e diagnosticar aluguel para short.
- Quando nao usar: Nao use falta de borrow para esconder setup; ela bloqueia execucao.
- Arquivos lidos: storage/borrow/latest_borrow_data.csv, data/universes/ibov_live.csv
- Arquivos gerados: storage/borrow/current/latest conforme `--output`
- Subcomandos reais: `diagnose`, `import`, `show`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator borrow --help`

### `python -m pymercator borrow show`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator borrow show [opcoes]`
- Quando usar: Importar, mostrar e diagnosticar aluguel para short.
- Quando nao usar: Nao use falta de borrow para esconder setup; ela bloqueia execucao.
- Arquivos lidos: storage/borrow/latest_borrow_data.csv, data/universes/ibov_live.csv
- Arquivos gerados: storage/borrow/current/latest conforme `--output`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `''` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator borrow show --help`

### `python -m pymercator borrow import`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator borrow import [opcoes]`
- Quando usar: Importar, mostrar e diagnosticar aluguel para short.
- Quando nao usar: Nao use falta de borrow para esconder setup; ela bloqueia execucao.
- Arquivos lidos: storage/borrow/latest_borrow_data.csv, data/universes/ibov_live.csv
- Arquivos gerados: storage/borrow/current/latest conforme `--output`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |
| `--output` | `output` | `''` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator borrow import --help`

### `python -m pymercator borrow diagnose`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator borrow diagnose [opcoes]`
- Quando usar: Importar, mostrar e diagnosticar aluguel para short.
- Quando nao usar: Nao use falta de borrow para esconder setup; ela bloqueia execucao.
- Arquivos lidos: storage/borrow/latest_borrow_data.csv, data/universes/ibov_live.csv
- Arquivos gerados: storage/borrow/current/latest conforme `--output`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `''` | no | `-` | - |
| `--tickers-file` | `tickers_file` | `'data/universes/ibov_live.csv'` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator borrow diagnose --help`

### `python -m pymercator lab`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator lab [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--fast` | `fast` | `False` | no | `-` | - |
| `--engines` | `engines` | `''` | no | `-` | Prediction engines to run. Valid engines: rolling_majority, extratrees, randomforest, gradientboosting, histgradientboosting, lightgbm, ridge_ensemble |
| `--autotune` | `autotune` | `False` | no | `-` | - |
| `--jobs` | `jobs` | `0` | no | `-` | Number of jobs (alias for n-jobs) |
| `--horizon` | `horizon` | `0` | no | `-` | - |
| `--profile` | `profile` | `''` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator lab --help`

### `python -m pymercator cfg`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator cfg [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--profile` | `profile` | `''` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator cfg --help`

### `python -m pymercator board`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator board [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--profile` | `profile` | `''` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator board --help`

### `python -m pymercator open`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator open [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `artifact` | `artifact` | `'eval'` | no | `-` | - |
| `--raw` | `raw` | `False` | no | `-` | - |
| `--profile` | `profile` | `''` | no | `-` | - |

Exemplos:
- `python -m pymercator open --help`

### `python -m pymercator diag`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator diag [opcoes]`
- Quando usar: Checagem rpida de configuracao, arquivos e ambiente.
- Quando nao usar: Nao substitui pytest nem weekend_full.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--profile` | `profile` | `''` | no | `-` | - |
| `--verbose` | `verbose` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator diag --help`

### `python -m pymercator basket`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator basket [opcoes]`
- Quando usar: Criar ou exibir basket analysis-only.
- Quando nao usar: Nao use como ordem automtica.
- Arquivos lidos: storage/baskets/latest_daily_basket.csv/json e artefatos de run
- Arquivos gerados: storage/baskets/latest_daily_basket.csv/json quando daily
- Subcomandos reais: `daily`, `show`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--profile` | `profile` | `''` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator basket --help`

### `python -m pymercator basket daily`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator basket daily [opcoes]`
- Quando usar: Criar ou exibir basket analysis-only.
- Quando nao usar: Nao use como ordem automtica.
- Arquivos lidos: storage/baskets/latest_daily_basket.csv/json e artefatos de run
- Arquivos gerados: storage/baskets/latest_daily_basket.csv/json quando daily

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--slots` | `slots` | `5` | no | `-` | - |
| `--min-sectors` | `min_sectors` | `3` | no | `-` | - |
| `--min-weight` | `min_weight` | `0.1` | no | `-` | - |
| `--capital` | `capital` | `100000.0` | no | `-` | - |
| `--risk-per-trade` | `risk_per_trade` | `0.005` | no | `-` | - |
| `--targets` | `targets` | `2` | no | `-` | - |
| `--stop` | `stop` | `'progressive'` | no | `progressive` | - |
| `--prices-dir` | `prices_dir` | `'data/prices'` | no | `-` | - |
| `--universe` | `universe` | `'data/universes/ibov_live.csv'` | no | `-` | - |
| `--matrix` | `matrix` | `'storage/features/latest_feature_matrix.csv'` | no | `-` | - |
| `--evaluation` | `evaluation` | `'storage/prediction/latest_evaluation.json'` | no | `-` | - |
| `--output` | `output` | `'storage/baskets/latest_daily_basket.csv'` | no | `-` | - |
| `--daily-report` | `daily_report` | `''` | no | `-` | - |

Exemplos:
- `python -m pymercator basket daily --help`

### `python -m pymercator basket show`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator basket show [opcoes]`
- Quando usar: Criar ou exibir basket analysis-only.
- Quando nao usar: Nao use como ordem automtica.
- Arquivos lidos: storage/baskets/latest_daily_basket.csv/json e artefatos de run
- Arquivos gerados: storage/baskets/latest_daily_basket.csv/json quando daily

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--output` | `output` | `'storage/baskets/latest_daily_basket.csv'` | no | `-` | - |
| `--details` | `details` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator basket show --help`
- `python -m pymercator basket show`

### `python -m pymercator daily`

- Classificacao: **REMOVER/UNIFICAR**
- Sintaxe: `python -m pymercator daily [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: IBOV, config/policy.json
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--universe` | `universe` | `None` | yes | `-` | - |
| `--universe-name` | `universe_name` | `'IBOV'` | no | `-` | - |
| `--profile` | `profile` | `''` | no | `-` | - |
| `--headline-risk` | `headline_risk` | `'OFF'` | no | `-` | - |
| `--policy` | `policy` | `'config/policy.json'` | no | `-` | - |
| `--limit` | `limit` | `0` | no | `-` | - |
| `--output` | `output` | `''` | no | `-` | - |
| `--json-output` | `json_output` | `''` | no | `-` | - |
| `--run-dir` | `run_dir` | `''` | no | `-` | - |
| `--context` | `context` | `''` | no | `-` | - |
| `--context-preset` | `context_preset` | `''` | no | `-` | - |
| `--headline-tags` | `headline_tags` | `''` | no | `-` | - |
| `--market-trend` | `market_trend` | `'CHOPPY'` | no | `-` | - |
| `--market-volatility` | `market_volatility` | `'NORMAL'` | no | `-` | - |

Exemplos:
- `python -m pymercator daily --help`

### `python -m pymercator daily-real`

- Classificacao: **REMOVER/UNIFICAR**
- Sintaxe: `python -m pymercator daily-real [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: config/execution_policy.json, config/features_catalog.json, IBOV, config/policy.json
- Arquivos gerados: storage/scenario_runs

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--execution-policy` | `execution_policy` | `'config/execution_policy.json'` | no | `-` | - |
| `--tickers-file` | `tickers_file` | `None` | yes | `-` | - |
| `--features-file` | `features_file` | `'config/features_catalog.json'` | no | `-` | - |
| `--start` | `start` | `''` | no | `-` | - |
| `--end` | `end` | `''` | no | `-` | - |
| `--prices-dir` | `prices_dir` | `None` | yes | `-` | - |
| `--universe-output` | `universe_output` | `None` | yes | `-` | - |
| `--run-dir` | `run_dir` | `'storage/scenario_runs'` | no | `-` | - |
| `--universe-name` | `universe_name` | `'IBOV'` | no | `-` | - |
| `--policy` | `policy` | `'config/policy.json'` | no | `-` | - |
| `--limit` | `limit` | `0` | no | `-` | - |
| `--skip-fetch` | `skip_fetch` | `False` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |
| `--context` | `context` | `''` | no | `-` | - |
| `--context-preset` | `context_preset` | `''` | no | `-` | - |
| `--headline-tags` | `headline_tags` | `''` | no | `-` | - |
| `--market-trend` | `market_trend` | `'CHOPPY'` | no | `-` | - |
| `--market-volatility` | `market_volatility` | `'NORMAL'` | no | `-` | - |

Exemplos:
- `python -m pymercator daily-real --help`

### `python -m pymercator real-pack`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator real-pack [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: config/execution_policy.json, config/features_catalog.json, IBOV, config/policy.json
- Arquivos gerados: storage/scenario_runs

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--execution-policy` | `execution_policy` | `'config/execution_policy.json'` | no | `-` | - |
| `--tickers-file` | `tickers_file` | `None` | yes | `-` | - |
| `--features-file` | `features_file` | `'config/features_catalog.json'` | no | `-` | - |
| `--start` | `start` | `''` | no | `-` | - |
| `--end` | `end` | `''` | no | `-` | - |
| `--prices-dir` | `prices_dir` | `None` | yes | `-` | - |
| `--universe-output` | `universe_output` | `None` | yes | `-` | - |
| `--run-dir` | `run_dir` | `'storage/scenario_runs'` | no | `-` | - |
| `--universe-name` | `universe_name` | `'IBOV'` | no | `-` | - |
| `--policy` | `policy` | `'config/policy.json'` | no | `-` | - |
| `--limit` | `limit` | `0` | no | `-` | - |
| `--skip-fetch` | `skip_fetch` | `False` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |
| `--context` | `context` | `''` | no | `-` | - |
| `--context-preset` | `context_preset` | `''` | no | `-` | - |
| `--headline-tags` | `headline_tags` | `''` | no | `-` | - |
| `--market-trend` | `market_trend` | `'CHOPPY'` | no | `-` | - |
| `--market-volatility` | `market_volatility` | `'NORMAL'` | no | `-` | - |

Exemplos:
- `python -m pymercator real-pack --help`

### `python -m pymercator scenario-pack`

- Classificacao: **REMOVER/UNIFICAR**
- Sintaxe: `python -m pymercator scenario-pack [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: IBOV, config/policy.json
- Arquivos gerados: storage/scenario_runs

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--universe` | `universe` | `None` | yes | `-` | - |
| `--universe-name` | `universe_name` | `'IBOV'` | no | `-` | - |
| `--policy` | `policy` | `'config/policy.json'` | no | `-` | - |
| `--run-dir` | `run_dir` | `'storage/scenario_runs'` | no | `-` | - |
| `--limit` | `limit` | `0` | no | `-` | - |
| `--context` | `context` | `''` | no | `-` | - |
| `--context-preset` | `context_preset` | `''` | no | `-` | - |
| `--headline-tags` | `headline_tags` | `''` | no | `-` | - |
| `--market-trend` | `market_trend` | `'CHOPPY'` | no | `-` | - |
| `--market-volatility` | `market_volatility` | `'NORMAL'` | no | `-` | - |

Exemplos:
- `python -m pymercator scenario-pack --help`

### `python -m pymercator scenario`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator scenario [opcoes]`
- Quando usar: Rodar cenrios sintticos e scenario positive.
- Quando nao usar: Nao trate cenrio positivo como mercado real.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional
- Subcomandos reais: `run`
- Opcoes: sem opcoes publicas alem de `--help`.

Exemplos:
- `python -m pymercator scenario --help`

### `python -m pymercator scenario run`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator scenario run [opcoes]`
- Quando usar: Rodar cenrios sintticos e scenario positive.
- Quando nao usar: Nao trate cenrio positivo como mercado real.
- Arquivos lidos: AGR, config/policy.json
- Arquivos gerados: storage/scenarios, storage/reports/latest_daily_report.txt, storage/reports/latest_daily_report.json, storage/runs/latest, storage/baskets/latest_daily_basket.csv

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--preset` | `preset` | `'positive_risk_on'` | no | `-` | - |
| `--profile` | `profile` | `'AGR'` | no | `-` | - |
| `--policy` | `policy` | `'config/policy.json'` | no | `-` | - |
| `--output-root` | `output_root` | `'storage/scenarios'` | no | `-` | - |
| `--report-output` | `report_output` | `'storage/reports/latest_daily_report.txt'` | no | `-` | - |
| `--json-output` | `json_output` | `'storage/reports/latest_daily_report.json'` | no | `-` | - |
| `--run-dir` | `run_dir` | `'storage/runs/latest'` | no | `-` | - |
| `--limit` | `limit` | `5` | no | `-` | - |
| `--basket` | `basket` | `False` | no | `-` | - |
| `--basket-output` | `basket_output` | `'storage/baskets/latest_daily_basket.csv'` | no | `-` | - |
| `--slots` | `slots` | `5` | no | `-` | - |
| `--min-sectors` | `min_sectors` | `3` | no | `-` | - |
| `--min-weight` | `min_weight` | `0.1` | no | `-` | - |
| `--capital` | `capital` | `100000.0` | no | `-` | - |
| `--risk-per-trade` | `risk_per_trade` | `0.005` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator scenario run --help`

### `python -m pymercator daily-auto`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator daily-auto [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: config/execution_policy.json, config/indices_catalog.json, data/indices, config/features_catalog.json, data/universes/ibov_tickers.csv, data/sentiment, 2000-01-01, data/prices, IBOV, config/policy.json
- Arquivos gerados: config/market_context_auto.json, storage/features/latest_feature_matrix.csv, storage/prediction/latest_prediction_dataset.csv, storage/prediction/latest_evaluation.json, data/universes/ibov_live.csv, storage/scenario_runs

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--execution-policy` | `execution_policy` | `'config/execution_policy.json'` | no | `-` | - |
| `--indices-catalog` | `indices_catalog` | `'config/indices_catalog.json'` | no | `-` | - |
| `--indices-start` | `indices_start` | `'2000-01-01'` | no | `-` | - |
| `--indices-dir` | `indices_dir` | `'data/indices'` | no | `-` | - |
| `--context-output` | `context_output` | `'config/market_context_auto.json'` | no | `-` | - |
| `--features-file` | `features_file` | `'config/features_catalog.json'` | no | `-` | - |
| `--feature-matrix-output` | `feature_matrix_output` | `'storage/features/latest_feature_matrix.csv'` | no | `-` | - |
| `--prediction-dataset-output` | `prediction_dataset_output` | `'storage/prediction/latest_prediction_dataset.csv'` | no | `-` | - |
| `--prediction-evaluation-output` | `prediction_evaluation_output` | `'storage/prediction/latest_evaluation.json'` | no | `-` | - |
| `--prediction-horizon` | `prediction_horizon` | `5` | no | `-` | - |
| `--prediction-min-history` | `prediction_min_history` | `20` | no | `-` | - |
| `--prediction-min-train-rows` | `prediction_min_train_rows` | `100` | no | `-` | - |
| `--prediction-engines` | `prediction_engines` | `''` | no | `-` | Prediction engines to run. Valid engines: rolling_majority, extratrees, randomforest, gradientboosting, histgradientboosting, lightgbm, ridge_ensemble |
| `--prediction-n-jobs` | `prediction_n_jobs` | `4` | no | `-` | - |
| `--prediction-autotune` | `prediction_autotune` | `False` | no | `-` | - |
| `--prediction-autotune-iter` | `prediction_autotune_iter` | `15` | no | `-` | - |
| `--prediction-autotune-cv` | `prediction_autotune_cv` | `3` | no | `-` | - |
| `--tickers-file` | `tickers_file` | `'data/universes/ibov_tickers.csv'` | no | `-` | - |
| `--sentiment-dir` | `sentiment_dir` | `'data/sentiment'` | no | `-` | - |
| `--prices-start` | `prices_start` | `'2000-01-01'` | no | `-` | - |
| `--prices-dir` | `prices_dir` | `'data/prices'` | no | `-` | - |
| `--universe-output` | `universe_output` | `'data/universes/ibov_live.csv'` | no | `-` | - |
| `--run-dir` | `run_dir` | `'storage/scenario_runs'` | no | `-` | - |
| `--universe-name` | `universe_name` | `'IBOV'` | no | `-` | - |
| `--policy` | `policy` | `'config/policy.json'` | no | `-` | - |
| `--skip-asset-fetch` | `skip_asset_fetch` | `False` | no | `-` | - |
| `--skip-indices-fetch` | `skip_indices_fetch` | `False` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator daily-auto --help`

### `python -m pymercator context`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator context [opcoes]`
- Quando usar: Auditar, mostrar ou atualizar fontes de Market Context.
- Quando nao usar: Nao invente dados quando uma fonte aparecer NOT_IMPLEMENTED/FAIL.
- Arquivos lidos: storage/context/latest_market_context.json, config/market_context.json
- Arquivos gerados: storage/context/latest_market_context.json e diagnostics de fontes
- Subcomandos reais: `auto`, `calibrate`, `check`, `presets`, `refresh`, `show`, `sources`, `template`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--json` | `json` | `False` | no | `-` | - |
| `--context` | `context` | `''` | no | `-` | - |
| `--context-preset` | `context_preset` | `''` | no | `-` | - |
| `--headline-tags` | `headline_tags` | `''` | no | `-` | - |
| `--market-trend` | `market_trend` | `'CHOPPY'` | no | `-` | - |
| `--market-volatility` | `market_volatility` | `'NORMAL'` | no | `-` | - |

Exemplos:
- `python -m pymercator context --help`

### `python -m pymercator context auto`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator context auto [opcoes]`
- Quando usar: Auditar, mostrar ou atualizar fontes de Market Context.
- Quando nao usar: Nao invente dados quando uma fonte aparecer NOT_IMPLEMENTED/FAIL.
- Arquivos lidos: storage/context/latest_market_context.json, config/market_context.json
- Arquivos gerados: storage/context/latest_market_context.json e diagnostics de fontes

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--indices-dir` | `indices_dir` | `None` | yes | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |
| `--thresholds` | `thresholds` | `'config/market_context_thresholds.json'` | no | `-` | - |

Exemplos:
- `python -m pymercator context auto --help`

### `python -m pymercator context calibrate`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator context calibrate [opcoes]`
- Quando usar: Auditar, mostrar ou atualizar fontes de Market Context.
- Quando nao usar: Nao invente dados quando uma fonte aparecer NOT_IMPLEMENTED/FAIL.
- Arquivos lidos: storage/context/latest_market_context.json, config/market_context.json
- Arquivos gerados: storage/context/latest_market_context.json e diagnostics de fontes

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--indices-dir` | `indices_dir` | `None` | yes | `-` | - |
| `--output` | `output` | `'storage/calibration/latest_market_context_calibration.json'` | no | `-` | - |

Exemplos:
- `python -m pymercator context calibrate --help`

### `python -m pymercator context template`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator context template [opcoes]`
- Quando usar: Auditar, mostrar ou atualizar fontes de Market Context.
- Quando nao usar: Nao invente dados quando uma fonte aparecer NOT_IMPLEMENTED/FAIL.
- Arquivos lidos: storage/context/latest_market_context.json, config/market_context.json
- Arquivos gerados: storage/context/latest_market_context.json e diagnostics de fontes

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator context template --help`

### `python -m pymercator context presets`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator context presets [opcoes]`
- Quando usar: Auditar, mostrar ou atualizar fontes de Market Context.
- Quando nao usar: Nao invente dados quando uma fonte aparecer NOT_IMPLEMENTED/FAIL.
- Arquivos lidos: storage/context/latest_market_context.json, config/market_context.json
- Arquivos gerados: storage/context/latest_market_context.json e diagnostics de fontes
- Opcoes: sem opcoes publicas alem de `--help`.

Exemplos:
- `python -m pymercator context presets --help`

### `python -m pymercator context check`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator context check [opcoes]`
- Quando usar: Auditar, mostrar ou atualizar fontes de Market Context.
- Quando nao usar: Nao invente dados quando uma fonte aparecer NOT_IMPLEMENTED/FAIL.
- Arquivos lidos: storage/context/latest_market_context.json, config/market_context.json
- Arquivos gerados: storage/context/latest_market_context.json e diagnostics de fontes

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator context check --help`

### `python -m pymercator context sources`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator context sources [opcoes]`
- Quando usar: Auditar, mostrar ou atualizar fontes de Market Context.
- Quando nao usar: Nao invente dados quando uma fonte aparecer NOT_IMPLEMENTED/FAIL.
- Arquivos lidos: storage/context/latest_market_context.json, config/market_context.json
- Arquivos gerados: storage/context/latest_market_context.json e diagnostics de fontes

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `'storage/context/latest_market_context.json'` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator context sources --help`
- `python -m pymercator context sources`

### `python -m pymercator context show`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator context show [opcoes]`
- Quando usar: Auditar, mostrar ou atualizar fontes de Market Context.
- Quando nao usar: Nao invente dados quando uma fonte aparecer NOT_IMPLEMENTED/FAIL.
- Arquivos lidos: storage/context/latest_market_context.json, config/market_context.json
- Arquivos gerados: storage/context/latest_market_context.json e diagnostics de fontes

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `'storage/context/latest_market_context.json'` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator context show --help`

### `python -m pymercator context refresh`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator context refresh [opcoes]`
- Quando usar: Auditar, mostrar ou atualizar fontes de Market Context.
- Quando nao usar: Nao invente dados quando uma fonte aparecer NOT_IMPLEMENTED/FAIL.
- Arquivos lidos: storage/context/latest_market_context.json, config/market_context.json
- Arquivos gerados: storage/context/latest_market_context.json e diagnostics de fontes

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `'storage/context/latest_market_context.json'` | no | `-` | - |
| `--source` | `source` | `''` | no | `-` | - |
| `--all` | `all` | `False` | no | `-` | - |
| `--config` | `config` | `'config/market_context.json'` | no | `-` | - |
| `--timeout` | `timeout` | `10` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator context refresh --help`

### `python -m pymercator execution`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator execution [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional
- Subcomandos reais: `check`, `template`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator execution --help`

### `python -m pymercator execution template`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator execution template [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator execution template --help`

### `python -m pymercator execution check`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator execution check [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator execution check --help`

### `python -m pymercator indices`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator indices [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional
- Subcomandos reais: `catalog`, `check`, `fetch`, `prices-check`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator indices --help`

### `python -m pymercator indices fetch`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator indices fetch [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--catalog` | `catalog` | `None` | yes | `-` | - |
| `--start` | `start` | `None` | yes | `-` | - |
| `--end` | `end` | `''` | no | `-` | - |
| `--no-cache` | `no_cache` | `False` | no | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator indices fetch --help`

### `python -m pymercator indices prices-check`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator indices prices-check [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--prices-dir` | `prices_dir` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator indices prices-check --help`

### `python -m pymercator indices catalog`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator indices catalog [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator indices catalog --help`

### `python -m pymercator indices check`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator indices check [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator indices check --help`

### `python -m pymercator sentiment`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator sentiment [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional
- Subcomandos reais: `check`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator sentiment --help`

### `python -m pymercator sentiment check`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator sentiment check [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--sentiment-dir` | `sentiment_dir` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator sentiment check --help`

### `python -m pymercator predict`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator predict [opcoes]`
- Quando usar: Ferramentas de dataset/evaluate/lab para pesquisa de modelo.
- Quando nao usar: Nao e o caminho operacional simplificado.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional
- Subcomandos reais: `dataset`, `evaluate`, `lab`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator predict --help`

### `python -m pymercator predict dataset`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator predict dataset [opcoes]`
- Quando usar: Ferramentas de dataset/evaluate/lab para pesquisa de modelo.
- Quando nao usar: Nao e o caminho operacional simplificado.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--matrix` | `matrix` | `None` | yes | `-` | - |
| `--prices-dir` | `prices_dir` | `None` | yes | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |
| `--horizon` | `horizon` | `5` | no | `-` | - |
| `--min-history` | `min_history` | `20` | no | `-` | - |

Exemplos:
- `python -m pymercator predict dataset --help`

### `python -m pymercator predict evaluate`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator predict evaluate [opcoes]`
- Quando usar: Ferramentas de dataset/evaluate/lab para pesquisa de modelo.
- Quando nao usar: Nao e o caminho operacional simplificado.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--dataset` | `dataset` | `None` | yes | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |
| `--horizon` | `horizon` | `5` | no | `-` | - |
| `--min-train-rows` | `min_train_rows` | `100` | no | `-` | - |
| `--engines` | `engines` | `''` | no | `-` | Prediction engines to run. Valid engines: rolling_majority, extratrees, randomforest, gradientboosting, histgradientboosting, lightgbm, ridge_ensemble |
| `--n-jobs` | `n_jobs` | `1` | no | `-` | - |
| `--autotune` | `autotune` | `False` | no | `-` | - |
| `--autotune-iter` | `autotune_iter` | `0` | no | `-` | - |
| `--autotune-cv` | `autotune_cv` | `0` | no | `-` | - |

Exemplos:
- `python -m pymercator predict evaluate --help`

### `python -m pymercator predict lab`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator predict lab [opcoes]`
- Quando usar: Ferramentas de dataset/evaluate/lab para pesquisa de modelo.
- Quando nao usar: Nao e o caminho operacional simplificado.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--matrix` | `matrix` | `None` | yes | `-` | - |
| `--prices-dir` | `prices_dir` | `None` | yes | `-` | - |
| `--dataset-output` | `dataset_output` | `None` | yes | `-` | - |
| `--evaluation-output` | `evaluation_output` | `None` | yes | `-` | - |
| `--horizon` | `horizon` | `5` | no | `-` | Prediction horizon in trading days. Default: 5 |
| `--min-history` | `min_history` | `20` | no | `-` | Minimum price history. Default: 20 |
| `--min-train-rows` | `min_train_rows` | `100` | no | `-` | Minimum training rows. Default: 100 |
| `--engines` | `engines` | `''` | no | `-` | Prediction engines to run. Valid engines: rolling_majority, extratrees, randomforest, gradientboosting, histgradientboosting, lightgbm, ridge_ensemble |
| `--n-jobs` | `n_jobs` | `4` | no | `-` | Parallel workers. Default: 4 |
| `--autotune` | `autotune` | `False` | no | `-` | - |
| `--autotune-iter` | `autotune_iter` | `0` | no | `-` | - |
| `--autotune-cv` | `autotune_cv` | `0` | no | `-` | - |

Exemplos:
- `python -m pymercator predict lab --help`

### `python -m pymercator features`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator features [opcoes]`
- Quando usar: Validar catelogo ou gerar matriz de features.
- Quando nao usar: Nao rode manualmente no dia normal se update ja cobre.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional
- Subcomandos reais: `catalog`, `check`, `matrix`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator features --help`

### `python -m pymercator features check`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator features check [opcoes]`
- Quando usar: Validar catelogo ou gerar matriz de features.
- Quando nao usar: Nao rode manualmente no dia normal se update ja cobre.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator features check --help`

### `python -m pymercator features catalog`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator features catalog [opcoes]`
- Quando usar: Validar catelogo ou gerar matriz de features.
- Quando nao usar: Nao rode manualmente no dia normal se update ja cobre.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator features catalog --help`

### `python -m pymercator features matrix`

- Classificacao: **DESENVOLVIMENTO**
- Sintaxe: `python -m pymercator features matrix [opcoes]`
- Quando usar: Validar catelogo ou gerar matriz de features.
- Quando nao usar: Nao rode manualmente no dia normal se update ja cobre.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--universe` | `universe` | `None` | yes | `-` | - |
| `--prices-dir` | `prices_dir` | `None` | yes | `-` | - |
| `--context` | `context` | `None` | yes | `-` | - |
| `--features` | `features` | `None` | yes | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator features matrix --help`

### `python -m pymercator confirm`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator confirm [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: config/execution_policy.json
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--pack` | `pack` | `None` | yes | `-` | - |
| `--ticker` | `ticker` | `None` | yes | `-` | - |
| `--decision` | `decision` | `None` | yes | `-` | - |
| `--notes` | `notes` | `''` | no | `-` | - |
| `--operator` | `operator` | `''` | no | `-` | - |
| `--execution-policy` | `execution_policy` | `'config/execution_policy.json'` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator confirm --help`

### `python -m pymercator legacy`

- Classificacao: **LEGADO**
- Sintaxe: `python -m pymercator legacy [opcoes]`
- Quando usar: Inventrio e migracao de cdigo/dados legados.
- Quando nao usar: Nao use em operacao diaria.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional
- Subcomandos reais: `classify`, `migrate-features`, `migrate-indices`, `migrate-sentiment`, `migrate-universe`, `scan`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator legacy --help`

### `python -m pymercator legacy classify`

- Classificacao: **LEGADO**
- Sintaxe: `python -m pymercator legacy classify [opcoes]`
- Quando usar: Inventrio e migracao de cdigo/dados legados.
- Quando nao usar: Nao use em operacao diaria.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--inventory` | `inventory` | `None` | yes | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator legacy classify --help`

### `python -m pymercator legacy migrate-sentiment`

- Classificacao: **LEGADO**
- Sintaxe: `python -m pymercator legacy migrate-sentiment [opcoes]`
- Quando usar: Inventrio e migracao de cdigo/dados legados.
- Quando nao usar: Nao use em operacao diaria.
- Arquivos lidos: data/sentiment
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--legacy-path` | `legacy_path` | `None` | yes | `-` | - |
| `--source-dir` | `source_dir` | `'data/sentiment'` | no | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator legacy migrate-sentiment --help`

### `python -m pymercator legacy migrate-features`

- Classificacao: **LEGADO**
- Sintaxe: `python -m pymercator legacy migrate-features [opcoes]`
- Quando usar: Inventrio e migracao de cdigo/dados legados.
- Quando nao usar: Nao use em operacao diaria.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--legacy-path` | `legacy_path` | `None` | yes | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator legacy migrate-features --help`

### `python -m pymercator legacy migrate-indices`

- Classificacao: **LEGADO**
- Sintaxe: `python -m pymercator legacy migrate-indices [opcoes]`
- Quando usar: Inventrio e migracao de cdigo/dados legados.
- Quando nao usar: Nao use em operacao diaria.
- Arquivos lidos: config/indices/catalog.yaml
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--legacy-path` | `legacy_path` | `None` | yes | `-` | - |
| `--catalog-file` | `catalog_file` | `'config/indices/catalog.yaml'` | no | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator legacy migrate-indices --help`

### `python -m pymercator legacy migrate-universe`

- Classificacao: **LEGADO**
- Sintaxe: `python -m pymercator legacy migrate-universe [opcoes]`
- Quando usar: Inventrio e migracao de cdigo/dados legados.
- Quando nao usar: Nao use em operacao diaria.
- Arquivos lidos: config/assets/ibov_assets.yaml, config/universes/ibov.yaml
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--legacy-path` | `legacy_path` | `None` | yes | `-` | - |
| `--assets-file` | `assets_file` | `'config/assets/ibov_assets.yaml'` | no | `-` | - |
| `--universe-file` | `universe_file` | `'config/universes/ibov.yaml'` | no | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator legacy migrate-universe --help`

### `python -m pymercator legacy scan`

- Classificacao: **LEGADO**
- Sintaxe: `python -m pymercator legacy scan [opcoes]`
- Quando usar: Inventrio e migracao de cdigo/dados legados.
- Quando nao usar: Nao use em operacao diaria.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--path` | `path` | `None` | yes | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator legacy scan --help`

### `python -m pymercator packs`

- Classificacao: **ÚTIL**
- Sintaxe: `python -m pymercator packs [opcoes]`
- Quando usar: Use quando precisar da utilidade indicada pelo help real.
- Quando nao usar: Nao use na rotina simplificada se um dos scripts principais cobre o fluxo.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--run-dir` | `run_dir` | `None` | yes | `-` | - |
| `--limit` | `limit` | `10` | no | `-` | - |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator packs --help`

### `python -m pymercator prices`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator prices [opcoes]`
- Quando usar: Buscar, validar ou criar templates de precos.
- Quando nao usar: Nao use sem conferir freshness quando for operar.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional
- Subcomandos reais: `check`, `fetch`, `fetch-list`, `tickers-check`, `tickers-template`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator prices --help`

### `python -m pymercator prices fetch`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator prices fetch [opcoes]`
- Quando usar: Buscar, validar ou criar templates de precos.
- Quando nao usar: Nao use sem conferir freshness quando for operar.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--tickers` | `tickers` | `''` | no | `-` | - |
| `--start` | `start` | `None` | yes | `-` | - |
| `--end` | `end` | `''` | no | `-` | - |
| `--no-cache` | `no_cache` | `False` | no | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator prices fetch --help`

### `python -m pymercator prices fetch-list`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator prices fetch-list [opcoes]`
- Quando usar: Buscar, validar ou criar templates de precos.
- Quando nao usar: Nao use sem conferir freshness quando for operar.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--tickers-file` | `tickers_file` | `None` | yes | `-` | - |
| `--start` | `start` | `None` | yes | `-` | - |
| `--end` | `end` | `''` | no | `-` | - |
| `--no-cache` | `no_cache` | `False` | no | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator prices fetch-list --help`

### `python -m pymercator prices tickers-template`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator prices tickers-template [opcoes]`
- Quando usar: Buscar, validar ou criar templates de precos.
- Quando nao usar: Nao use sem conferir freshness quando for operar.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator prices tickers-template --help`

### `python -m pymercator prices tickers-check`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator prices tickers-check [opcoes]`
- Quando usar: Buscar, validar ou criar templates de precos.
- Quando nao usar: Nao use sem conferir freshness quando for operar.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator prices tickers-check --help`

### `python -m pymercator prices check`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator prices check [opcoes]`
- Quando usar: Buscar, validar ou criar templates de precos.
- Quando nao usar: Nao use sem conferir freshness quando for operar.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--prices-dir` | `prices_dir` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator prices check --help`

### `python -m pymercator universe`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator universe [opcoes]`
- Quando usar: Diagnosticar, validar, montar ou resumir universo.
- Quando nao usar: Nao altera decisao final sozinho.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional
- Subcomandos reais: `build`, `check`, `diagnose`, `summary`, `template`

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--json` | `json` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator universe --help`

### `python -m pymercator universe check`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator universe check [opcoes]`
- Quando usar: Diagnosticar, validar, montar ou resumir universo.
- Quando nao usar: Nao altera decisao final sozinho.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator universe check --help`

### `python -m pymercator universe summary`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator universe summary [opcoes]`
- Quando usar: Diagnosticar, validar, montar ou resumir universo.
- Quando nao usar: Nao altera decisao final sozinho.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator universe summary --help`

### `python -m pymercator universe template`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator universe template [opcoes]`
- Quando usar: Diagnosticar, validar, montar ou resumir universo.
- Quando nao usar: Nao altera decisao final sozinho.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--output` | `output` | `None` | yes | `-` | - |

Exemplos:
- `python -m pymercator universe template --help`

### `python -m pymercator universe build`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator universe build [opcoes]`
- Quando usar: Diagnosticar, validar, montar ou resumir universo.
- Quando nao usar: Nao altera decisao final sozinho.
- Arquivos lidos: ver opcoes do comando
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--prices-dir` | `prices_dir` | `None` | yes | `-` | - |
| `--output` | `output` | `None` | yes | `-` | - |
| `--sentiment-dir` | `sentiment_dir` | `''` | no | `-` | - |
| `--tickers-file` | `tickers_file` | `''` | no | `-` | - |

Exemplos:
- `python -m pymercator universe build --help`

### `python -m pymercator universe diagnose`

- Classificacao: **DIAGNÓSTICO**
- Sintaxe: `python -m pymercator universe diagnose [opcoes]`
- Quando usar: Diagnosticar, validar, montar ou resumir universo.
- Quando nao usar: Nao altera decisao final sozinho.
- Arquivos lidos: config/policy.json
- Arquivos gerados: terminal/JSON opcional

| Opcao/posicional | Destino | Default | Obrigatorio | Choices | Help |
| --- | --- | --- | --- | --- | --- |
| `--file` | `file` | `None` | yes | `-` | - |
| `--policy` | `policy` | `'config/policy.json'` | no | `-` | - |
| `--details` | `details` | `False` | no | `-` | - |

Exemplos:
- `python -m pymercator universe diagnose --help`

## Defaults simplificados atuais

- `python -m pymercator run` equivale a `run --profile CON --basket --list IBOV`; use `--no-basket` para desligar o basket.
- `python -m pymercator train` le `config/prediction.json` e usa horizons/base_engines/weights/calibration de config.
- `python -m pymercator observe` defaulta `--list IBOV`.
- `python -m pymercator basket show` defaulta `storage/baskets/latest_daily_basket.csv`.

## Comandos que deveriam virar defaults

Status desta revisao:

- `train` ja usa `config/prediction.json` completo.
- `run` ja defaulta profile CON, list IBOV e basket ligado.
- `observe` ja defaulta list IBOV.
- `basket show` ja defaulta latest basket.
- Candidatos futuros: `context sources` pode virar parte padrao do fechamento diario; `borrow show` pode defaultar o arquivo de borrow mais recente quando houver historico versionado.

## Comandos redundantes ou candidatos a remocao

- `daily` duplica parte de `run` e scripts operacionais; candidato a REMOVER/UNIFICAR.
- `daily-real` e `real-pack` se sobrepoem; manter um caminho principal.
- `scenario-pack` se sobrepoe ao ecossistema `scenario`; manter como compatibilidade ate migrar docs/tests.
- `lab` duplica `predict lab` como atalho; classificar como avancado.
- `cfg`, `board` e `open` sao atalhos de desenvolvimento; nao entram na rotina operacional.
- `indices check` e `indices catalog` sao proximos; podem ser unificados futuramente.
- Scripts em `scripts/legacy` sao LEGADO e preservados apenas para auditoria/historia.

## Observacoes operacionais

- JSON/CSV/TXT/log/manifest devem permanecer sem ANSI. Cor e apenas terminal.
- Basket e analysis-only; nao executa ordem.
- Observation nao e compra.
- Short setup nao e venda automatica; falta de borrow/cost bloqueia execucao e nao esconde setup.
- Scenario positive e validacao sintetica, nao recomendacao de mercado real.
