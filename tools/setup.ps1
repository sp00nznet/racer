<#
Star Wars Episode I: Racer recomp setup: from a plain download to a launcher, using your own ROM.

    Setup.cmd                                   double-click; asks before installing anything
    powershell -File tools\setup.ps1 -Yes -Game "D:\roms"   no questions (recomp-launcher uses this)
    ... -Targets pc,android,linux-arm64                   also build for other machines, in Docker

Targets: pc (this computer, the default) and the builds in scripts\targets.tsv, which
tools\setup-builds.ps1 makes after this computer's. Only the picked ones' toolchains are downloaded.

It runs the README's Building steps, skips the ones already done (so a rerun after a failure
resumes), and logs everything to logs\setup.log. The ROM stays on this machine: it's copied into the
repo folder as baserom.z64 (gitignored) and recompiled here. Nothing from the game is downloaded.
#>
param(
    [switch]$Yes,          # install missing prerequisites without asking
    [string]$Game = "",    # folder holding the ROM (default: the repo folder)
    [string]$Targets = "pc" # comma-separated: pc and/or scripts\targets.tsv's ids
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$picked = @($Targets -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if (-not $picked) { $picked = @('pc') }
$others = @($picked | Where-Object { $_ -ne 'pc' })
# Only other machines: that's tools\setup-builds.ps1's job alone.
if ($picked -notcontains 'pc') {
    & (Join-Path $PSScriptRoot "setup-builds.ps1") -Yes:$Yes -Game $Game -Targets ($others -join ',')
    exit $LASTEXITCODE
}
# The toolkits' deepest source files sit ~150 characters below this folder, and the C++ compiler
# can't open paths past Windows' 260-character limit.
if ($Root.Length -gt 100) {
    Write-Host "Setup stopped: this folder's path is too long to build in ($($Root.Length) characters). Move it somewhere shorter, such as C:\Games\Racer, and run Setup again." -ForegroundColor Red
    exit 1
}
New-Item -ItemType Directory -Force logs, deps | Out-Null
$Log = Join-Path $Root "logs\setup.log"
"Racer recomp setup, $(Get-Date)" | Out-File $Log -Encoding utf8

# Toolkits: sp00nznet's forks, which carry the fixes Racer needs (README, Building).
$Toolkits = @(
    @{ Dir = "N64Recomp";        Repo = "https://github.com/sp00nznet/N64Recomp";        Ref = "main" },
    @{ Dir = "N64ModernRuntime"; Repo = "https://github.com/sp00nznet/N64ModernRuntime"; Ref = "main" },
    @{ Dir = "rt64";             Repo = "https://github.com/sp00nznet/rt64";             Ref = "main" }
)
$Title = "Star Wars Episode I Racer"
$Header = "STAR WARS EP1 RACER"   # ROM header name (0x20)
$Crc = "72F70398"                 # CRC1 (0x10), USA release
$Steps = 7

function Step($n, $what) { $line = "[$n/$Steps] $what"; Write-Host $line; $line | Out-File $Log -Append -Encoding utf8 }
function Stop-Setup($why) {
    Write-Host ""
    Write-Host "Setup stopped: $why" -ForegroundColor Red
    Write-Host "Details are in $Log"
    "Setup stopped: $why" | Out-File $Log -Append -Encoding utf8
    exit 1
}
# Runs a native command with its output in the log; stops with $why if it fails.
function Run($why, $exe, [string[]]$arguments) {
    "> $exe $($arguments -join ' ')" | Out-File $Log -Append -Encoding utf8
    # Windows PowerShell turns a native program's stderr into errors; only the exit code counts.
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $global:LASTEXITCODE = 0
    & $exe @arguments 2>&1 | ForEach-Object { "$_" } | Out-File $Log -Append -Encoding utf8
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($code -ne 0) { Stop-Setup $why }
}
function Ask($question) {
    if ($Yes) { return $true }
    return (Read-Host "$question [Y/n]") -notmatch '^[nN]'
}
function Refresh-Path {
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [Environment]::GetEnvironmentVariable("PATH", "User")
}
function Find-VS {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { return $null }
    return & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
}
# The ROM header: big-endian .z64 only (N64Recomp reads it as is).
function Read-Header($path) {
    $buf = New-Object byte[] 0x40
    $fs = [IO.File]::OpenRead($path)
    try { if ($fs.Read($buf, 0, 0x40) -lt 0x40) { return $null } } finally { $fs.Close() }
    return @{
        Name = [Text.Encoding]::ASCII.GetString($buf, 0x20, 19)
        Crc  = ($buf[0x10..0x13] | ForEach-Object { $_.ToString("X2") }) -join ""
    }
}

# ---------------------------------------------------------------------------------------------
Step 1 "Checking the tools it needs"
$need = @()
if (-not (Get-Command git -ErrorAction SilentlyContinue))   { $need += @{ Name = "Git"; Id = "Git.Git"; Size = "about 300 MB" } }
if (-not (Get-Command py -ErrorAction SilentlyContinue))    { $need += @{ Name = "Python 3"; Id = "Python.Python.3.12"; Size = "about 100 MB" } }
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) { $need += @{ Name = "CMake"; Id = "Kitware.CMake"; Size = "about 100 MB" } }
if (-not (Find-VS)) { $need += @{ Name = "Visual Studio 2022 Build Tools (C++)"; Id = "Microsoft.VisualStudio.2022.BuildTools"; Size = "about 3 GB";
    Extra = @("--override", "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive --wait") } }
foreach ($t in $need) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Stop-Setup "$($t.Name) is missing and winget isn't available to install it. Install $($t.Name) yourself, then run Setup again."
    }
    if (-not (Ask "$($t.Name) is needed to build the game and isn't installed. Install it with winget ($($t.Size))?")) {
        Stop-Setup "$($t.Name) is needed. Install it, then run Setup again."
    }
    $args_ = @("install", "--id", $t.Id, "-e", "--accept-source-agreements", "--accept-package-agreements") + $t.Extra
    Run "installing $($t.Name) failed" "winget" $args_
    Refresh-Path
}
if (-not (Find-VS)) { Stop-Setup "Visual Studio's C++ build tools didn't install. Install the 'Desktop development with C++' workload, then run Setup again." }

