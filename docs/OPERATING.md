# pyMercator Operating Guide

## Rotina simples

Dia normal:

```powershell
.\scripts\signal.ps1
```

Fim da tarde:

```powershell
.\scripts\review.ps1
```

Treino eventual:

```powershell
.\scripts\train.ps1
```

Fim de semana:

```powershell
.\scripts\weekend.ps1
```

## Diagnostico

```powershell
python -m pymercator diag
python -m pymercator context sources
python -m pymercator mtm --run-dir runtime\daily_signal_<timestamp> --capital 10000
python -m pymercator db status
python -m pymercator db last-run
python -m pytest tests -q
```

## Regra operacional

O operador precisa decorar apenas os scripts de rotina. Os comandos CLI
continuam disponiveis para diagnostico, desenvolvimento, auditoria e casos
avancados, mas nao substituem a rotina simplificada.
