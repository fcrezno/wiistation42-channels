# Boots one channel WAD in Dolphin (test user folder) and captures Dolphin's OWN window
# (PrintWindow on its handle: no mouse, no keyboard, no full-screen capture) at set times.
# Then closes Dolphin through its window (a normal close, so the SD image is written back).
param([string]$Exe = $(if ($env:WS42_DOLPHIN) { $env:WS42_DOLPHIN } else { "Dolphin.exe" }), [string]$Wad, [int[]]$At = @(8, 20, 35, 50), [string]$Name = "test", [string]$User = "dolphin-user", [string[]]$Boot = @())
$root = Split-Path $PSScriptRoot
$user = Join-Path $root $User
$exe = $Exe   # Dolphin.exe: -Exe or env WS42_DOLPHIN
$keep = Join-Path $root "out\shots_$Name"
New-Item -ItemType Directory -Force -Path $keep | Out-Null

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  public struct RECT { public int L, T, R, B; }
}
"@

$bootArgs = if ($Boot.Count) { $Boot } else { @("-e", "`"$Wad`"") }
$p = Start-Process -FilePath $exe -ArgumentList (@("-u", "`"$user`"", "-b") + $bootArgs) -PassThru
$t0 = Get-Date
foreach ($s in $At) {
    while (((Get-Date) - $t0).TotalSeconds -lt $s -and -not $p.HasExited) { Start-Sleep -Milliseconds 250 }
    if ($p.HasExited) { "Dolphin exited at $([int]((Get-Date)-$t0).TotalSeconds) s"; break }
    $p.Refresh()
    $h = $p.MainWindowHandle
    if ($h -eq [IntPtr]::Zero) { "no window at $s s"; continue }
    $r = New-Object W+RECT
    [void][W]::GetWindowRect($h, [ref]$r)
    $w = $r.R - $r.L; $hh = $r.B - $r.T
    if ($w -le 0 -or $hh -le 0) { "window has no size at $s s"; continue }
    $bmp = New-Object System.Drawing.Bitmap $w, $hh
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $dc = $g.GetHdc()
    [void][W]::PrintWindow($h, $dc, 2)
    $g.ReleaseHdc($dc); $g.Dispose()
    $f = Join-Path $keep ("t{0:d2}.png" -f $s)
    $bmp.Save($f, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    "captured $f ($w x $hh), title: $($p.MainWindowTitle)"
}
if (-not $p.HasExited) {
    [void]$p.CloseMainWindow()
    if (-not $p.WaitForExit(15000)) { Stop-Process -Id $p.Id -Force; "Dolphin had to be stopped" } else { "Dolphin closed normally" }
}
