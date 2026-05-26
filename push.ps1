#!/usr/bin/env pwsh
# Kayta tata git push -komennon sijaan.
# Pushaa koodin ja odottaa etta deploy menee live.

git push @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\hooks\post-push.py"
