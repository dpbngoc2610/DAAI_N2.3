param(
    [string]$ConnectionName = "student_sales"
)

$ErrorActionPreference = "Stop"
$dataWarehouseRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $dataWarehouseRoot
$python = Join-Path $dataWarehouseRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "Snowflake environment is missing. Installing project dependencies..."
    & (Join-Path $dataWarehouseRoot "install_snowflake_tools.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Khong the tao moi truong Snowflake tai $python"
    }
}

$windowsCaBundle = Join-Path $dataWarehouseRoot ".venv\windows-ca-bundle.pem"
& $python (Join-Path $dataWarehouseRoot "build_windows_ca_bundle.py") --output $windowsCaBundle
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$env:REQUESTS_CA_BUNDLE = $windowsCaBundle
$env:SSL_CERT_FILE = $windowsCaBundle

& $python (Join-Path $dataWarehouseRoot "validate_lineage.py") --project-root $projectRoot --rebuild
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python (Join-Path $dataWarehouseRoot "validate_source.py") --project-root $projectRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python (Join-Path $projectRoot "star_schema\validate_model.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python (Join-Path $dataWarehouseRoot "validate_pipeline.py")
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
