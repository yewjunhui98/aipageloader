$ErrorActionPreference = "Stop"
podman pod exists poc-stack | Out-Null
if ($LASTEXITCODE -eq 0) {
  podman pod rm -f poc-stack
  Write-Host "poc-stack removed."
} else {
  Write-Host "poc-stack does not exist."
}
