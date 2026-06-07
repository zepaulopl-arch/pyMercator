param(
    [switch]$Details
)

$ErrorActionPreference = "Stop"

$cmd = @("-m", "pymercator", "train", "run")

if ($Details) {
    $cmd += "--details"
}

python @cmd
exit $LASTEXITCODE
