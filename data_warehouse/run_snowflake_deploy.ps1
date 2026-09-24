param(
    [string]$ConnectionName = "student_sales"
)

$ErrorActionPreference = "Stop"
$dataWarehouseRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $dataWarehouseRoot
$python = Join-Path $dataWarehouseRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Chua cai moi truong Snowflake. Hay chay .\data_warehouse\install_snowflake_tools.ps1 truoc."
}

& $python (Join-Path $dataWarehouseRoot "validate_source.py") --project-root $projectRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python (Join-Path $projectRoot "star_schema\validate_model.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python (Join-Path $dataWarehouseRoot "build_warehouse.py") `
    --project-root $projectRoot `
    --connection-name $ConnectionName
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python (Join-Path $projectRoot "star_schema\validate_model.py") `
    --connection-name $ConnectionName
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python (Join-Path $dataWarehouseRoot "validate_warehouse.py") `
    --connection-name $ConnectionName
exit $LASTEXITCODE
