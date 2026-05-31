# pyMercator

Sistema de autorizacao operacional para mercado financeiro.

O pyMercator nao e um robo de trade. Ele e um sistema de decisao em camadas:

1. Market Regime
2. Universe Health
3. Asset Ranking
4. Trade Validation
5. Execution Permission
6. Human Confirmation

## Filosofia

O sistema nao procura "compras". Ele avalia se um risco pode ser autorizado.

## Estados principais

- READY: candidato operacional, ainda exige confirmacao humana.
- WATCH: candidato interessante, mas sem autorizacao operacional.
- BLOCKED: operacao vetada.
- MANUAL_ONLY: apenas excecao manual documentada.
- INVALID: dados insuficientes ou inconsistentes.

## Primeira execucao

```powershell
python -m pip install -e .
python -m pymercator daily `
  --universe data\universes\ibov_sample.csv `
  --headline-risk ACTIVE `
  --headline-tags IRAN,OIL,WAR `
  --profile AGR
```

## Rotina oficial

```powershell
python -m pymercator update --list IBOV
python -m pymercator train
python -m pymercator run --profile CON --basket
```

Os comandos internos continuam disponiveis para diagnostico e operacoes pontuais.
O treino e baseado no dataset e nao depende de perfil operacional.
Perfis como `CON` e `AGR` sao aplicados no `run`, junto com politica, risco, filtros e execucao.
Por default, `train` executa o ensemble multi-horizonte parametrizado em
`config/prediction.json`: D5, D20 e D60; base engines `extratrees`,
`randomforest` e `gradientboosting`; meta-modelo `ridge`; observador ponderado.
O arquivo `storage/prediction/latest_evaluation.json` aponta para a avaliacao
final `multi_horizon_ridge`.

Bibliotecas instaladas aparecem no `diag`; engines validas aparecem no help do
`predict lab` e as engines/base engines do treino aparecem no help do `train`.
