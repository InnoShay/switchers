# RoomService setup for Windows. Idempotent: safe to run twice.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Workspace = Join-Path $HOME "roomservice-workspace"
$Volt = Join-Path $Workspace "projects\volt"
$fail = $false

function Ok($m)   { Write-Host "  OK   $m" }
function Bad($m)   { Write-Host "  FAIL $m"; $script:fail = $true }
function Warn($m)  { Write-Host "  WARN $m" }

Write-Host "== Checks"
if (Get-Command uv -ErrorAction SilentlyContinue) { Ok "uv" } else { Bad "uv missing: winget install astral-sh.uv" }
if (Get-Command node -ErrorAction SilentlyContinue) {
  $major = [int]((node -v) -replace '^v(\d+).*', '$1')
  if ($major -ge 20) { Ok "node $(node -v)" } else { Bad "node $(node -v) is older than 20: winget install OpenJS.NodeJS" }
} else { Bad "node missing: winget install OpenJS.NodeJS" }
if (Get-Command npm -ErrorAction SilentlyContinue) { Ok "npm" } else { Bad "npm missing" }
if (Get-Command git -ErrorAction SilentlyContinue) { Ok "git" } else { Bad "git missing: winget install Git.Git" }
docker info *> $null
if ($LASTEXITCODE -eq 0) { Ok "Docker running" } else { Bad "Docker is not running: open Docker Desktop" }
if (Get-Command code -ErrorAction SilentlyContinue) { Ok "code CLI" } else { Warn "code CLI missing: in VS Code run 'Shell Command: Install code command in PATH'" }
if ($fail) { Write-Host "Fix the FAIL items above and run this script again."; exit 1 }

Write-Host "== Workspace"
foreach ($d in "concierge", "scout", "projects") { New-Item -ItemType Directory -Force -Path (Join-Path $Workspace $d) | Out-Null }
Ok $Workspace

if (-not (Test-Path $Volt)) {
  Copy-Item -Recurse (Join-Path $Root "demo\volt") $Volt
  Ok "copied demo\volt to $Volt"
} else { Ok "$Volt already exists (left as is)" }
Push-Location $Volt
npm install --no-audit --no-fund | Out-Null
Ok "npm install in volt"
if (-not (Test-Path ".git")) {
  git init -q -b main
  git config user.name "RoomService"
  git config user.email "roomservice@local"
  "node_modules/`ndist/" | Set-Content -Path ".gitignore"
  git add -A
  git commit -q -m "Initial commit"
  Ok "git init + initial commit in volt"
} else { Ok "volt is already a git repo" }
Pop-Location

Write-Host "== RoomService"
Set-Location $Root
if (-not (Test-Path "config\desk.yaml")) { Copy-Item "config\desk.example.yaml" "config\desk.yaml" }
Ok "config\desk.yaml"
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
Ok ".env (fill in SWITCH_URL and SWITCH_REGISTRATION_KEY)"
uv sync | Out-Null
Ok "uv sync"
uv run playwright install chromium | Out-Null
Ok "playwright chromium"

Write-Host ""
Write-Host "Then: uv run roomservice doctor"
