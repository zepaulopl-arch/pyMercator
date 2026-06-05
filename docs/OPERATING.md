# pyMercator Operating Guide

## Rotina simples

Dia normal:

```powershell
.\scripts\run_daily_signal.ps1
```

Treino eventual:

```powershell
.\scripts\run_daily_train.ps1
```

Fim de semana:

```powershell
.\scripts\run_weekend_full.ps1
```

## Diagnostico

```powershell
python -m pymercator diag
python -m pymercator context sources
python -m pytest tests -q
```

## Regra operacional

O operador precisa decorar apenas os tres scripts principais. Os comandos CLI
continuam disponiveis para diagnostico, desenvolvimento, auditoria e casos
avancados, mas nao substituem a rotina simplificada.
