\# pyMercator



Sistema de autorização operacional para mercado financeiro.



O pyMercator não é um robô de trade. Ele é um sistema de decisão em camadas:



1\. Market Regime

2\. Universe Health

3\. Asset Ranking

4\. Trade Validation

5\. Execution Permission

6\. Human Confirmation



\## Filosofia



O sistema não procura "compras". Ele avalia se um risco pode ser autorizado.



\## Estados principais



\- READY: candidato operacional, ainda exige confirmação humana.

\- WATCH: candidato interessante, mas sem autorização operacional.

\- BLOCKED: operação vetada.

\- MANUAL\_ONLY: apenas exceção manual documentada.

\- INVALID: dados insuficientes ou inconsistentes.



\## Primeira execução



```powershell

python -m pip install -e .

python -m pymercator daily --universe data\\universes\\ibov\_sample.csv --headline-risk ACTIVE --headline-tags IRAN,OIL,WAR --profile AGR

