param([switch]$Offline, [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Build step failed: $Program (exit $LASTEXITCODE)" }
}
if ([Environment]::Is64BitOperatingSystem -eq $false) { throw 'Windows x64 is required.' }
Invoke-Checked $Python @('-c', 'import struct,sys; assert struct.calcsize("P")==8, "Python x64 required"; assert sys.version_info[:2]==(3,12), "Use Python 3.12 x64"')
if ($Offline) {
    Invoke-Checked $Python @('-m','pip','install','--no-index','--find-links','wheelhouse','-r','requirements-build.txt')
} else {
    Invoke-Checked $Python @('-m','pip','install','-r','requirements-build.txt')
}
Invoke-Checked $Python @('packaging/prepare_ai_model.py')
Invoke-Checked $Python @('-m','unittest','discover','-s','tests','-v')
Invoke-Checked $Python @('packaging/collect_licenses.py')
if ($Offline) { Invoke-Checked $Python @('packaging/prepare_dependency_sources.py','--offline') }
else { Invoke-Checked $Python @('packaging/prepare_dependency_sources.py') }
$bundleArgs = @('-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name','OfflinePDF',
    '--version-file','packaging/windows-version.txt',
    '--collect-all','pymupdf','--collect-all','PIL','--collect-all','pillow_heif',
    '--collect-binaries','onnxruntime','--collect-data','onnxruntime',
    '--hidden-import','onnxruntime.capi.onnxruntime_pybind11_state','--exclude-module','onnx','--exclude-module','torch',
    '--exclude-module','onnxruntime.transformers','--exclude-module','onnxruntime.tools','--exclude-module','onnxruntime.quantization',
    '--add-data','models;models',
    '--additional-hooks-dir','packaging/hooks','--add-data','licenses;licenses','--add-data','LICENSE;.',
    '--add-data','README.md;.','main.py')
if (Test-Path 'tessdata') { $bundleArgs += @('--add-data','tessdata;tessdata') }
Invoke-Checked $Python $bundleArgs
$destination = 'dist/OfflinePDF'
Copy-Item 'README.md','USER_GUIDE_KO.txt','LICENSE','THIRD_PARTY_NOTICES.md' $destination
Copy-Item 'CHANGELOG.md' $destination
Copy-Item 'BUILDING.md' $destination
Copy-Item 'assets' "$destination/assets" -Recurse -Force
Copy-Item 'licenses' "$destination/licenses" -Recurse -Force
Copy-Item 'dependency-sources' "$destination/dependency-sources" -Recurse -Force
Invoke-Checked $Python @('packaging/make_source_archive.py', "$destination/CorrespondingSource.zip")
New-Item -ItemType Directory -Force 'release' | Out-Null
Compress-Archive -Path $destination -DestinationPath 'release/OfflinePDF-Windows-x64-portable.zip' -Force
$iscc = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
$isccPath = if ($iscc) { $iscc.Source } else { $null }
if (-not $isccPath) {
    $candidate = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe'
    if (Test-Path $candidate) { $isccPath = $candidate }
}
if ($isccPath) {
    Invoke-Checked $isccPath @('packaging/installer.iss')
} else {
    Write-Host 'Portable build completed. Install Inno Setup 6 and run ISCC.exe packaging/installer.iss for the installer.'
}
Get-ChildItem 'release' -File | ForEach-Object {
    $hash = Get-FileHash $_.FullName -Algorithm SHA256
    "$($hash.Hash)  $($_.Name)"
} | Set-Content -Encoding utf8 'release/SHA256SUMS.txt'
Write-Host 'Build completed. See release folder.'
