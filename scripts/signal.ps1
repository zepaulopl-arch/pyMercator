param(
    [string]$Profile = "CON",
    [int]$Top = 10,
    [string]$List = "IBOV",
    [switch]$Basket
)

$ErrorActionPreference = "Stop"

$cmd = @(
    "-m", "pymercator",
    "signal", "run",
    "--profile", $Profile,
    "--top", "$Top",
    "--list", $List
)

if ($Basket) {
    $cmd += "--basket"
}

python @cmd
exit $LASTEXITCODE
