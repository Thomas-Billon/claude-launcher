# INFO: Creates the "Claude Code" Start menu shortcut, pointing to the launcher of this repo.
# Paths are deduced from the script location: run it again if the repo is moved.

$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'Claude Code.lnk'
$launcherPath = Join-Path $PSScriptRoot 'claude_launcher.py'

$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcut.Arguments = "-NoExit -Command `"python '$launcherPath'`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.IconLocation = "$(Join-Path $PSScriptRoot 'claude_launcher.ico'),0"
$shortcut.Save()

Write-Host "Shortcut created: $shortcutPath"

# INFO: Shared skills repo: its path is saved in config.json (not versioned), which the launcher reads to fetch & pull it.

function Read-YesNo($question) {
    while ($true) {
        $answer = (Read-Host "$question (Y/N)").Trim().ToUpper()

        if ($answer -eq 'Y') { return $true }
        if ($answer -eq 'N') { return $false }
    }
}

function Read-SkillsRepo {
    while ($true) {
        # INFO: Quotes are stripped since a path copied from the Explorer comes quoted
        $path = (Read-Host 'Local path of the shared skills repo').Trim().Trim('"')

        if ($path -and (Test-Path (Join-Path $path '.git'))) {
            return (Resolve-Path $path).Path
        }

        Write-Host 'Not a git repository, try again.' -ForegroundColor Yellow
    }
}

$configPath = Join-Path $PSScriptRoot 'config.json'

if (Test-Path $configPath) {
    try {
        $currentRepo = (Get-Content $configPath -Raw | ConvertFrom-Json).skills_repo
    } catch {
        $currentRepo = $null
    }

    $currentSetting = if ($currentRepo) { $currentRepo } else { 'disabled' }
    Write-Host "Current shared skills repo: $currentSetting"

    if (Read-YesNo 'Keep this setting?') {
        return
    }
}

$skillsRepo = if (Read-YesNo 'Use a shared skills repo?') { Read-SkillsRepo } else { $null }

# INFO: WriteAllText writes UTF-8 without BOM, which Python's json module would reject
[IO.File]::WriteAllText($configPath, (@{ skills_repo = $skillsRepo } | ConvertTo-Json))

Write-Host "Config saved: $configPath"
