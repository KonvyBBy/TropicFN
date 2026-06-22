$host.UI.RawUI.WindowTitle = "Konvy Accounts - F7 to Restart"
function Kill-Server { netstat -ano | findstr ":5000 " | ForEach-Object { $p = ($_ -split '\s+')[-1]; if ($p -and $p -ne '0') { try { Stop-Process -Id $p -Force } catch {} } }; Start-Sleep 1.5 }
function Start-Server { Kill-Server; Start-Process powershell -WindowStyle Normal -ArgumentList "-NoExit cd '$PWD'; python web_app.py"; Start-Sleep 3; [Console]::Beep(800,150); Start-Sleep 80; [Console]::Beep(1000,250); Clear-Host; Write-Host "  Konvy Accounts Server" -ForegroundColor Cyan; Write-Host "  [F7] Restart  |  [CTRL+C] Quit" -ForegroundColor DarkGray }
Start-Server
while ($true) { if ([Console]::KeyAvailable) { $k = [Console]::ReadKey($true); if ($k.Key -eq 'F7') { Write-Host "  Restarting..." -ForegroundColor Yellow; Start-Server } }; Start-Sleep -Milliseconds 100 }
