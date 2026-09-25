param(
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$ExecutableName = "XsdXmlBuilder"
)

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $projectDir ".build-venv"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
$distExe = Join-Path $projectDir ("dist\" + $ExecutableName + ".exe")
$systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$tempBuildRoot = Join-Path $systemTemp ("XsdXmlBuilder-build-" + [guid]::NewGuid().ToString("N"))
$tempBuildRoot = [IO.Path]::GetFullPath($tempBuildRoot)
if (-not $tempBuildRoot.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Diretório temporário de compilação fora da pasta TEMP: $tempBuildRoot"
}
New-Item -ItemType Directory -Path $tempBuildRoot | Out-Null

function Assert-LastExitCode([string]$step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$step falhou com código $LASTEXITCODE."
    }
}

$running = Get-Process -Name $ExecutableName -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $distExe }
if ($running) {
    throw "Feche $ExecutableName.exe antes de recompilar."
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    python -m venv $venvDir
    Assert-LastExitCode "Criação do ambiente virtual"
}

& $pythonExe -m pip install --upgrade pip
Assert-LastExitCode "Atualização do pip"
& $pythonExe -m pip install -e $projectDir
Assert-LastExitCode "Instalação do projeto"
& $pythonExe -m pip install "pyinstaller>=6.0"
Assert-LastExitCode "Instalação do PyInstaller"

Push-Location $projectDir
try {
    & $pythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name $ExecutableName `
        --paths src `
        --collect-all lxml `
        --workpath (Join-Path $tempBuildRoot "build") `
        --specpath (Join-Path $tempBuildRoot "spec") `
        --distpath (Join-Path $projectDir "dist") `
        src\xsd_model_builder\gui_entry.py
    Assert-LastExitCode "Compilação do executável"
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $tempBuildRoot) {
        Remove-Item -LiteralPath $tempBuildRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Executável criado em: $distExe"
