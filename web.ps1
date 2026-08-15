# Compatibility wrapper: the recommended entry point is `cloudra` itself.
param(
    [switch]$Browser,
    [switch]$SkipBuild,
    [switch]$Rebuild
)
$ErrorActionPreference = "Stop"
$Python = if ($env:CLOUDRA_PYTHON) { $env:CLOUDRA_PYTHON } else { "python" }
$Args = @("web")
if ($Browser) { $Args += "--browser" }
if ($SkipBuild) { $Args += "--skip-build" }
if ($Rebuild) { $Args += "--rebuild" }
& $Python -m cloudra @Args
exit $LASTEXITCODE
