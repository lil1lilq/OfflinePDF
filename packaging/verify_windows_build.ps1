param(
    [string]$Executable = 'dist/OfflinePDF/OfflinePDF.exe',
    [string]$Installer = 'release/OfflinePDF-Setup-Windows-x64.exe',
    [switch]$SkipFirewall
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$reports = Join-Path (Get-Location) 'release/validation'
New-Item -ItemType Directory -Force $reports | Out-Null
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('OfflinePDF-verify-' + [guid]::NewGuid())
New-Item -ItemType Directory $temporary | Out-Null
$auditBackup = Join-Path $temporary 'audit.csv'
$auditSaved = $false
$rules = @()
$installed = $null
$profileStates = @()

if (-not ('OfflinePDF.VerificationPaths' -as [type])) {
    Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
using System.Text;
namespace OfflinePDF {
    public static class VerificationPaths {
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        public static extern uint GetLongPathName(string path, StringBuilder buffer, uint size);
    }
}
'@
}

function Get-ProgramPath([string]$Path) {
    $resolved = (Resolve-Path $Path).Path
    $buffer = [Text.StringBuilder]::new(32768)
    $length = [OfflinePDF.VerificationPaths]::GetLongPathName($resolved, $buffer, $buffer.Capacity)
    if ($length -eq 0 -or $length -ge $buffer.Capacity) {
        throw 'Cannot canonicalize the executable path for the native event audit.'
    }
    return $buffer.ToString()
}

function Invoke-NativeChecked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Verification command failed: $Program ($LASTEXITCODE)" }
}

function Invoke-Diagnostic([string]$Program, [string]$Command, [string]$Report) {
    Remove-Item $Report -Force -ErrorAction SilentlyContinue
    $process = Start-Process -FilePath $Program -ArgumentList @($Command, "`"$Report`"") -PassThru
    if (-not $process.WaitForExit(180000)) {
        $process.Kill()
        throw "Executable diagnostic timed out: $Command"
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) {
        $detail = if (Test-Path $Report) { Get-Content $Report -Raw } else { 'No report was produced.' }
        throw "Executable diagnostic failed: $Command`n$detail"
    }
    if (-not (Test-Path $Report)) { throw "Missing executable report: $Command" }
    return Get-Content $Report -Raw | ConvertFrom-Json
}

function Read-AppConnections([string]$Program, [long]$AfterRecord) {
    # Native WFP audit catches connections attempted by C/C++ DLLs as well.
    $suffix = $Program.Substring(2).ToLowerInvariant()
    $query = "*[System[(EventID=5156 or EventID=5157) and EventRecordID > $AfterRecord]]"
    $events = Get-WinEvent -LogName Security -FilterXPath $query -ErrorAction SilentlyContinue
    foreach ($event in $events) {
        [xml]$xml = $event.ToXml()
        $data = @{}
        foreach ($item in $xml.Event.EventData.Data) { $data[$item.Name] = [string]$item.'#text' }
        if ($data['Application'] -and $data['Application'].ToLowerInvariant().EndsWith($suffix)) {
            [pscustomobject]@{
                event = $event.Id
                process = $data['ProcessID']
                address = $data['DestAddress']
                port = $data['DestPort']
            }
        }
    }
}

function Verify-Program([string]$Program, [string]$Name) {
    # TEMP may contain RUNNER~1; audit events use the expanded filesystem name.
    $Program = Get-ProgramPath $Program
    if ($SkipFirewall) {
        $result = Invoke-Diagnostic $Program '--self-test' (Join-Path $reports "$Name-self-test.json")
        if (-not $result.ok) { throw "Self-test failed: $Name" }
        return
    }
    # This explicit developer-only canary sends no documents: TCP handshake only.
    $baseline = Invoke-Diagnostic $Program '--network-probe' (Join-Path $temporary "$Name-before.json")
    if (-not $baseline.connected) {
        throw 'Native TCP baseline unavailable. Firewall verification is inconclusive, not a pass.'
    }
    $rule = 'OfflinePDF-Verification-' + [guid]::NewGuid()
    New-NetFirewallRule -Name $rule -DisplayName $rule -Direction Outbound `
        -Program $Program -Action Block -Enabled True -Profile Any | Out-Null
    $script:rules += $rule
    $marker = (Get-WinEvent -LogName Security -MaxEvents 1).RecordId
    $blocked = Invoke-Diagnostic $Program '--network-probe' (Join-Path $temporary "$Name-blocked.json")
    $controlEvents = @()
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $controlEvents = @(Read-AppConnections $Program $marker)
        if ($controlEvents | Where-Object event -eq 5157) { break }
        Start-Sleep -Milliseconds 100
    }
    if ($blocked.connected -or -not ($controlEvents | Where-Object event -eq 5157)) {
        throw 'OS firewall did not produce confirmed native TCP block evidence.'
    }
    $marker = (Get-WinEvent -LogName Security -MaxEvents 1).RecordId
    $result = Invoke-Diagnostic $Program '--self-test' (Join-Path $reports "$Name-self-test.json")
    Start-Sleep -Milliseconds 1500
    $connections = @(Read-AppConnections $Program $marker)
    $report = [ordered]@{
        executable = $Name
        baselineConnected = $baseline.connected
        nativeCanaryBlocked = -not $blocked.connected
        firewallDropConfirmed = $true
        selfTestPassed = $result.ok
        applicationConnectionEvents = $connections
        scope = 'Synthetic self-test only; not a sandbox or proof for every possible input.'
    }
    $report | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $reports "$Name-network.json")
    if (-not $result.ok -or $connections.Count -ne 0) {
        throw "Offline processing or zero-connection audit failed: $Name"
    }
}

try {
    if (-not $SkipFirewall) {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = [Security.Principal.WindowsPrincipal]::new($identity)
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw 'Firewall verification requires an administrator test environment.'
        }
        if ((Get-Service MpsSvc).Status -ne 'Running') { throw 'Windows Firewall service is not running.' }
        $profileStates = @(Get-NetFirewallProfile | Select-Object Name, Enabled)
        Set-NetFirewallProfile -Profile Domain,Private,Public -Enabled True
        Invoke-NativeChecked 'auditpol.exe' @('/backup', "/file:$auditBackup")
        $auditSaved = $true
        Invoke-NativeChecked 'auditpol.exe' @('/set', '/subcategory:{0CCE9226-69AE-11D9-BED3-505054503030}', '/success:enable', '/failure:enable')
    }
    Verify-Program $Executable 'portable'
    if (Test-Path $Installer) {
        $installed = Join-Path $temporary '한글 설치 테스트'
        $installerProcess = Start-Process -FilePath (Resolve-Path $Installer).Path `
            -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCANCEL', "/DIR=`"$installed`"") -PassThru -Wait
        if ($installerProcess.ExitCode -ne 0) { throw "Installer test failed ($($installerProcess.ExitCode))" }
        Verify-Program (Join-Path $installed 'OfflinePDF.exe') 'installed'
    }
    Write-Host 'Portable/installer self-tests completed. See release/validation.'
} finally {
    foreach ($rule in $rules) { Remove-NetFirewallRule -Name $rule -ErrorAction Continue }
    foreach ($savedProfile in $profileStates) { Set-NetFirewallProfile -Profile $savedProfile.Name -Enabled $savedProfile.Enabled }
    if ($auditSaved) { Invoke-NativeChecked 'auditpol.exe' @('/restore', "/file:$auditBackup") }
    if ($installed -and (Test-Path (Join-Path $installed 'unins000.exe'))) {
        Start-Process (Join-Path $installed 'unins000.exe') -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -Wait
    }
    Remove-Item $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
