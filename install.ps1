# INFO: Installs the launcher on this machine:
# 1. the "Claude Code" Start menu shortcut, pointing to the launcher of this repo (run again if the repo is moved);
# 2. the shared skills repo: an existing local one, a new one created from the base repo template, or none.
#    Its path is saved in config.json (not versioned), which the launcher reads to sync it;
# 3. the global CLAUDE.md, turned into a relay to the CLAUDE.md of the skills repo;
# 4. the install.ps1 of the skills repo.
# Every git action is shown, then asked first.

$baseRepo = 'Thomas-Billon/claude-skills-base'
$configPath = Join-Path $PSScriptRoot 'config.json'
$globalClaudeMdPath = Join-Path $env:USERPROFILE '.claude\CLAUDE.md'

function Read-YesNo($question) {
    while ($true) {
        $answer = (Read-Host "$question (Y/N)").Trim().ToUpper()

        if ($answer -eq 'Y') { return $true }
        if ($answer -eq 'N') { return $false }
    }
}

function Read-Path($question) {
    # INFO: Quotes are stripped since a path copied from the Explorer comes quoted
    return (Read-Host $question).Trim().Trim('"')
}

function Read-TextFile($path) {
    # INFO: ReadAllText rather than Get-Content -Raw, which returns $null for an empty file
    if (-not (Test-Path $path -PathType Leaf)) { return '' }

    return [IO.File]::ReadAllText($path)
}

function Install-Shortcut {
    $programsDirectory = [Environment]::GetFolderPath('Programs')

    # INFO: Empty when the Start menu folder cannot be resolved, e.g. with USERPROFILE redirected to another folder
    if (-not $programsDirectory) {
        Write-Host 'Start menu folder not found, shortcut not created.' -ForegroundColor Yellow
        return
    }

    $shortcutPath = Join-Path $programsDirectory 'Claude Code.lnk'
    $launcherPath = Join-Path $PSScriptRoot 'claude_launcher.py'

    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $shortcut.Arguments = "-NoExit -Command `"python '$launcherPath'`""
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.IconLocation = "$(Join-Path $PSScriptRoot 'claude_launcher.ico'),0"
    $shortcut.Save()

    Write-Host "Shortcut created: $shortcutPath"
}

function Test-KeepCurrentConfig {
    if (-not (Test-Path $configPath)) { return $false }

    try {
        $currentRepo = (Get-Content $configPath -Raw | ConvertFrom-Json).skills_repo
    } catch {
        $currentRepo = $null
    }

    $currentSetting = if ($currentRepo) { $currentRepo } else { 'disabled' }
    Write-Host "Current shared skills repo: $currentSetting"

    return Read-YesNo 'Keep this setting?'
}

function Select-ExistingRepo {
    while ($true) {
        $path = Read-Path 'Local path of the shared skills repo'

        if ($path -and (Test-Path (Join-Path $path '.git'))) {
            return (Resolve-Path $path).Path
        }

        Write-Host 'Not a git repository, try again.' -ForegroundColor Yellow
    }
}

function Get-RepoNameFromUrl($url) {
    # INFO: Works for HTTPS and SSH URLs (git@github.com:user/repo.git), with or without the .git suffix
    return ($url.TrimEnd('/', '\') -split '[/\\]')[-1] -replace '\.git$', ''
}

function New-SkillsRepoFromTemplate {
    # INFO: The GitHub repo is created by the user in the browser, so the script needs no GitHub access, only git
    $templateUrl = "https://github.com/$baseRepo/generate"
    Write-Host "Opening $templateUrl in the browser:"
    Write-Host '  create your repo from the template there (private recommended), then copy its URL.'
    Start-Process $templateUrl

    $url = (Read-Host 'URL of your new repo (leave empty to go back)').Trim()

    if (-not $url) { return $null }

    $parent = Read-Path 'Local folder to clone it into'

    if (-not $parent -or -not (Test-Path $parent -PathType Container)) {
        Write-Host 'Folder not found.' -ForegroundColor Yellow
        return $null
    }

    $repoPath = Join-Path (Resolve-Path $parent).Path (Get-RepoNameFromUrl $url)

    if (Test-Path $repoPath) {
        Write-Host "$repoPath already exists." -ForegroundColor Yellow
        return $null
    }

    Write-Host "Command: git clone $url $repoPath"

    if (-not (Read-YesNo 'Clone it?')) {
        return $null
    }

    # INFO: Sent to the host, otherwise the output of git would be returned by the function along the path
    git clone $url $repoPath | Out-Host

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $repoPath '.git'))) {
        Write-Host 'Clone failed, check the URL and your access to the repo.' -ForegroundColor Yellow
        return $null
    }

    return $repoPath
}

function Select-SkillsRepo {
    while ($true) {
        Write-Host 'Shared skills repo:'
        Write-Host '  1. Use an existing local repo'
        Write-Host "  2. Create a new repo from the $baseRepo template"
        Write-Host '  3. No shared skills repo'
        $choice = (Read-Host 'Choice (1/2/3)').Trim()

        if ($choice -eq '1') { return Select-ExistingRepo }
        if ($choice -eq '3') { return $null }

        if ($choice -eq '2') {
            $repoPath = New-SkillsRepoFromTemplate

            if ($repoPath) { return $repoPath }
        }
    }
}

function Save-Config($skillsRepo) {
    # INFO: WriteAllText writes UTF-8 without BOM, which Python's json module would reject
    [IO.File]::WriteAllText($configPath, (@{ skills_repo = $skillsRepo } | ConvertTo-Json))

    Write-Host "Config saved: $configPath"
}

function Write-ClaudeMdRelay($relayContent) {
    # INFO: WriteAllText writes UTF-8 without BOM, like the install.ps1 of the skills repo
    [IO.File]::WriteAllText($globalClaudeMdPath, "$relayContent`n")

    Write-Host '~/.claude/CLAUDE.md now references the CLAUDE.md of the repo.'
}

