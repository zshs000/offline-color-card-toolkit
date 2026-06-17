Set-Location -LiteralPath $PSScriptRoot\..
$env:PYTHONPATH = (Resolve-Path ".\src").Path
.\.venv\Scripts\python -m color_card_toolkit.review_app --host 127.0.0.1 --port 8765
