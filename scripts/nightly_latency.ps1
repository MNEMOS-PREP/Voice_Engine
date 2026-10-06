<#
.SYNOPSIS
  M11's nightly latency run (day 14): the latency harness on a good network
  and on 2G, each run's grade appended to research/latency/history.jsonl.

.DESCRIPTION
  Needs the stack running (start_all.bat): the shell on :5173, M06 on :8106,
  M11 on :8111 with its voice ready. When it is not - the laptop was asleep,
  the services were stopped - the night is recorded as skipped, not failed:
  a stack that is not up is not a slow one.

  Runs as its own student, so a nightly interview never lands in a real
  student's history, streak or notes.

  -Register   adds a daily Windows task (02:30, this user, catches up after
              sleep). -Unregister removes it. Neither needs admin.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\nightly_latency.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\nightly_latency.ps1 -Register
#>
param(
  [switch]$Register,
  [switch]$Unregister,
  [string]$At = "02:30"
)

$ErrorActionPreference = "Stop"
$TaskName = "AI-Interviewer M11 latency (nightly)"
$Root = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $Root "research\latency"
$History = Join-Path $Out "history.jsonl"
# Not a real student: nightly interviews stay out of everyone's history.
$Candidate = "1a7e0c10-0000-4000-8000-000000000011"

if ($Unregister) {
  try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop; Write-Output "Removed '$TaskName'." }
  catch { Write-Output "'$TaskName' was not registered." }
  exit 0
}

if ($Register) {
  $action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" `
    -WorkingDirectory $Root
  $trigger = New-ScheduledTaskTrigger -Daily -At $At
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "M11 latency harness, good network and 2G; results in research\latency\history.jsonl." -Force | Out-Null
  Write-Output "Registered '$TaskName' daily at $At. Remove with: nightly_latency.ps1 -Unregister"
  exit 0
}

New-Item -ItemType Directory -Force -Path $Out | Out-Null

function Write-History($entry) {
  $line = $entry | ConvertTo-Json -Compress -Depth 6
  Add-Content -Path $History -Value $line -Encoding UTF8
}

function Test-Up($url) {
  try { $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5; return $r.StatusCode -eq 200 }
  catch { return $false }
}

$now = (Get-Date).ToString("o")
$voiceReady = $false
try {
  $engine = Invoke-RestMethod -Uri "http://127.0.0.1:8111/v1/voice/engine" -TimeoutSec 5
  $voiceReady = $engine.state -eq "ready"
} catch { $voiceReady = $false }
$up = (Test-Up "http://localhost:5173/") -and (Test-Up "http://127.0.0.1:8106/health") -and $voiceReady
if (-not $up) {
  Write-History @{ at = $now; skipped = "the stack is not running (shell, M06, or M11's voice)" }
  Write-Output "Skipped: the stack is not running."
  exit 0
}

foreach ($net in @("good", "2g")) {
  $runs = Join-Path $Out "runs"
  New-Item -ItemType Directory -Force -Path $runs | Out-Null
  $before = @(Get-ChildItem -Path $runs -Filter "latency-*.json" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
  $max = if ($net -eq "2g") { "5" } else { "14" }
  & node (Join-Path $PSScriptRoot "latency_harness.mjs") --candidate $Candidate --profile $net `
    --minutes 15 --spoken 3 --max $max --out $runs | Out-Null
  $code = $LASTEXITCODE
  $report = Get-ChildItem -Path $runs -Filter "latency-*.json" |
    Where-Object { $before -notcontains $_.FullName } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  $entry = [ordered]@{ at = $now; network = $net; exit = $code }
  if ($report) {
    $r = Get-Content -Raw -Path $report.FullName | ConvertFrom-Json
    $stages = [ordered]@{}
    foreach ($s in $r.summary.stages) {
      if ($s.n -gt 0) { $stages[$s.name] = [ordered]@{ n = $s.n; p50 = $s.p50; p95 = $s.p95; target = $s.target_ms; met = $s.met } }
    }
    $entry.session = $r.session_id
    $entry.lines = $r.summary.lines
    $entry.stages = $stages
    $entry.handovers = $r.handovers
    $entry.asides = $r.asides_played
    $entry.hold_to_talk = $r.hold_to_talk
    $entry.errors = @($r.errors).Count
  }
  Write-History $entry
  Write-Output ("{0}: exit {1}" -f $net, $code)
}
