# Crée le raccourci "Claude Code" dans le menu Démarrer, pointant vers le launcher de ce repo.
# Les chemins sont déduits de l'emplacement du script : à relancer si le repo est déplacé.

$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'Claude Code.lnk'
$launcherPath = Join-Path $PSScriptRoot 'claude_launcher.py'

$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcut.Arguments = "-NoExit -Command `"python '$launcherPath'`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.IconLocation = "$(Join-Path $PSScriptRoot 'claude_launcher.ico'),0"
$shortcut.Save()

Write-Host "Raccourci créé : $shortcutPath"
