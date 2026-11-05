param(
    [Parameter(Mandatory = $true)][string]$InputDirectory,
    [string]$ReportDirectory = 'scan-report'
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$report = [IO.Path]::GetFullPath($ReportDirectory)
New-Item -ItemType Directory -Force $report | Out-Null
$summary = [ordered]@{
    status = 'not_started'
    started_utc = (Get-Date).ToUniversalTime().ToString('o')
    note = 'Microsoft Defender results do not determine Chrome Safe Browsing verdicts.'
    signature_update_exit_code = $null
    scans = @()
    error = $null
}
$failed = $false
try {
    $inputRoot = (Resolve-Path -LiteralPath $InputDirectory).Path
    if (-not (Test-Path -LiteralPath $inputRoot -PathType Container)) {
        throw 'Input must be a directory containing the downloaded build artifact.'
    }
    # Record bytes before scanning: background protection can quarantine a file.
    $originalFiles = @(Get-ChildItem -LiteralPath $inputRoot -Recurse -File)
    if (-not $originalFiles.Count) { throw 'The downloaded artifact is empty.' }
    $originalHashes = @{}
    $originalFiles | ForEach-Object {
        $originalHashes[$_.FullName] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        [pscustomobject]@{
            path = [IO.Path]::GetRelativePath($inputRoot, $_.FullName)
            size_bytes = $_.Length
            sha256 = $originalHashes[$_.FullName]
        }
    } | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $report 'artifact-sha256.csv')

    $installer = @($originalFiles | Where-Object Name -eq 'OfflinePDF-Setup-Windows-x64.exe')
    $portable = @($originalFiles | Where-Object Name -eq 'OfflinePDF-Windows-x64-portable.zip')
    if ($installer.Count -ne 1 -or $portable.Count -ne 1) {
        throw 'Expected exactly one installer EXE and one portable ZIP from the Windows build.'
    }
    Get-AuthenticodeSignature -LiteralPath $installer[0].FullName |
        Select-Object -Property @(
            'Path'; 'Status'; 'StatusMessage'
            @{Name = 'Signer'; Expression = { if ($_.SignerCertificate) { $_.SignerCertificate.Subject } }}
        ) |
        ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $report 'installer-signature.json')

    $candidates = @()
    $platform = Join-Path $env:ProgramData 'Microsoft/Windows Defender/Platform'
    if (Test-Path -LiteralPath $platform) {
        $candidates += @(Get-ChildItem -LiteralPath $platform -Directory |
            Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'MpCmdRun.exe' })
    }
    $candidates += (Join-Path $env:ProgramFiles 'Windows Defender/MpCmdRun.exe')
    $engine = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
    if (-not $engine) { throw 'Microsoft Defender command-line engine is unavailable on this runner.' }
    $summary['engine'] = $engine
    $service = Get-Service -Name WinDefend -ErrorAction Stop
    if ($service.Status -ne 'Running') {
        # Start the existing service; never disable protection or create exclusions.
        Start-Service -Name WinDefend -ErrorAction Stop
    }
    & $engine -SignatureUpdate 2>&1 | Tee-Object -FilePath (Join-Path $report 'signature-update.log')
    $summary.signature_update_exit_code = $LASTEXITCODE
    if ($LASTEXITCODE -ne 0) { throw 'Defender security intelligence update failed. See signature-update.log.' }
    Get-MpComputerStatus | Select-Object -Property @(
        'AMProductVersion'; 'AMEngineVersion'; 'AntivirusSignatureVersion'
        'AntivirusSignatureLastUpdated'; 'AMServiceEnabled'; 'AntivirusEnabled'; 'RealTimeProtectionEnabled'
    ) |
        ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $report 'defender-status.json')

    function Invoke-ArtifactScan([string]$Label, [string]$Target) {
        $log = Join-Path $report "$Label.log"
        # Custom no-remediation scans ignore file exclusions and scan archives.
        # Code 2 means detection OR a scan error; the raw log is authoritative.
        & $engine -Scan -ScanType 3 -File $Target -DisableRemediation 2>&1 |
            Tee-Object -FilePath $log
        $code = $LASTEXITCODE
        $summary.scans += [ordered]@{
            target = $Label
            exit_code = $code
            log = "$Label.log"
            result = $(if ($code -eq 0) { 'no_detection_reported' } else { 'needs_review' })
        }
    }
    Invoke-ArtifactScan 'installer' $installer[0].FullName
    Invoke-ArtifactScan 'portable-zip' $portable[0].FullName

    # Also scan extracted EXE/DLL files; never execute the downloaded application.
    $temporary = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
    $expanded = Join-Path $temporary ('offlinepdf-av-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $expanded | Out-Null
    try {
        Expand-Archive -LiteralPath $portable[0].FullName -DestinationPath $expanded
        $expandedFiles = @(Get-ChildItem -LiteralPath $expanded -Recurse -File)
        if (-not @($expandedFiles | Where-Object Name -eq 'OfflinePDF.exe').Count) {
            throw 'Portable ZIP did not contain OfflinePDF.exe; scan is incomplete.'
        }
        $expandedHashes = @{}
        $expandedFiles | ForEach-Object {
            $expandedHashes[$_.FullName] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            [pscustomobject]@{
                path = [IO.Path]::GetRelativePath($expanded, $_.FullName)
                size_bytes = $_.Length
                sha256 = $expandedHashes[$_.FullName]
            }
        } | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $report 'portable-files-sha256.csv')
        Invoke-ArtifactScan 'portable-files' $expanded
        foreach ($file in $expandedFiles) {
            if (-not (Test-Path -LiteralPath $file.FullName) -or
                (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne $expandedHashes[$file.FullName]) {
                throw 'An extracted file disappeared or changed during inspection.'
            }
        }
    } finally {
        Remove-Item -LiteralPath $expanded -Recurse -Force -ErrorAction SilentlyContinue
    }
    # Ensure background protection did not remove/alter an input and mask a result.
    $after = @(Get-ChildItem -LiteralPath $inputRoot -Recurse -File)
    if ($after.Count -ne $originalFiles.Count) { throw 'Artifact files disappeared during inspection; review protection logs.' }
    foreach ($file in $originalFiles) {
        if (-not (Test-Path -LiteralPath $file.FullName) -or
            (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne $originalHashes[$file.FullName]) {
            throw 'An input artifact disappeared or changed during inspection.'
        }
    }
    if (@($summary.scans | Where-Object exit_code -ne 0).Count) {
        $summary.status = 'needs_review'
        $failed = $true
    } else {
        $summary.status = 'no_detection_reported'
    }
} catch {
    $summary.status = 'incomplete_or_unavailable'
    $summary.error = $_.Exception.Message
    $failed = $true
    Write-Warning $summary.error
} finally {
    try {
        Get-MpThreatDetection -ErrorAction Stop |
            Where-Object { $_.InitialDetectionTime -ge [datetime]$summary.started_utc } |
            Select-Object -Property @(
                'ThreatID'; 'InitialDetectionTime'; 'LastThreatStatusChangeTime'
                'Resources'; 'ActionSuccess'; 'ThreatStatusErrorCode'
            ) |
            ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $report 'recent-protection-detections.json')
    } catch {
        $_.Exception.Message | Set-Content -Encoding utf8 (Join-Path $report 'protection-history-unavailable.txt')
    }
    $summary['finished_utc'] = (Get-Date).ToUniversalTime().ToString('o')
    $summary | ConvertTo-Json -Depth 8 |
        Set-Content -Encoding utf8 (Join-Path $report 'summary.json')
    Write-Host "Defender scan status: $($summary.status)"
    if ($env:GITHUB_STEP_SUMMARY) {
        @(
            '### OfflinePDF artifact inspection',
            "Result: **$($summary.status)**",
            'Download OfflinePDF-antivirus-report for raw scanner output and SHA256 values.',
            'A clean Defender result does not guarantee Chrome will allow the download.'
        ) | Add-Content -Encoding utf8 $env:GITHUB_STEP_SUMMARY
    }
}
if ($failed) { throw 'Artifact inspection needs review or could not complete. Download OfflinePDF-antivirus-report.' }
