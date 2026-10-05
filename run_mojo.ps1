# Run the project-owned Pixi tasks inside WSL.
param([switch]$Test)
$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot -replace '\\', '/'
$linuxPath = (& wsl --exec wslpath -a -u $projectPath)
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the project folder inside WSL.' }
$launcherArgs = @()
if ($Test) { $launcherArgs += '--test' }
& wsl --cd $linuxPath.Trim() --exec bash ./run_mojo.sh @launcherArgs
exit $LASTEXITCODE
