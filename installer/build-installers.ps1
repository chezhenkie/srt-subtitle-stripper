# Builds the two per-user Windows setup executables from released binaries.
# Input: srtstripper-windows-x86_64.exe and srtstripper-windows-aarch64.exe.
# ASCII only; Inno Setup 6.3 or newer is required for the arm64 identifier.

[CmdletBinding()]
param(
    [string]$DistDir,
    [string]$OutDir,
    [string]$Version,
    [string]$Iscc,
    [string]$Arch
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

if (-not $Version) {
    $match = Select-String -Path (Join-Path $root 'srtstripper\Cargo.toml') -Pattern '^version = "(.+)"$'
    if (-not $match) { throw 'cannot read version from srtstripper/Cargo.toml' }
    $Version = $match.Matches[0].Groups[1].Value
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "version must be numeric x.y.z for the setup metadata: $Version"
}

if (-not $DistDir) { $DistDir = Join-Path $root "releases\v$Version" }
if (-not $OutDir) { $OutDir = Join-Path $root '_scratch\installers' }
$DistDir = [IO.Path]::GetFullPath($DistDir).TrimEnd('\')
$OutDir = [IO.Path]::GetFullPath($OutDir).TrimEnd('\')
if (-not (Test-Path -LiteralPath $DistDir)) { throw "dist dir not found: $DistDir" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

if (-not $Iscc) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )
    $Iscc = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $Iscc -or -not (Test-Path -LiteralPath $Iscc)) {
    throw 'ISCC.exe not found: pass -Iscc <path> or install Inno Setup 6'
}

$script = Join-Path $PSScriptRoot 'srtstripper.iss'
$archs = @(
    @{ Name = 'x86_64'; Exe = 'srtstripper-windows-x86_64.exe' },
    @{ Name = 'aarch64'; Exe = 'srtstripper-windows-aarch64.exe' }
)
if ($Arch) {
    $filtered = @($archs | Where-Object { $_.Name -eq $Arch })
    if ($filtered.Count -ne 1) { throw "unknown -Arch value: $Arch (expected x86_64 or aarch64)" }
    $archs = $filtered
}

for ($i = 0; $i -lt $archs.Count; $i++) {
    $arch = $archs[$i]
    $input = Join-Path $DistDir $arch.Exe
    if (-not (Test-Path -LiteralPath $input)) { throw "missing input: $input" }
    $inputVersion = (Get-Item -LiteralPath $input).VersionInfo.FileVersion.Trim()
    if ($inputVersion -ne "$Version.0") {
        throw "input version mismatch: $input has $inputVersion, expected $Version.0"
    }
    $output = Join-Path $OutDir "srtstripper-windows-$($arch.Name)-setup.exe"
    if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Force }

    & $Iscc "/DAppVersion=$Version" "/DArch=$($arch.Name)" "/DDistDir=$DistDir" "/DOutDir=$OutDir" $script
    if ($LASTEXITCODE -ne 0) { throw "ISCC failed for $($arch.Name), exit $LASTEXITCODE" }
    if (-not (Test-Path -LiteralPath $output)) { throw "setup not produced: $output" }
    $setupVersion = (Get-Item -LiteralPath $output).VersionInfo
    $setupFile = $setupVersion.FileVersion.Trim()
    $setupProduct = $setupVersion.ProductVersion.Trim()
    if ($setupFile -ne "$Version.0" -or $setupProduct -ne "$Version.0") {
        throw "setup version mismatch: file=$setupFile product=$setupProduct expected=$Version.0"
    }
    Write-Output "built $output"
}
