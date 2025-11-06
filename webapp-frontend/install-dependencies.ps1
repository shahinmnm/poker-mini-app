# PowerShell script to install npm dependencies
# Run this script from the webapp-frontend directory

Write-Host "Installing npm dependencies..." -ForegroundColor Cyan

# Check if npm is available
$npmPath = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmPath) {
    Write-Host "ERROR: npm is not found in PATH." -ForegroundColor Red
    Write-Host "Please install Node.js from https://nodejs.org/" -ForegroundColor Yellow
    Write-Host "Or add npm to your PATH if it's already installed." -ForegroundColor Yellow
    exit 1
}

# Install dependencies
npm install

if ($LASTEXITCODE -eq 0) {
    Write-Host "Dependencies installed successfully!" -ForegroundColor Green
} else {
    Write-Host "Failed to install dependencies." -ForegroundColor Red
    exit 1
}

