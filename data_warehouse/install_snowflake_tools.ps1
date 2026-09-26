param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$dataWarehouseRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvRoot = Join-Path $dataWarehouseRoot ".venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$snowCli = Join-Path $venvRoot "Scripts\snow.exe"
$requirements = Join-Path $dataWarehouseRoot "requirements.txt"

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "Khong tim thay Python 3.10 tro len. Hay cai Python va chay lai script."
    }
    $PythonPath = $pythonCommand.Source
}

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Khong tim thay Python tai: $PythonPath"
}

& $PythonPath -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Can Python 3.10 tro len de cai Snowflake CLI."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonPath -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $venvPython -m pip install --requirement $requirements
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $snowCli --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $venvPython -c "import snowflake.connector, pandas, sqlparse; print(f'Snowflake Connector {snowflake.connector.__version__}'); print(f'pandas {pandas.__version__}'); print(f'sqlparse {sqlparse.__version__}')"
exit $LASTEXITCODE
