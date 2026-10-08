# INFO: Removes what install.ps1 and the launcher created on this machine: the Start menu shortcut, the Windows
# Terminal profile, config.json,
# then each account on confirmation (logged out, then its directory deleted).
# ~/.claude and the cloned repos (this one, the shared skills repo) are never touched.

$configPath = Join-Path $PSScriptRoot 'config.json'
$accountsDirectory = Join-Path $env:USERPROFILE '.claude-accounts'
$statePath = Join-Path $accountsDirectory 'launcher_state.json'
$terminalFragmentDirectory = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\Fragments\claude-launcher'

function Read-YesNo($question) {
    while ($true) {
        $answer = (Read-Host "$question (Y/N)").Trim().ToUpper()

        if ($answer -eq 'Y') { return $true }
        if ($answer -eq 'N') { return $false }
    }
}

function Remove-Shortcut {
    $programsDirectory = [Environment]::GetFolderPath('Programs')

    # INFO: Empty when the Start menu folder cannot be resolved, e.g. with USERPROFILE redirected to another folder
    if (-not $programsDirectory) { return }

    $shortcutPath = Join-Path $programsDirectory 'Claude Code.lnk'

    if (Test-Path $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath
        Write-Host "Removed: $shortcutPath"
    }
}

function Remove-TerminalProfile {
    if (Test-Path $terminalFragmentDirectory) {
        Remove-Item -LiteralPath $terminalFragmentDirectory -Recurse
        Write-Host "Removed: $terminalFragmentDirectory"
    }
}

function Remove-Config {
    if (Test-Path $configPath) {
        Remove-Item -LiteralPath $configPath
        Write-Host "Removed: $configPath"
    }
}

function Read-LauncherState {
    if (-not (Test-Path $statePath)) { return $null }

    try {
        return Get-Content $statePath -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-AccountLabel($directory, $state) {
    $name = if ($state -and $state.accounts) { $state.accounts.($directory.Name).name } else { $null }

    if ($name) { return $name }

    try {
        $email = (Get-Content (Join-Path $directory.FullName '.claude.json') -Raw | ConvertFrom-Json).oauthAccount.emailAddress
    } catch {
        $email = $null
    }

    if ($email) { return $email }

    return "Unknown account $($directory.Name)"
}

function Invoke-AccountLogout($directory) {
    if (-not (Test-Path (Join-Path $directory.FullName '.credentials.json'))) { return }

    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        Write-Host '  Claude Code CLI not found, the account is deleted without logging out.' -ForegroundColor Yellow
        return
    }

    $env:CLAUDE_CONFIG_DIR = $directory.FullName

    try {
        claude auth logout *> $null
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR
    }
}

function Remove-Account($directory) {
    Invoke-AccountLogout $directory

    # INFO: Junctions to ~/.claude are removed first, with rmdir which never deletes their target content
    Get-ChildItem -LiteralPath $directory.FullName -Force |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } |
        ForEach-Object { cmd /c rmdir "$($_.FullName)" }

    cmd /c rmdir /s /q "$($directory.FullName)"

    return -not (Test-Path -LiteralPath $directory.FullName)
}

function Remove-Accounts {
    if (-not (Test-Path $accountsDirectory)) { return }

    $state = Read-LauncherState
    $removedIds = @()

    foreach ($directory in Get-ChildItem -LiteralPath $accountsDirectory -Directory) {
        $label = Get-AccountLabel $directory $state

        if (-not (Read-YesNo "Delete the account `"$label`" (logged out, then its folder deleted)?")) {
            continue
        }

        if (Remove-Account $directory) {
            $removedIds += $directory.Name
            Write-Host "Deleted: $label"
        } else {
            Write-Host "Could not fully delete $label, is Claude Code still running with it?" -ForegroundColor Yellow
        }
    }

    if (-not (Get-ChildItem -LiteralPath $accountsDirectory -Directory)) {
        cmd /c rmdir /s /q "$accountsDirectory"
        Write-Host "Removed: $accountsDirectory"
    } elseif ($removedIds -and $state -and $state.accounts) {
        foreach ($id in $removedIds) {
            $state.accounts.PSObject.Properties.Remove($id)
        }

        # INFO: WriteAllText writes UTF-8 without BOM, which Python's json module would reject
        [IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json -Depth 10))
    }
}

if (-not (Read-YesNo 'Uninstall the launcher (Start menu shortcut, Windows Terminal profile, config.json, then accounts on confirmation)?')) {
    return
}

Remove-Shortcut
Remove-TerminalProfile
Remove-Config
Remove-Accounts
