param(
    [string]$PythonPath = "C:\Users\ngocb\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)

$ErrorActionPreference = "Stop"
$dataWarehouseRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvRoot = Join-Path $dataWarehouseRoot ".venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$snowCli = Join-Path $venvRoot "Scripts\snow.exe"
$requirements = Join-Path $dataWarehouseRoot "requirements.txt"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "Khong tim thay Python 3.9 tro len. Hay cai Python va chay lai script."
    }
    $PythonPath = $pythonCommand.Source
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
