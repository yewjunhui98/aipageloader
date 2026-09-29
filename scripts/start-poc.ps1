param(
  [string]$SaPassword = "Your_strong_password123"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Run-Checked {
  param([string]$Command)
  Write-Host ">> $Command"
  Invoke-Expression $Command
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $Command"
  }
}

Write-Host "Building backend image..."
Run-Checked "podman build -t poc-backend `"$root/backend`""

Write-Host "Building frontend image..."
Run-Checked "podman build -t poc-frontend `"$root/frontend`""

podman pod exists poc-stack | Out-Null
if ($LASTEXITCODE -eq 0) {
  Write-Host "Replacing existing pod poc-stack..."
  Run-Checked "podman pod rm -f poc-stack"
}

Write-Host "Creating pod..."
Run-Checked "podman pod create --name poc-stack -p 1433:1433 -p 8000:8000 -p 8080:80"

podman volume exists poc_mssql_data | Out-Null
if ($LASTEXITCODE -ne 0) {
  Run-Checked "podman volume create poc_mssql_data"
}

Write-Host "Starting MSSQL..."
Run-Checked "podman run -d --name poc-mssql --pod poc-stack -e ACCEPT_EULA=Y -e MSSQL_PID=Developer -e MSSQL_SA_PASSWORD=$SaPassword -v poc_mssql_data:/var/opt/mssql mcr.microsoft.com/mssql/server:2019-latest"

Write-Host "Starting backend..."
Run-Checked "podman run -d --name poc-backend --pod poc-stack -e DB_HOST=127.0.0.1 -e DB_PORT=1433 -e DB_NAME=master -e DB_USER=sa -e DB_PASSWORD=$SaPassword -e DB_DRIVER=`"ODBC Driver 18 for SQL Server`" localhost/poc-backend:latest"

Write-Host "Starting frontend..."
Run-Checked "podman run -d --name poc-frontend --pod poc-stack localhost/poc-frontend:latest"

Write-Host "Done."
Write-Host "Frontend: http://localhost:8080"
Write-Host "API docs: http://localhost:8000/docs"
