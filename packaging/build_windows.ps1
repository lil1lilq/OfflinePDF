param([switch]$Offline, [switch]$FixFormat, [switch]$SkipInstaller, [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Build step failed: $Program (exit $LASTEXITCODE)" }
}
if ([Environment]::Is64BitOperatingSystem -eq $false) { throw 'Windows x64 is required.' }
Invoke-Checked $Python @('-c', 'import struct,sys; assert struct.calcsize(chr(80))==8; assert sys.version_info[:2]==(3,12)')
# Install exactly the locked packages; pip refuses any file whose hash differs.
if ($Offline) {
    Invoke-Checked $Python @('-m','pip','install','--require-hashes','--no-index','--find-links','wheelhouse','-r','requirements-lock.txt')
} else {
    Invoke-Checked $Python @('-m','pip','install','--require-hashes','-r','requirements-lock.txt')
}
Invoke-Checked $Python @('packaging/prepare_ai_model.py')
if ($FixFormat) { Invoke-Checked $Python @('-m','ruff','format','offline_pdf','packaging','tests','main.py') }
Invoke-Checked $Python @('-m','ruff','check','offline_pdf','packaging','tests','main.py')
Invoke-Checked $Python @('-m','ruff','format','--check','offline_pdf','packaging','tests','main.py')
Invoke-Checked $Python @('-X','faulthandler','-m','unittest','discover','-s','tests','-v')
Invoke-Checked $Python @('packaging/collect_licenses.py')
if ($Offline) { Invoke-Checked $Python @('packaging/prepare_dependency_sources.py','--offline') }
else { Invoke-Checked $Python @('packaging/prepare_dependency_sources.py') }
$bundleArgs = @('-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name','OfflinePDF',
    '--version-file','packaging/windows-version.txt','--icon','assets/app.ico',
    '--add-data','assets;assets','--add-data','offline_pdf/translations.json;offline_pdf',
    '--collect-all','pymupdf','--collect-all','PIL','--collect-all','customtkinter',
    '--collect-binaries','onnxruntime','--collect-data','onnxruntime',
    '--hidden-import','onnxruntime.capi.onnxruntime_pybind11_state','--exclude-module','onnx','--exclude-module','torch',
    '--exclude-module','onnxruntime.transformers','--exclude-module','onnxruntime.tools','--exclude-module','onnxruntime.quantization',
    '--add-data','models;models',
    '--add-data','licenses;licenses','--add-data','LICENSE;.',
    '--add-data','README.md;.','main.py')
if (Test-Path 'tessdata') { $bundleArgs += @('--add-data','tessdata;tessdata') }
Invoke-Checked $Python $bundleArgs
$destination = 'dist/OfflinePDF'
Copy-Item 'README.md','README.en.md','LICENSE','THIRD_PARTY_NOTICES.md' $destination
Copy-Item 'CHANGELOG.md' $destination
Copy-Item 'BUILDING.md' $destination
Copy-Item 'assets' "$destination/assets" -Recurse -Force
Copy-Item 'licenses' "$destination/licenses" -Recurse -Force
Copy-Item 'dependency-sources' "$destination/dependency-sources" -Recurse -Force
Invoke-Checked $Python @('packaging/make_source_archive.py', "$destination/CorrespondingSource.zip")
New-Item -ItemType Directory -Force 'release' | Out-Null
Compress-Archive -Path $destination -DestinationPath 'release/OfflinePDF-Windows-x64-portable.zip' -Force
# Do not carry a generated setup file from an earlier local build into a release.
$setup = 'release/OfflinePDF-Setup-Windows-x64.exe'
Remove-Item -LiteralPath $setup -Force -ErrorAction SilentlyContinue
$outputs = @('release/OfflinePDF-Windows-x64-portable.zip')
if (-not $SkipInstaller) {
    # The installer packs exactly the dist/OfflinePDF folder of the portable ZIP.
    $iscc = @(
        (Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue).Source,
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $iscc) {
        throw 'Inno Setup 6 (ISCC.exe) was not found. Install it, or pass -SkipInstaller for a portable-only build.'
    }
    $version = (& $Python -c 'import offline_pdf; print(offline_pdf.__version__)').Trim()
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw "Unexpected app version: $version" }
    Invoke-Checked $iscc @('/Qp', "/DAppVersion=$version", "/DAppVersionNumeric=$version.0", 'packaging/installer.iss')
    if (-not (Test-Path -LiteralPath $setup)) { throw "Installer was not created: $setup" }
    $outputs += $setup
}
$outputs | ForEach-Object {
    $hash = Get-FileHash -LiteralPath $_ -Algorithm SHA256
    "$($hash.Hash)  $([IO.Path]::GetFileName($_))"
} | Set-Content -Encoding utf8 'release/SHA256SUMS.txt'
Write-Host "Build completed: $($outputs -join ', ')"
