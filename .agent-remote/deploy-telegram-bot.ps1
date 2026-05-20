param(
    [string]$ServerHost = "193.168.196.12",
    [string]$User = "root",
    [string]$KeyPath = "C:\Users\User\.ssh\alexklyvibe",
    [string]$RemoteDir = "/opt/LightRAG"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[deploy-telegram-bot] $Message" -ForegroundColor Cyan
}

if (-not (Test-Path -Path $KeyPath)) {
    throw "SSH key not found: $KeyPath"
}

$localBotDir = Join-Path $PSScriptRoot "..\telegram_bot"
$localCompose = Join-Path $PSScriptRoot "docker-compose.telegram-bot.yml"

if (-not (Test-Path -Path $localBotDir)) {
    throw "Local bot directory not found: $localBotDir"
}
if (-not (Test-Path -Path $localCompose)) {
    throw "Compose overlay not found: $localCompose"
}

$target = "$User@$ServerHost"
Write-Step "Sync bot sources to ${target}:$RemoteDir"
ssh -i $KeyPath $target "mkdir -p $RemoteDir/telegram_bot"
scp -i $KeyPath -r "$localBotDir" "${target}:$RemoteDir/"
scp -i $KeyPath "$localCompose" "${target}:$RemoteDir/docker-compose.telegram-bot.yml"

Write-Step "Validate TELEGRAM_BOT_TOKEN in $RemoteDir/.env"
$tokenLine = ssh -i $KeyPath $target "grep '^TELEGRAM_BOT_TOKEN=' $RemoteDir/.env || true"
if ([string]::IsNullOrWhiteSpace($tokenLine)) {
    throw "MISSING_TELEGRAM_BOT_TOKEN in $RemoteDir/.env"
}
$tokenValue = $tokenLine -replace '^TELEGRAM_BOT_TOKEN=', ''
if ([string]::IsNullOrWhiteSpace($tokenValue)) {
    throw "EMPTY_TELEGRAM_BOT_TOKEN in $RemoteDir/.env"
}

Write-Step "Build and start telegram-bot container on server"
$deployCommand = @"
set -e
cd $RemoteDir
docker compose -f docker-compose.yml -f docker-compose.telegram-bot.yml up -d --build --force-recreate telegram-bot
docker compose -f docker-compose.yml -f docker-compose.telegram-bot.yml ps telegram-bot
"@
ssh -i $KeyPath $target $deployCommand

Write-Step "Done"

