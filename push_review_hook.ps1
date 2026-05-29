$stdinContent = [Console]::In.ReadToEnd()
try {
    $data = $stdinContent | ConvertFrom-Json
    $command = $data.tool_input.command
} catch { exit 0 }

if ($command -notmatch 'git push') { exit 0 }

$pushTime = [DateTime]::UtcNow

# Odotetaan että GitHub rekisteroi uuden ajon (max 15s)
$runId = $null
for ($i = 0; $i -lt 5; $i++) {
    Start-Sleep -Seconds 3
    $runs = gh run list --workflow code_review.yml --limit 1 --json databaseId,createdAt 2>$null | ConvertFrom-Json
    if ($runs -and $runs.Count -gt 0) {
        $runCreated = [DateTime]::Parse($runs[0].createdAt)
        if ($runCreated -gt $pushTime.AddSeconds(-30)) {
            $runId = $runs[0].databaseId
            break
        }
    }
}

if (-not $runId) {
    Write-Output "CODE REVIEW: ajoa ei loydy — push ehka epaonnistui tai review ei kaynnistynyt"
    exit 0
}

# Pollaa 30s valein, max 8 min
for ($i = 0; $i -lt 16; $i++) {
    Start-Sleep -Seconds 30
    $run = gh run view $runId --json status,conclusion 2>$null | ConvertFrom-Json
    if ($run.status -eq 'completed') {
        if ($run.conclusion -eq 'success') {
            Write-Output "CODE REVIEW: valmis — lapaisty"
        } else {
            Write-Output "CODE REVIEW: FEILASI ($($run.conclusion)) — tarkista GitHub Actions"
        }
        exit 0
    }
}

Write-Output "CODE REVIEW: timeout 8 minuutin jalkeen — tarkista manuaalisesti"