# ---------------------------------------------------------------------------------------------
Step 2 "Finding your ROM"
$target = Join-Path $Root "baserom.z64"
$match = $null
$searchDirs = @($Root) + $(if ($Game) { @($Game) } else { @() })
foreach ($dir in $searchDirs) {
    # The folder itself, then its direct subfolders (Windows PowerShell ignores -Depth with -Include).
    $files = @(Get-ChildItem -LiteralPath $dir -File -ErrorAction SilentlyContinue) +
             @(Get-ChildItem -LiteralPath $dir -Directory -ErrorAction SilentlyContinue | ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -File -ErrorAction SilentlyContinue })
    foreach ($f in $files | Where-Object { $_.Extension -in ".z64", ".n64", ".v64" }) {
        $h = Read-Header $f.FullName
        if (-not $h) { continue }
        if ($h.Name -eq $Header -and $h.Crc -eq $Crc) { $match = $f.FullName; break }
        # A byte-swapped dump (.v64/.n64) reads "TSRAW RA..." here.
        if ($h.Name.StartsWith("TSRAW RA")) { "  $($f.FullName): byte-swapped dump, skipped" | Out-File $Log -Append -Encoding utf8 }
    }
    if ($match) { break }
}
if (-not $match) {
    Stop-Setup "No Racer ROM found. Put your USA .z64 of Star Wars Episode I: Racer in this folder (or pass -Game <folder>), then run Setup again. Byte-swapped .v64/.n64 dumps need converting to .z64 first."
}
if ($match -ne $target) { Copy-Item -LiteralPath $match -Destination $target -Force }
Write-Host "  $match"

# ---------------------------------------------------------------------------------------------
Step 3 "Getting the recompiler, runtime and renderer"
foreach ($t in $Toolkits) {
    $dir = Join-Path "deps" $t.Dir
    if (Test-Path (Join-Path $dir ".git")) { continue }
    # core.longpaths: the toolkits' submodules have paths past Windows' 260-character limit.
    Run "downloading $($t.Dir) failed (no internet, or see the log)" "git" @("-c", "core.longpaths=true", "clone", "--recurse-submodules", "--branch", $t.Ref, $t.Repo, $dir)
}

