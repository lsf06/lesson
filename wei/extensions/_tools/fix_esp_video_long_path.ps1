<#
.SYNOPSIS
    Installs espressif/esp_video through a short-path directory junction so the
    ESP-IDF Component Manager does not fail on the Windows MAX_PATH (260 character)
    limit inside this (deeply nested) repository.

.DESCRIPTION
    The Component Manager copies every dependency from its cache into
    <project>\managed_components\<component>. For this repository that destination
    prefix is already ~132 characters long:

        E:\study\...\esi-mvp-code-main\extensions\03_catdog_static_infer\managed_components\

    espressif/esp_video ships paths that are up to ~150 characters long, so the copy
    raises a Windows path-too-long error, leaves a half-written directory behind and
    never writes the .component_hash marker file. On the next build the manager sees
    "espressif__esp_video does not exist or ..." and the build fails.

    This script performs the installation by hand, once:

      1. reads the expected component hash from the project's dependencies.lock,
      2. copies the component out of the Component Manager cache into a short
         directory (<ShortRoot>\<hash8>),
      3. writes the .component_hash marker file the manager compares against the lock,
      4. turns <project>\managed_components\espressif__esp_video into a directory
         junction pointing at that short directory.

    The manager then treats the component as already installed
    (IDF_COMPONENT_STRICT_CHECKSUM defaults to False + matching hash file) and never
    copies it again, while the ESP-IDF build compiles the sources through the junction.

    The script is idempotent: projects that already have a valid install are skipped,
    and it never touches a managed_components entry that is already complete.

.PARAMETER Project
    Project directories to fix. Defaults to the two cat/dog demo projects next to this
    script (03_catdog_static_infer and 03_live_catdog_assignment).

.PARAMETER ShortRoot
    Short directory that holds the real component files.
    Default: %USERPROFILE%\ev_video_component

.PARAMETER Force
    Re-create the junction even if it already exists.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\_tools\fix_esp_video_long_path.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\_tools\fix_esp_video_long_path.ps1 `
        -Project ..\03_catdog_static_infer -ShortRoot C:\ev
#>
[CmdletBinding()]
param(
    [string[]]$Project,
    [string]$ShortRoot = (Join-Path $env:USERPROFILE 'ev_video_component'),
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ComponentName = 'espressif/esp_video'
$ComponentDirName = 'espressif__esp_video'

if (-not $Project -or $Project.Count -eq 0) {
    $Project = @(
        (Join-Path $PSScriptRoot '..\03_catdog_static_infer'),
        (Join-Path $PSScriptRoot '..\03_live_catdog_assignment')
    )
}

# ---------------------------------------------------------------- long path state
$longPathsEnabled = $false
try {
    $reg = Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' `
        -Name 'LongPathsEnabled' -ErrorAction SilentlyContinue
    if ($reg -and $reg.LongPathsEnabled -eq 1) { $longPathsEnabled = $true }
} catch {
    $longPathsEnabled = $false
}
if ($longPathsEnabled) {
    Write-Warning ('LongPathsEnabled=1 is set in the registry. If the toolchain is also ' +
        'long-path aware the workaround is unnecessary, but it stays harmless.')
}

# ------------------------------------------------------------ component-manager cache
$cacheRoot = Join-Path $env:LOCALAPPDATA 'Espressif\ComponentManager\Cache'
if (-not (Test-Path $cacheRoot)) {
    throw "Component Manager cache not found: $cacheRoot (run a build once so the manager downloads its dependencies)"
}
$cacheDirs = Get-ChildItem $cacheRoot -Directory |
    ForEach-Object { Get-ChildItem $_.FullName -Directory -Filter "$ComponentDirName`_*" }
if (-not $cacheDirs) {
    throw "No $ComponentDirName entry in $cacheRoot (run a build once so the manager downloads it)"
}

