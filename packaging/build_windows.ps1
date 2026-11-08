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
Invoke-Checked $Python @('-m','ruff','check','offline_pdf','packaging','tests','main.py')
Invoke-Checked $Python @('-m','ruff','format','--check','offline_pdf','packaging','tests','main.py')
Invoke-Checked $Python @('-m','unittest','discover','-s','tests','-v')
Invoke-Checked $Python @('packaging/collect_licenses.py')
if ($Offline) { Invoke-Checked $Python @('packaging/prepare_dependency_sources.py','--offline') }
else { Invoke-Checked $Python @('packaging/prepare_dependency_sources.py') }
$bundleArgs = @('-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name','OfflinePDF',
    '--version-file','packaging/windows-version.txt','--icon','assets/app.ico',
    '--add-data','assets;assets','--add-data','offline_pdf/translations.json;offline_pdf',
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
# Do not carry a generated setup file from an earlier local build into a release.
Remove-Item -LiteralPath 'release/OfflinePDF-Setup-Windows-x64.exe' -Force -ErrorAction SilentlyContinue
$portable = 'release/OfflinePDF-Windows-x64-portable.zip'
$hash = Get-FileHash -LiteralPath $portable -Algorithm SHA256
"$($hash.Hash)  $([IO.Path]::GetFileName($portable))" |
    Set-Content -Encoding utf8 'release/SHA256SUMS.txt'
Write-Host 'Portable build completed. See release/OfflinePDF-Windows-x64-portable.zip.'
