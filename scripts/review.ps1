param(
    [string]$Profile = "CON",
    [string]$List = "IBOV"
)

$ErrorActionPreference = "Stop"

python -m pymercator review run --profile $Profile --list $List
exit $LASTEXITCODE
