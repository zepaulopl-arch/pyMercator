param(
    [switch]$NoAutotune
)

$ErrorActionPreference = "Stop"

$cmd = @("-m", "pymercator", "weekend", "run")

if ($NoAutotune) {
    $cmd += "--no-autotune"
}

python @cmd
exit $LASTEXITCODE
