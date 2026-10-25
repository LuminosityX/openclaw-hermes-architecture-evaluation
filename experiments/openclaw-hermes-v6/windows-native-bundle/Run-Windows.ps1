param([string]$ExperimentRoot = (Join-Path ([IO.Path]::GetTempPath()) ('och-' + [guid]::NewGuid().ToString('N').Substring(0,8))))
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$utf8 = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$ExperimentRoot = [IO.Path]::GetFullPath($ExperimentRoot)
if (Test-Path -LiteralPath $ExperimentRoot) { throw 'Choose a new, empty experiment directory.' }
$drive = New-Object -TypeName System.IO.DriveInfo -ArgumentList ([IO.Path]::GetPathRoot($ExperimentRoot))
if ($drive.AvailableFreeSpace -lt 12GB) { throw 'At least 12 GiB free is required before downloading dependencies.' }
New-Item -ItemType Directory -Path $ExperimentRoot | Out-Null
New-Item -ItemType Directory -Path (Join-Path $ExperimentRoot 'logs') | Out-Null
Write-Host ('Experiment directory: ' + $ExperimentRoot)
$manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'pins.json') | ConvertFrom-Json
$architecture = [Environment]::GetEnvironmentVariable('PROCESSOR_ARCHITEW6432')
if (-not $architecture) { $architecture = $env:PROCESSOR_ARCHITECTURE }
$target = if ($architecture -eq 'ARM64') { 'arm64' } elseif ($architecture -in @('AMD64','x64')) { 'x64' } else { throw 'This bundle supports Windows x64 and ARM64.' }
$report = [ordered]@{ platform='windows-native'; architecture=$target; os=[Environment]::OSVersion.VersionString; powershell=$PSVersionTable.PSVersion.ToString(); root=$ExperimentRoot; phases=@(); stage='preparation'; paid_model_calls=0 }
function Save-Report { [IO.File]::WriteAllText((Join-Path $ExperimentRoot 'setup-report.json'), ($report | ConvertTo-Json -Depth 10), $utf8) }
function Require-Space { if ($drive.AvailableFreeSpace -lt 6GB) { throw 'Capacity guard: less than 6 GiB free. No further installation or native task will start.' } }
function Download-Verified([string]$url,[string]$path,[string]$sha) {
    Require-Space
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $path
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant() -ne $sha) { throw ('Download hash mismatch: ' + [IO.Path]::GetFileName($path)) }
}
function Native-Stage([string]$name,[scriptblock]$action) {
    Require-Space
    Write-Host ('Running: ' + $name)
    $report.stage = $name; Save-Report
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $action *> (Join-Path $ExperimentRoot ('logs\' + $name + '.log')); $exitCode = $LASTEXITCODE } finally { $ErrorActionPreference = $previous }
    $report.phases += @{ name=$name; exit_code=$exitCode }
    Save-Report
    if ($exitCode -ne 0) { throw ('Preparation failed in ' + $name + '. The log is retained; this is not automatically a product rating.') }
}
try {
    $nodePin = $manifest.node.$target
    $nodeArchive = Join-Path $ExperimentRoot 'node.zip'
    Download-Verified $nodePin.url $nodeArchive $nodePin.sha256
    Expand-Archive -LiteralPath $nodeArchive -DestinationPath (Join-Path $ExperimentRoot 'node')
    Remove-Item -LiteralPath $nodeArchive
    $nodeDir = Join-Path $ExperimentRoot ('node\node-v' + $manifest.node.version + '-win-' + $target)
    $node = Join-Path $nodeDir 'node.exe'
    $env:PATH = $nodeDir + ';' + $env:PATH
    $env:NPM_CONFIG_CACHE = Join-Path $ExperimentRoot 'npm-cache'
    $env:NPM_CONFIG_USERCONFIG = Join-Path $ExperimentRoot 'empty-npmrc'
    $env:NPM_CONFIG_GLOBALCONFIG = Join-Path $ExperimentRoot 'empty-global-npmrc'
    [IO.File]::WriteAllText($env:NPM_CONFIG_USERCONFIG,'',$utf8)
    [IO.File]::WriteAllText($env:NPM_CONFIG_GLOBALCONFIG,'',$utf8)
    $ocPrefix = Join-Path $ExperimentRoot 'openclaw-app'
    Native-Stage 'openclaw-install' { & $node (Join-Path $nodeDir 'node_modules\npm\bin\npm-cli.js') install --prefix $ocPrefix --omit=dev --no-audit --no-fund ('openclaw@' + $manifest.openclaw.version) }
    $env:HERMES_HOME = Join-Path $ExperimentRoot 'hermes-owner'
    $env:HERMES_RUNTIME_DIR = Join-Path $ExperimentRoot 'hermes-tools'
    $env:UV_CACHE_DIR = Join-Path $ExperimentRoot 'uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $ExperimentRoot 'bootstrap-python'
    $env:UV_NO_CONFIG = '1'
    $source = Join-Path $env:HERMES_HOME 'hermes-agent'
    $sourceArchive = Join-Path $ExperimentRoot 'hermes-source.tar.gz'
    Download-Verified $manifest.hermes.url $sourceArchive $manifest.hermes.sha256
    $unpack = Join-Path $ExperimentRoot 'source-unpack'
    New-Item -ItemType Directory -Path $unpack | Out-Null
    Native-Stage 'hermes-source-extract' { & tar.exe -xf $sourceArchive -C $unpack }
    New-Item -ItemType Directory -Path $env:HERMES_HOME | Out-Null
    $children = @(Get-ChildItem -LiteralPath $unpack -Directory)
    if ($children.Count -ne 1) { throw 'Unexpected Hermes source archive layout.' }
    Move-Item -LiteralPath $children[0].FullName -Destination $source
    Remove-Item -LiteralPath $sourceArchive
    $installer = Join-Path $source 'scripts\install.ps1'
    if ((Get-FileHash -Algorithm SHA256 $installer).Hash.ToLowerInvariant() -ne $manifest.hermes.installer_sha256) { throw 'Pinned native installer source changed.' }
    $ps = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path $ps)) { $ps = (Get-Process -Id $PID).Path }
    # Only the official bootstrap-interpreter stage; no PATH publication,
    # desktop build, service registration or credential setup stages run.
    Native-Stage 'hermes-bootstrap-python' { & $ps -NoProfile -ExecutionPolicy Bypass -File $installer -Stage venv -HermesHome $env:HERMES_HOME -InstallDir $source -NonInteractive }
    $uvPin = $manifest.uv.$target
    $uv = Join-Path $env:HERMES_RUNTIME_DIR ('uv-' + $manifest.uv.version + '-win32-' + $target + '\uv.exe')
    if (-not (Test-Path $uv)) { throw 'Official bootstrap did not produce the pinned uv slot.' }
    $bootstrapPython = (& $uv python find --managed-python --no-project ('cpython-3.14-windows-' + $(if ($target -eq 'arm64') { 'aarch64' } else { 'x86_64' }) + '-none')) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw 'Bootstrap Python lookup failed.' }
    $bootstrapPython = $bootstrapPython.Trim()
    Push-Location $source
    try { Native-Stage 'hermes-application-dependencies' { & $bootstrapPython -m pm.cli install --extra all } } finally { Pop-Location }
    $launch = @{ node=$node; root=$ExperimentRoot; openclaw_entry=(Join-Path $ocPrefix 'node_modules\openclaw\openclaw.mjs'); hermes_source=$source; bootstrap_python=$bootstrapPython; hermes_owner=$env:HERMES_HOME; hermes_tools=$env:HERMES_RUNTIME_DIR }
    $launchPath = Join-Path $ExperimentRoot 'launch-paths.json'
    [IO.File]::WriteAllText($launchPath,($launch | ConvertTo-Json),$utf8)
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'windows-native.mjs') -Destination $ExperimentRoot
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'pins.json') -Destination $ExperimentRoot
    Native-Stage 'native-platform-cases' { & $node (Join-Path $ExperimentRoot 'windows-native.mjs') $launchPath }
    $report.stage='finished'; Save-Report
} catch {
    $report.stage='needs_review'; $report['error']=$_.Exception.Message; Save-Report
    Write-Host ('Stopped: ' + $_.Exception.Message)
} finally {
    # Return only native evidence and small scripts/manifests, never dependency
    # stores or a copy of the user's environment/credentials.
    $returnDir = Join-Path $ExperimentRoot 'return-results'
    New-Item -ItemType Directory -Force -Path $returnDir | Out-Null
    foreach ($name in @('setup-report.json','platform-results.json','controller-error.json','pins.json','windows-native.mjs','logs')) {
        $item = Join-Path $ExperimentRoot $name
        if (Test-Path $item) { Copy-Item -LiteralPath $item -Destination $returnDir -Recurse }
    }
    function Copy-NativeEvidence([string]$from,[string]$to) {
        if (-not (Test-Path -LiteralPath $from)) { return }
        New-Item -ItemType Directory -Force -Path $to | Out-Null
        foreach ($entry in Get-ChildItem -LiteralPath $from -Force) {
            if ($entry.PSIsContainer) {
                if ($entry.Name -notin @('installs','node_modules','cache','tools','skills','__pycache__')) { Copy-NativeEvidence $entry.FullName (Join-Path $to $entry.Name) }
            } else { Copy-Item -LiteralPath $entry.FullName -Destination $to }
        }
    }
    Copy-NativeEvidence (Join-Path $ExperimentRoot 'cases') (Join-Path $returnDir 'cases')
    $zip = Join-Path $ExperimentRoot 'windows-results.zip'
    Compress-Archive -Path (Join-Path $returnDir '*') -DestinationPath $zip
    Write-Host ('Return this file: ' + $zip)
    Write-Host ('Dependencies remain only in the experiment directory. To reclaim space after returning results, remove: ' + $ExperimentRoot)
}