function Get-ExpectedHash {
    param([string]$ProjectDir)
    $lock = Join-Path $ProjectDir 'dependencies.lock'
    if (-not (Test-Path $lock)) { return $null }
    $text = Get-Content -LiteralPath $lock -Raw
    $pattern = "(?ms)^\s{2}$([regex]::Escape($ComponentName)):\s*\r?\n.*?component_hash:\s*([0-9a-fA-F]{64})"
    $match = [regex]::Match($text, $pattern)
    if ($match.Success) { return $match.Groups[1].Value.ToLowerInvariant() }
    return $null
}

function Get-CacheDir {
    param([string]$Hash)
    # the manager names cache directories <component>_<version>_<first 8 hash chars>
    return ($cacheDirs | Where-Object { $_.Name -like "*_$($Hash.Substring(0, 8))" } |
        Select-Object -First 1)
}

$summary = New-Object System.Collections.Generic.List[string]

foreach ($raw in $Project) {
    $projectDir = [System.IO.Path]::GetFullPath($raw)
    $name = Split-Path $projectDir -Leaf

    if (-not (Test-Path $projectDir)) {
        $summary.Add("SKIP  $name : directory not found ($projectDir)")
        continue
    }

    $expected = Get-ExpectedHash -ProjectDir $projectDir
    if (-not $expected) {
        $summary.Add("SKIP  $name : no $ComponentName entry in dependencies.lock")
        continue
    }

    $managed = Join-Path $projectDir 'managed_components'
    $link = Join-Path $managed $ComponentDirName

    # ---- already installed (junction from an earlier run or a real CM install)?
    if (Test-Path $link) {
        $hashFile = Join-Path $link '.component_hash'
        $isJunction = ((Get-Item -LiteralPath $link -Force).Attributes -band
            [System.IO.FileAttributes]::ReparsePoint) -ne 0
        $hashMatches = (Test-Path $hashFile) -and
            ((Get-Content -LiteralPath $hashFile -Raw).Trim() -eq $expected)
        if ($hashMatches -and -not $Force) {
            $kind = if ($isJunction) { 'junction' } else { 'directory' }
            $summary.Add("OK    $name : already installed ($kind, hash matches)")
            continue
        }
        Write-Host "  $name : re-creating $link (hash missing or stale)"
        Remove-Item -LiteralPath $link -Recurse -Force
    }

    $cacheDir = Get-CacheDir -Hash $expected
    if (-not $cacheDir) {
        $summary.Add("FAIL  $name : no cache entry for $ComponentName (hash $expected)")
        continue
    }

    # ---- real files live in a short directory, one sub-directory per component hash
    $target = Join-Path $ShortRoot $expected.Substring(0, 8)
    if (-not (Test-Path $target)) {
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        $rc = Start-Process robocopy -Wait -PassThru -WindowStyle Hidden -ArgumentList @(
            "`"$($cacheDir.FullName)`"", "`"$target`"", '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NP'
        )
        if ($rc.ExitCode -ge 8) {
            $summary.Add("FAIL  $name : robocopy exited with $($rc.ExitCode)")
            continue
        }
    }

    $hashFile = Join-Path $target '.component_hash'
    if (-not (Test-Path $hashFile) -or
        ((Get-Content -LiteralPath $hashFile -Raw) -ne $expected)) {
        [System.IO.File]::WriteAllText($hashFile, $expected,
            (New-Object System.Text.ASCIIEncoding))
    }

    New-Item -ItemType Directory -Force -Path $managed | Out-Null
    New-Item -ItemType Junction -Path $link -Target $target | Out-Null

    $files = Get-ChildItem -LiteralPath $target -Recurse -File -Force
    $longestRel = ($files | ForEach-Object { $_.FullName.Substring($target.Length) } |
        Sort-Object Length -Descending | Select-Object -First 1).Length
    $longestHost = $link.Length + $longestRel
    $note = ''
    if ($longestHost -ge 260) { $note = " (warning: longest path is $longestHost characters)" }
    $summary.Add("FIXED $name : $($files.Count) files -> $target$note")
}

Write-Host ''
Write-Host "=== $ComponentName long-path workaround ==="
$summary | ForEach-Object { Write-Host "  $_" }
Write-Host ''