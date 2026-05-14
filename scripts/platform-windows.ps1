param(
    [Parameter(Mandatory = $false, Position = 0)]
    [string]$Action,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ValidActions = @(
    "ui", "start", "stop", "restart", "status", "health",
    "local-start", "local-stop",
    "docker-start", "docker-full-start", "docker-stop", "docker-restart", "docker-status",
    "configure", "doctor", "config-status"
)

function Show-Usage {
    Write-Host "用法: .\scripts\platform-windows.ps1 {ui|start|stop|restart|status|health|local-start|local-stop|docker-start|docker-full-start|docker-stop|docker-restart|docker-status|configure|doctor|config-status} [extra args...]"
}

if ([string]::IsNullOrWhiteSpace($Action) -or -not ($ValidActions -contains $Action)) {
    Show-Usage
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent $ScriptDir

if ($Action -eq "ui" -or $Action -eq "configure") {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        $PythonCommand = Get-Command python3 -ErrorAction SilentlyContinue
    }
    if (-not $PythonCommand) {
        Write-Host "未检测到 Python。请先安装 Python 3。"
        exit 1
    }
    & $PythonCommand.Source (Join-Path $ScriptDir "launch.py") @ExtraArgs
    exit $LASTEXITCODE
}

$BashScriptPath = Join-Path $ScriptDir "platform-linux.sh"

if (-not (Test-Path -Path $BashScriptPath -PathType Leaf)) {
    Write-Host "未找到 bash 入口脚本: $BashScriptPath"
    exit 1
}

$BashCommand = Get-Command bash -ErrorAction SilentlyContinue
$WslCommand = Get-Command wsl -ErrorAction SilentlyContinue

if ($BashCommand) {
    & $BashCommand.Source $BashScriptPath $Action @ExtraArgs
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
    & $WslCommand.Source bash $UnixScriptPath $Action @ExtraArgs
    exit $LASTEXITCODE
}

Write-Host "未检测到可用的 bash 环境。请先安装并配置 WSL 或 Git Bash。"
Show-Usage
exit 1
