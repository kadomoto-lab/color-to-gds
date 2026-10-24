param(
    [int]$Port = 8765,
    [string]$Distribution = 'Ubuntu',
    # Linux path of the clone inside WSL; defaults to ~/color-to-gds of the WSL user.
    [string]$RepositoryPath = ''
)
$ErrorActionPreference = 'Stop'
if (-not $RepositoryPath) { $RepositoryPath = ((wsl.exe -d $Distribution --exec sh -c 'printf %s "$HOME"') -join '') + '/color-to-gds' }
$studioUrl = "http://127.0.0.1:$Port"
try { $running = (Invoke-WebRequest -Uri $studioUrl -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { $running = $false }
if (-not $running) {
    Start-Process -FilePath 'wsl.exe' -WindowStyle Hidden -ArgumentList @('-d', $Distribution, '--exec', ('"' + $RepositoryPath + '/.venv/bin/python"'), ('"' + $RepositoryPath + '/run_web.py"'), '--port', "$Port")
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Seconds 1
        try { if ((Invoke-WebRequest -Uri $studioUrl -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) { $running = $true; break } } catch { }
    }
    if (-not $running) { throw '起動を確認できません。WSLで uv run run_web.py を実行してログを確認してください。' }
}
Write-Output "Color2GDS Studio: $studioUrl"
