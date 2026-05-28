param([string]$message = "")
if (-not $message) { Write-Error "Kayta: .\push.ps1 'commit viesti'"; exit 1 }
git add -A
git commit -m $message
if (-not $?) { Write-Host "Commit epaonnistui"; exit 1 }
git push origin main
if (-not $?) { Write-Host "Push epaonnistui"; exit 1 }
Write-Host "Odotetaan GitHub Actions -ajoa..."
$runId = $null
for ($i = 0; $i -lt 6; $i++) {
    Start-Sleep -Seconds 5
    $runs = gh run list --limit 1 --workflow code_review.yml --branch main --json databaseId,status | ConvertFrom-Json
    if ($runs -and $runs[0].status -in @("in_progress","queued","waiting")) { $runId = $runs[0].databaseId; break }
}
if (-not $runId) { Write-Host "Ei loydetty aktiivista ajoa"; exit 1 }
Write-Host "Seurataan run $runId..."
gh run watch $runId --exit-status
if ($?) { Write-Host "OK deploy valmis — koodi on live." } else { Write-Host "EPAONNISTUI — gh run view $runId" }
