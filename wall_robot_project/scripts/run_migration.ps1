param(
    [string]$DbPath = "robot_trajectories.db"
)

# Safe migration helper (PowerShell)
# Usage: .\scripts\run_migration.ps1 -DbPath .\robot_trajectories.db

if (-not (Test-Path $DbPath)) {
    Write-Error "DB file not found: $DbPath"
    exit 1
}

$backup = "$DbPath.bak"
Copy-Item -Path $DbPath -Destination $backup -Force
Write-Host "Backup created at $backup"

Write-Host "Running migration script against $DbPath"
python migrations/remove_legacy_column.py --db-path "$DbPath"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Migration script failed. Check output and restore from $backup if needed."
    exit $LASTEXITCODE
}

Write-Host "Migration completed. Backup retained at $backup"
