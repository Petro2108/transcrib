$pythonw = "C:\Python314\pythonw.exe"
$script  = "C:\Users\uuit\Documents\Projects\transcrib\transcriber.py"
$cmd     = "`"$pythonw`" `"$script`""
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Transcrib" -Value $cmd
Write-Host "OK: $cmd"