# INFO: ~/.claude/CLAUDE.md must become a relay importing the CLAUDE.md of the repo. Without one, the install.ps1
# of the skills repo creates both. An existing one is imported into the repo when the repo has none (an empty one counts
# as none): two different files can only be merged by hand.
function Sync-GlobalClaudeMd($repoPath) {
    if (-not (Test-Path $globalClaudeMdPath -PathType Leaf)) { return }

    $repoClaudeMdPath = Join-Path $repoPath 'CLAUDE.md'
    $relayContent = '@' + ($repoClaudeMdPath -replace '\\', '/')
    $globalContent = (Read-TextFile $globalClaudeMdPath).Trim()

    if ($globalContent -eq $relayContent) { return }

    # INFO: A relay to another file (e.g. a previous skills repo) holds no rules itself, the file it references does
    $sourcePath = $globalClaudeMdPath

    if ($globalContent -match '^@(\S+)$') {
        $sourcePath = $Matches[1] -replace '^~', $env:USERPROFILE
    }

    $hasRepoRules = [bool](Read-TextFile $repoClaudeMdPath).Trim()
    $hasSourceRules = [bool](Read-TextFile $sourcePath).Trim()

    if ($sourcePath -ne $globalClaudeMdPath -and ($hasRepoRules -or -not $hasSourceRules)) {
        Write-Host "~/.claude/CLAUDE.md references $sourcePath."

        if (Read-YesNo 'Make it reference the CLAUDE.md of this repo instead?') {
            Write-ClaudeMdRelay $relayContent
        }

        return
    }

    if ($hasRepoRules) {
        Write-Host 'A CLAUDE.md exists both in ~/.claude and in the repo, they cannot be merged automatically:' -ForegroundColor Yellow
        Write-Host "  merge the rules of $globalClaudeMdPath into $repoClaudeMdPath, delete $globalClaudeMdPath," -ForegroundColor Yellow
        Write-Host '  then run the install.ps1 of the skills repo again.' -ForegroundColor Yellow
        return
    }

    Write-Host "Global rules found in $sourcePath, the repo has no CLAUDE.md yet."

    if (-not (Read-YesNo 'Import them into the CLAUDE.md of the repo, then make ~/.claude/CLAUDE.md reference it?')) {
        return
    }

    $sourceContent = Read-TextFile $sourcePath
    [IO.File]::WriteAllText($repoClaudeMdPath, $sourceContent)

    if ((Read-TextFile $repoClaudeMdPath) -ne $sourceContent) {
        Write-Host 'Import failed, ~/.claude/CLAUDE.md is left untouched.' -ForegroundColor Yellow
        return
    }

    Write-Host "Imported: $repoClaudeMdPath (not committed yet, the launcher will offer to)"
    Write-ClaudeMdRelay $relayContent
}

function Invoke-SkillsInstall($repoPath) {
    $installScript = Join-Path $repoPath 'install.ps1'

    if (-not (Test-Path $installScript -PathType Leaf)) { return }

    Write-Host "The skills repo has an install.ps1: in $baseRepo, it links the skills into ~/.claude/skills,"
    Write-Host 'creates the ~/.claude/CLAUDE.md relay and adds the base repo as the upstream git remote.'

    if (Read-YesNo 'Run it now?') {
        & $installScript
    }
}

Install-Shortcut

if (Test-KeepCurrentConfig) {
    return
}

$skillsRepo = Select-SkillsRepo
Save-Config $skillsRepo

if ($skillsRepo) {
    Sync-GlobalClaudeMd $skillsRepo
    Invoke-SkillsInstall $skillsRepo
}
