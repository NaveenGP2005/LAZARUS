# LAZARUS — run.ps1
# One-command launch: generate data, run batch, open dashboard.
# Usage: .\run.ps1

Write-Host ""
Write-Host "  ██╗      █████╗ ███████╗ █████╗ ██████╗ ██╗   ██╗███████╗" -ForegroundColor Cyan
Write-Host "  ██║     ██╔══██╗╚══███╔╝██╔══██╗██╔══██╗██║   ██║██╔════╝" -ForegroundColor Cyan
Write-Host "  ██║     ███████║  ███╔╝ ███████║██████╔╝██║   ██║███████╗" -ForegroundColor Cyan
Write-Host "  ██║     ██╔══██║ ███╔╝  ██╔══██║██╔══██╗██║   ██║╚════██║" -ForegroundColor Cyan
Write-Host "  ███████╗██║  ██║███████╗██║  ██║██║  ██║╚██████╔╝███████║" -ForegroundColor Cyan
Write-Host "  ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Cause-Aware Payment Recovery Agent — Razorpay AI Buildathon 2026" -ForegroundColor DarkCyan
Write-Host ""

# Check .env exists
if (-not (Test-Path ".env")) {
    Write-Host "[ERROR] .env file not found. Copy .env.example and fill in your credentials." -ForegroundColor Red
    Write-Host "        cp .env.example .env" -ForegroundColor Yellow
    exit 1
}

Write-Host "[1/3] Generating 100 synthetic failed transactions..." -ForegroundColor Yellow
python -X utf8 data/generator.py
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] Generator failed." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "[2/3] Running LAZARUS batch (Gemini calls — ~4 min)..." -ForegroundColor Yellow
python -X utf8 batch_runner.py
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] Batch runner failed." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "[3/3] Launching dashboard..." -ForegroundColor Yellow
Write-Host "      Open: http://localhost:8501" -ForegroundColor Green
Write-Host ""
streamlit run dashboard.py
