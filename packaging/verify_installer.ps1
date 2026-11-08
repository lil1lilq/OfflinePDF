# Install the setup silently for the current user, run the installed self-test,
# then uninstall and confirm that the program folder is gone.
param([string]$Setup = 'release/OfflinePDF-Setup-Windows-x64.exe')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$reports = Join-Path (Get-Location) 'release/validation'
New-Item -ItemType Directory -Force $reports | Out-Null
if (-not (Test-Path -LiteralPath $Setup -PathType Leaf)) { throw "Installer not found: $Setup" }
# A Korean folder name with a space checks path handling, as the portable check does.
$target = Join-Path ([IO.Path]::GetTempPath()) ('OfflinePDF 설치 검증 ' + [guid]::NewGuid())

function Wait-Process-Checked([string]$Program, [string[]]$Arguments, [string]$Step) {
    $process = Start-Process -FilePath $Program -ArgumentList $Arguments -PassThru
    if (-not $process.WaitForExit(300000)) { $process.Kill(); throw "$Step timed out" }
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "$Step failed (exit $($process.ExitCode))" }
}

try {
    Wait-Process-Checked (Resolve-Path $Setup).Path @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', "/DIR=`"$target`""
    ) 'Silent install'
    $exe = Join-Path $target 'OfflinePDF.exe'
    foreach ($file in @($exe, 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'SOURCE_CODE.txt', 'licenses')) {
        $path = if ([IO.Path]::IsPathRooted($file)) { $file } else { Join-Path $target $file }
        if (-not (Test-Path -LiteralPath $path)) { throw "Installed file missing: $file" }
    }
    # Sources are a separate release file now; they must not bloat the install.
    foreach ($file in @('dependency-sources', 'CorrespondingSource.zip')) {
        if (Test-Path -LiteralPath (Join-Path $target $file)) { throw "Unexpected file installed: $file" }
    }
    $report = Join-Path $reports 'installed-self-test.json'
    Wait-Process-Checked $exe @('--self-test', "`"$report`"") 'Installed self-test'
    if (-not (Get-Content $report -Raw | ConvertFrom-Json).ok) { throw 'Installed self-test failed.' }
    $uninstaller = Join-Path $target 'unins000.exe'
    Wait-Process-Checked $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') 'Silent uninstall'
    # The uninstaller finishes removing files after its own process exits.
    for ($i = 0; $i -lt 50 -and (Test-Path -LiteralPath $exe); $i++) { Start-Sleep -Milliseconds 200 }
    if (Test-Path -LiteralPath $exe) { throw 'Uninstall left OfflinePDF.exe behind.' }
    Write-Host 'Installer verified: silent install, self-test and uninstall.'
} finally {
    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
}
