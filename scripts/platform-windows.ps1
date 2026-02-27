param(
    [Parameter(Mandatory = $false, Position = 0)]
    [string]$Action
)

$ValidActions = @("start", "stop", "restart", "local-start", "local-stop")

function Show-Usage {
    Write-Host "用法: .\scripts\platform-windows.ps1 {start|stop|restart|local-start|local-stop}"
}

if ([string]::IsNullOrWhiteSpace($Action) -or -not ($ValidActions -contains $Action)) {
    Show-Usage
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BashScriptPath = Join-Path $ScriptDir "platform-linux.sh"

if (-not (Test-Path -Path $BashScriptPath -PathType Leaf)) {
    Write-Host "未找到 bash 入口脚本: $BashScriptPath"
    exit 1
}

$BashCommand = Get-Command bash -ErrorAction SilentlyContinue
$WslCommand = Get-Command wsl -ErrorAction SilentlyContinue

if ($BashCommand) {
    & $BashCommand.Source $BashScriptPath $Action
    exit $LASTEXITCODE
}

if ($WslCommand) {
    $ResolvedScriptPath = (Resolve-Path -Path $BashScriptPath).Path
    $UnixScriptPath = $ResolvedScriptPath -replace "\\", "/"
    if ($UnixScriptPath -match "^[A-Za-z]:") {
        $Drive = $UnixScriptPath.Substring(0, 1).ToLower()
        $Rest = $UnixScriptPath.Substring(2)
        $UnixScriptPath = "/mnt/$Drive$Rest"
    }
    & $WslCommand.Source bash $UnixScriptPath $Action
    exit $LASTEXITCODE
}

Write-Host "未检测到可用的 bash 环境。请先安装并配置 WSL 或 Git Bash。"
Show-Usage
exit 1
