$ErrorActionPreference = "Continue"
$scriptDir = Split-Path -Parent $PSCommandPath
$projectDir = Split-Path -Parent $scriptDir
$backtesterDir = Join-Path $projectDir "backtester"
$runnerScript = Join-Path $scriptDir "run_single_combo.py"
$outFile = Join-Path $scriptDir "combo_results_final.txt"

# 6 binary flags: EM_NO_SKEW, STALE_GUARD, WIND_DOWN, TOM_SKEW_005, IMB_ZERO, NO_DEPTH_CTR
$flagNames = @("EM_NO_SKEW", "STALE_GUARD", "WIND_DOWN", "TOM_SKEW_005", "IMB_ZERO", "NO_DEPTH_CTR")

# Generate all 64 combinations (0-63 as 6-bit binary)
$results = @()

"flags,em_skew,em_heavy,tom_skew,imb_weight,depth_contrarian,stale_guard,wind_down,total,day2,day1,em_d2,em_d1,tom_d2,tom_d1" | Out-File $outFile -Encoding utf8

$startTime = Get-Date
for ($i = 0; $i -lt 64; $i++) {
    $bits = @()
    for ($b = 5; $b -ge 0; $b--) { $bits += [int](($i -shr $b) -band 1) }
    
    $flagStr = ($bits -join "")
    $active = @()
    for ($j = 0; $j -lt 6; $j++) { if ($bits[$j] -eq 1) { $active += $flagNames[$j] } }
    $activeStr = if ($active.Count -gt 0) { $active -join "+" } else { "BASELINE" }
    
    # Map flags to params
    $em_skew = if ($bits[0]) { "1.0" } else { "0.3" }
    $em_heavy = if ($bits[0]) { "1.0" } else { "0.6" }
    $tom_skew = if ($bits[3]) { "0.05" } else { "0.15" }
    $imb_w = if ($bits[4]) { "0.0" } else { "0.5" }
    $depth_c = if ($bits[5]) { "0" } else { "1" }
    $stale = if ($bits[1]) { "1" } else { "0" }
    $wind = if ($bits[2]) { "1" } else { "0" }
    
    $elapsed = ((Get-Date) - $startTime).TotalSeconds
    
    try {
        $output = & python $runnerScript $em_skew $em_heavy $tom_skew $imb_w $depth_c $stale $wind 2>&1
        $resultLine = ($output | Select-String "RESULT\|").Line
        if ($resultLine) {
            $parts = $resultLine.Split("|")
            $total = [double]$parts[1]
            $d2 = [double]$parts[2]
            $d1 = [double]$parts[3]
            $em_d2 = [double]$parts[4]
            $em_d1 = [double]$parts[5]
            $tom_d2 = [double]$parts[6]
            $tom_d1 = [double]$parts[7]
            
            $eta = if ($i -gt 0) { [math]::Round($elapsed / ($i) * (63 - $i)) } else { 0 }
            Write-Host ("[{0,2}/64] {1} {2,-50} Total={3,10:N0}  D-2={4,8:N0}  D-1={5,8:N0}  [{6}s]" -f ($i+1), $flagStr, $activeStr, $total, $d2, $d1, $eta)
            
            "$flagStr,$em_skew,$em_heavy,$tom_skew,$imb_w,$depth_c,$stale,$wind,$total,$d2,$d1,$em_d2,$em_d1,$tom_d2,$tom_d1" | Out-File $outFile -Append -Encoding utf8
        } else {
            Write-Host ("[{0,2}/64] {1} {2,-50} ERROR: no RESULT line" -f ($i+1), $flagStr, $activeStr)
            $errText = ($output | Out-String).Substring(0, [Math]::Min(200, ($output | Out-String).Length))
            Write-Host "  $errText"
        }
    } catch {
        Write-Host ("[{0,2}/64] {1} {2,-50} EXCEPTION: {3}" -f ($i+1), $flagStr, $activeStr, $_.Exception.Message)
    }
}

$totalTime = ((Get-Date) - $startTime).TotalSeconds
Write-Host "`nCompleted 64 combinations in $([math]::Round($totalTime))s ($([math]::Round($totalTime/64, 1))s each)"
Write-Host "Results written to: $outFile"