# ---------------------------------------------------------------------------------------------
Step 4 "Building the recompiler"
$recomp = Join-Path $Root "deps\N64Recomp\build\Release\N64Recomp.exe"
$rsprecomp = Join-Path $Root "deps\N64Recomp\build\Release\RSPRecomp.exe"
if (-not (Test-Path $recomp) -or -not (Test-Path $rsprecomp)) {
    Run "configuring N64Recomp failed" "cmake" @("-S", "deps\N64Recomp", "-B", "deps\N64Recomp\build", "-G", "Visual Studio 17 2022", "-A", "x64")
    Run "building N64Recomp failed" "cmake" @("--build", "deps\N64Recomp\build", "--config", "Release", "--target", "N64RecompCLI", "RSPRecomp", "--parallel")
}

# ---------------------------------------------------------------------------------------------
Step 5 "Recompiling your game (a minute or two)"
# Redone whenever the recompiler's inputs change (an update to symbols.toml or recomp.toml).
$inputs = (Get-FileHash symbols.toml).Hash + (Get-FileHash recomp.toml).Hash + (Get-FileHash rsp\aspMain.toml).Hash
$stamp = "RecompiledFuncs\inputs.txt"
if (-not (Test-Path $stamp) -or (Get-Content $stamp) -ne $inputs -or -not (Test-Path "rsp\aspMain.cpp")) {
    if (Test-Path RecompiledFuncs) { Remove-Item -Recurse -Force RecompiledFuncs }
    New-Item -ItemType Directory RecompiledFuncs | Out-Null
    Run "recompiling failed" $recomp @("recomp.toml")
    Run "patching the recompiled code failed" "py" @("tools\fix_fallthroughs.py")
    Run "patching the recompiled code failed" "py" @("tools\post_recomp_patches.py")
    # The audio microcode (libultra's aspMain) runs as recompiled C++ too.
    Run "recompiling the audio microcode failed" $rsprecomp @("rsp\aspMain.toml")
    $inputs | Out-File $stamp -Encoding ascii -NoNewline
}

# ---------------------------------------------------------------------------------------------
Step 6 "Building (the first build takes 20 to 40 minutes)"
Run "configuring the game failed" "cmake" @("-S", ".", "-B", "build", "-G", "Visual Studio 17 2022", "-A", "x64")
Run "building the game failed" "cmake" @("--build", "build", "--config", "RelWithDebInfo", "--target", "SWE1Racer", "--parallel")

# ---------------------------------------------------------------------------------------------
Step 7 "Making the launcher"
# The exe won't start without these next to it (the build copies them; make sure).
$bin = Join-Path $Root "build\RelWithDebInfo"
$dlls = @{ "SDL2.dll" = "deps\rt64\src\contrib\mupen64plus-win32-deps\SDL2-2.26.3\lib\x64\SDL2.dll";
           "dxil.dll" = "deps\rt64\src\contrib\dxc\bin\x64\dxil.dll"; "dxcompiler.dll" = "deps\rt64\src\contrib\dxc\bin\x64\dxcompiler.dll" }
foreach ($d in $dlls.Keys) {
    if (-not (Test-Path -LiteralPath (Join-Path $bin $d))) { Copy-Item -LiteralPath (Join-Path $Root $dlls[$d]) -Destination $bin }
    if (-not (Test-Path -LiteralPath (Join-Path $bin $d))) { Stop-Setup "$d is missing next to the game, and copying it failed." }
}
# Cheats (Settings > Cheats) read a Project64 .cht code list; use Project64's if it's installed.
$cht = Join-Path $bin "cheats.cht"
$pj64 = Get-ChildItem "${env:ProgramFiles(x86)}\Project64*\Config\Cheats", "$env:ProgramFiles\Project64*\Config\Cheats" -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "Star Wars Episode I - Racer (U).cht" } | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not (Test-Path -LiteralPath $cht) -and $pj64) { Copy-Item -LiteralPath $pj64 -Destination $cht }
$launcher = Join-Path $Root "$Title (recomp).cmd"
"@echo off`r`ncd /d `"%~dp0`"`r`nstart `"`" `"build\RelWithDebInfo\SWE1Racer.exe`" %*`r`n" | Out-File $launcher -Encoding ascii
Write-Host "  $Title (recomp).cmd"
Write-Host ""
Write-Host "Done. Double-click the launcher above to play."
if ($others) {
    Write-Host ""
    & (Join-Path $PSScriptRoot "setup-builds.ps1") -Yes:$Yes -Game $Game -Targets ($others -join ',')
    exit $LASTEXITCODE
}
