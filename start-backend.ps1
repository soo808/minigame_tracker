# Free port 8000 then start API (run from repo root: .\start-backend.ps1)
#
# 默认监听 0.0.0.0:8000，同事在同一局域网可用 http://<你的IPv4>:8000/minigame-tracker/?platform=wx
# 查 IPv4：ipconfig。勿发 localhost/127.0.0.1 给对方（那会连到对方自己电脑）。
# 若同事访问不通：在本机放行入站 TCP 8000，例如（管理员 PowerShell）：
#   New-NetFirewallRule -DisplayName "Minigame Tracker 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
# 仅本机调试时可在当前会话设置： $env:UVICORN_HOST="127.0.0.1"

$bindHost = if ($env:UVICORN_HOST) { $env:UVICORN_HOST } else { "0.0.0.0" }

$listeners = @(
    Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
)
$procIds = $listeners | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ }
foreach ($procId in $procIds) {
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 600
Set-Location $PSScriptRoot
python -m uvicorn backend.main:app --host $bindHost --port 8000
