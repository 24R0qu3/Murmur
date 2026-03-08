# install.ps1 — download and install murmur from the latest GitHub release.
# Usage (PowerShell):
#   irm https://raw.githubusercontent.com/24R0qu3/Murmur/main/install.ps1 | iex
#   # or with a custom install location:
#   $env:INSTALL_DIR = "C:\Tools"; irm .../install.ps1 | iex
$ErrorActionPreference = "Stop"

$Repo       = "24R0qu3/Murmur"
$BinName    = "murmur"
$Artifact   = "murmur-windows-x86_64.exe"
$InstallDir = if ($env:INSTALL_DIR) { $env:INSTALL_DIR } `
              else { Join-Path $env:LOCALAPPDATA "Programs\murmur" }

# ── Resolve latest release tag ───────────────────────────────────────────────
Write-Host "Fetching latest release info..."
$Release = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest"
$Tag     = $Release.tag_name

if (-not $Tag) {
    Write-Error "Could not determine latest release tag."
    exit 1
}

# ── Download binary ──────────────────────────────────────────────────────────
$Url  = "https://github.com/$Repo/releases/download/$Tag/$Artifact"
$Dest = Join-Path $InstallDir "$BinName.exe"

Write-Host "Downloading $BinName $Tag..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Invoke-WebRequest -Uri $Url -OutFile $Dest

Write-Host "Installed to $Dest"

# ── Add to user PATH if not already present ──────────────────────────────────
$UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if (-not $UserPath) { $UserPath = "" }
if ($UserPath -notlike "*$InstallDir*") {
    $NewPath = ($InstallDir + ";" + $UserPath.TrimStart(";")).TrimEnd(";")
    [Environment]::SetEnvironmentVariable("PATH", $NewPath, "User")
    Write-Host ""
    Write-Host "  Added $InstallDir to your PATH."
    Write-Host "  Restart your terminal for it to take effect."
}

Write-Host ""
Write-Host "Done. Run: $BinName"
