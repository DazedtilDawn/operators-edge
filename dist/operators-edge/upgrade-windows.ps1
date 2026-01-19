# Operator's Edge v8.0 - Windows Upgrade Script
# Run this from the extracted operators-edge folder

param(
    [string]$TargetProject = "",
    [switch]$Help,
    [switch]$Force,
    [switch]$DryRun
)

# Don't stop on errors - we handle them ourselves
$ErrorActionPreference = "Continue"

# Track state for rollback
$Script:BackupsMade = @()
$Script:OperationsComplete = @()

function Show-Help {
    Write-Host @"

Operator's Edge v8.0 - Windows Upgrade Script (Failproof Edition)
==================================================================

USAGE:
  .\upgrade-windows.ps1 -TargetProject "C:\path\to\your\project"

OPTIONS:
  -TargetProject  Path to your project (required)
  -Force          Skip confirmation prompts
  -DryRun         Show what would be done without making changes
  -Help           Show this help

WHAT IT DOES:
  1. Validates source and target directories
  2. Backs up your active_context.yaml (with timestamp)
  3. Copies v8.0 hooks to .claude/hooks/
  4. Updates commands in .claude/commands/
  5. Preserves your .proof/ metrics data
  6. Runs setup.py to update settings.json
  7. Verifies all files were copied correctly

ROLLBACK:
  If anything fails, backups are preserved and you're told how to restore.

EXAMPLES:
  .\upgrade-windows.ps1 -TargetProject "C:\Dev\MyProject"
  .\upgrade-windows.ps1 -TargetProject . -DryRun
  .\upgrade-windows.ps1 -TargetProject "C:\Dev\MyProject" -Force

"@
}

function Write-Step {
    param([string]$Step, [string]$Message)
    Write-Host "[$Step] $Message" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Message)
    Write-Host "      $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "      WARNING: $Message" -ForegroundColor Yellow
}

function Write-Failure {
    param([string]$Message)
    Write-Host "      ERROR: $Message" -ForegroundColor Red
}

function Find-Python {
    # Try different Python commands in order of preference
    $pythonCommands = @("python", "python3", "py -3", "py")

    foreach ($cmd in $pythonCommands) {
        try {
            $parts = $cmd -split ' '
            $exe = $parts[0]
            $args = if ($parts.Length -gt 1) { $parts[1..($parts.Length-1)] } else { @() }

            $result = & $exe @args --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $result -match "Python 3") {
                return $cmd
            }
        } catch {
            continue
        }
    }
    return $null
}

function Backup-File {
    param([string]$FilePath, [string]$Suffix = "pre-v8")

    if (-not (Test-Path $FilePath)) {
        return $null
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupPath = "$FilePath.$Suffix.$timestamp.bak"

    try {
        Copy-Item $FilePath $backupPath -Force
        $Script:BackupsMade += @{Original = $FilePath; Backup = $backupPath}
        return $backupPath
    } catch {
        Write-Failure "Failed to backup $FilePath : $_"
        return $null
    }
}

function Verify-Copy {
    param([string]$Source, [string]$Destination, [string]$Pattern = "*")

    $sourceFiles = Get-ChildItem -Path $Source -Filter $Pattern -File -ErrorAction SilentlyContinue
    $destFiles = Get-ChildItem -Path $Destination -Filter $Pattern -File -ErrorAction SilentlyContinue

    if ($null -eq $sourceFiles) { return $true }  # Nothing to copy is OK

    $sourceCount = @($sourceFiles).Count
    $destCount = @($destFiles).Count

    if ($sourceCount -ne $destCount) {
        return $false
    }

    foreach ($sf in $sourceFiles) {
        $destFile = Join-Path $Destination $sf.Name
        if (-not (Test-Path $destFile)) {
            return $false
        }
    }

    return $true
}

function Show-Rollback {
    if ($Script:BackupsMade.Count -gt 0) {
        Write-Host ""
        Write-Host "ROLLBACK INSTRUCTIONS:" -ForegroundColor Cyan
        Write-Host "Your original files are preserved. To restore:" -ForegroundColor White
        foreach ($backup in $Script:BackupsMade) {
            Write-Host "  Copy-Item '$($backup.Backup)' '$($backup.Original)' -Force"
        }
    }
}

# =============================================================================
# MAIN SCRIPT
# =============================================================================

if ($Help -or [string]::IsNullOrWhiteSpace($TargetProject)) {
    Show-Help
    exit 0
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Operator's Edge v8.0 Upgrade" -ForegroundColor Cyan
if ($DryRun) {
    Write-Host " (DRY RUN - no changes will be made)" -ForegroundColor Magenta
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get source directory (where this script lives)
$SourceDir = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($SourceDir)) {
    $SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($SourceDir)) {
    $SourceDir = Get-Location
}

# Resolve target - handle relative paths safely
if ($TargetProject -eq ".") {
    $TargetDir = Get-Location
} else {
    try {
        # Try to resolve if it exists
        if (Test-Path $TargetProject) {
            $TargetDir = (Resolve-Path $TargetProject).Path
        } else {
            $TargetDir = $TargetProject
        }
    } catch {
        $TargetDir = $TargetProject
    }
}

Write-Host "Source: $SourceDir"
Write-Host "Target: $TargetDir"
Write-Host ""

# =============================================================================
# STEP 0: VALIDATION
# =============================================================================

Write-Step "0/6" "Validating..."

# Check source has hooks
$SourceHooks = Join-Path $SourceDir ".claude\hooks"
if (-not (Test-Path $SourceHooks)) {
    Write-Failure "Source does not contain .claude\hooks"
    Write-Failure "Make sure you're running from the extracted operators-edge folder"
    exit 1
}

$sourceHookCount = @(Get-ChildItem "$SourceHooks\*.py" -ErrorAction SilentlyContinue).Count
if ($sourceHookCount -eq 0) {
    Write-Failure "No Python files in source .claude\hooks"
    exit 1
}
Write-Success "Source has $sourceHookCount hook modules"

# Check target exists
if (-not (Test-Path $TargetDir)) {
    Write-Failure "Target project does not exist: $TargetDir"
    exit 1
}
Write-Success "Target directory exists"

# Check Python
$pythonCmd = Find-Python
if ($null -eq $pythonCmd) {
    Write-Warning "Python 3 not found - setup.py will be skipped"
    Write-Warning "Install Python 3 and run setup.py manually later"
} else {
    Write-Success "Python found: $pythonCmd"
}

# Confirm if not forced
if (-not $Force -and -not $DryRun) {
    Write-Host ""
    $confirm = Read-Host "Proceed with upgrade? (y/N)"
    if ($confirm -notmatch "^[Yy]") {
        Write-Host "Upgrade cancelled." -ForegroundColor Yellow
        exit 0
    }
}

# =============================================================================
# STEP 1: BACKUP
# =============================================================================

Write-Step "1/6" "Creating backups..."

$ContextFile = Join-Path $TargetDir "active_context.yaml"
if (Test-Path $ContextFile) {
    if ($DryRun) {
        Write-Success "Would backup: active_context.yaml"
    } else {
        $backup = Backup-File $ContextFile
        if ($backup) {
            Write-Success "Backed up to: $backup"
        } else {
            Write-Warning "Failed to backup active_context.yaml - continuing anyway"
        }
    }
} else {
    Write-Success "No active_context.yaml to backup (new installation)"
}

# Also backup CLAUDE.md if it exists and differs
$TargetClaudeMd = Join-Path $TargetDir "CLAUDE.md"
if (Test-Path $TargetClaudeMd) {
    if ($DryRun) {
        Write-Success "Would backup: CLAUDE.md"
    } else {
        $backup = Backup-File $TargetClaudeMd
        if ($backup) {
            Write-Success "Backed up CLAUDE.md"
        }
    }
}

$Script:OperationsComplete += "backup"

# =============================================================================
# STEP 2: CREATE DIRECTORIES
# =============================================================================

Write-Step "2/6" "Creating directories..."

$TargetHooks = Join-Path $TargetDir ".claude\hooks"
$TargetCommands = Join-Path $TargetDir ".claude\commands"
$TargetProof = Join-Path $TargetDir ".proof"

$dirsToCreate = @($TargetHooks, $TargetCommands, $TargetProof)

foreach ($dir in $dirsToCreate) {
    if (-not (Test-Path $dir)) {
        if ($DryRun) {
            Write-Success "Would create: $dir"
        } else {
            try {
                New-Item -ItemType Directory -Path $dir -Force | Out-Null
                Write-Success "Created: $dir"
            } catch {
                Write-Failure "Failed to create $dir : $_"
                Show-Rollback
                exit 1
            }
        }
    } else {
        Write-Success "Exists: $dir"
    }
}

$Script:OperationsComplete += "directories"

# =============================================================================
# STEP 3: COPY HOOKS
# =============================================================================

Write-Step "3/6" "Copying v8.0 hooks..."

if ($DryRun) {
    Write-Success "Would copy $sourceHookCount Python modules to .claude\hooks\"
} else {
    try {
        Copy-Item -Path "$SourceHooks\*" -Destination $TargetHooks -Force -Recurse -ErrorAction Stop

        # Verify
        if (Verify-Copy $SourceHooks $TargetHooks "*.py") {
            $copiedCount = @(Get-ChildItem "$TargetHooks\*.py").Count
            Write-Success "Copied and verified $copiedCount Python modules"
        } else {
            Write-Warning "Copy completed but verification found mismatches"
        }
    } catch {
        Write-Failure "Failed to copy hooks: $_"
        Show-Rollback
        exit 1
    }
}

$Script:OperationsComplete += "hooks"

# =============================================================================
# STEP 4: COPY COMMANDS
# =============================================================================

Write-Step "4/6" "Copying commands..."

$SourceCommands = Join-Path $SourceDir ".claude\commands"

if (Test-Path $SourceCommands) {
    if ($DryRun) {
        $cmdCount = @(Get-ChildItem "$SourceCommands\*.md" -ErrorAction SilentlyContinue).Count
        Write-Success "Would copy $cmdCount slash commands"
    } else {
        try {
            Copy-Item -Path "$SourceCommands\*" -Destination $TargetCommands -Force -Recurse -ErrorAction Stop

            if (Verify-Copy $SourceCommands $TargetCommands "*.md") {
                $copiedCount = @(Get-ChildItem "$TargetCommands\*.md").Count
                Write-Success "Copied and verified $copiedCount slash commands"
            } else {
                Write-Warning "Copy completed but verification found mismatches"
            }
        } catch {
            Write-Failure "Failed to copy commands: $_"
            Write-Warning "Continuing - hooks are more important"
        }
    }
} else {
    Write-Warning "No commands folder in source - skipping"
}

$Script:OperationsComplete += "commands"

# =============================================================================
# STEP 5: COPY DOCS
# =============================================================================

Write-Step "5/6" "Copying documentation..."

$docFiles = @("CLAUDE.md", "CHANGELOG.md")

foreach ($doc in $docFiles) {
    $sourceDoc = Join-Path $SourceDir $doc
    $targetDoc = Join-Path $TargetDir $doc

    if (Test-Path $sourceDoc) {
        if ($DryRun) {
            Write-Success "Would copy: $doc"
        } else {
            try {
                Copy-Item -Path $sourceDoc -Destination $targetDoc -Force -ErrorAction Stop
                Write-Success "Copied: $doc"
            } catch {
                Write-Warning "Failed to copy $doc - continuing"
            }
        }
    }
}

# Copy setup.py if it exists
$sourceSetup = Join-Path $SourceDir "setup.py"
$targetSetup = Join-Path $TargetDir "setup.py"
if (Test-Path $sourceSetup) {
    if ($DryRun) {
        Write-Success "Would copy: setup.py"
    } else {
        try {
            Copy-Item -Path $sourceSetup -Destination $targetSetup -Force -ErrorAction Stop
            Write-Success "Copied: setup.py"
        } catch {
            Write-Warning "Failed to copy setup.py - continuing"
        }
    }
}

$Script:OperationsComplete += "docs"

# =============================================================================
# STEP 6: RUN SETUP
# =============================================================================

Write-Step "6/6" "Configuring settings..."

if ($null -eq $pythonCmd) {
    Write-Warning "Python not found - skipping setup.py"
    Write-Warning "Run this manually later: python setup.py"
} elseif ($DryRun) {
    Write-Success "Would run: $pythonCmd setup.py"
} else {
    $setupPy = Join-Path $TargetDir "setup.py"
    if (Test-Path $setupPy) {
        Push-Location $TargetDir
        try {
            $parts = $pythonCmd -split ' '
            $exe = $parts[0]
            $args = @()
            if ($parts.Length -gt 1) { $args += $parts[1..($parts.Length-1)] }
            $args += "setup.py"

            $result = & $exe @args 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Settings configured successfully"
            } else {
                Write-Warning "setup.py returned non-zero exit code"
                Write-Warning "Output: $result"
            }
        } catch {
            Write-Warning "setup.py failed: $_"
            Write-Warning "You may need to run it manually"
        } finally {
            Pop-Location
        }
    } else {
        Write-Warning "setup.py not found in target - skipping"
    }
}

$Script:OperationsComplete += "setup"

# =============================================================================
# COMPLETE
# =============================================================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($DryRun) {
    Write-Host " Dry Run Complete!" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "No changes were made. Run without -DryRun to apply."
} else {
    Write-Host " Upgrade Complete!" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Operations completed: $($Script:OperationsComplete -join ', ')"

    if ($Script:BackupsMade.Count -gt 0) {
        Write-Host ""
        Write-Host "Backups created:" -ForegroundColor Yellow
        foreach ($backup in $Script:BackupsMade) {
            Write-Host "  $($backup.Backup)"
        }
    }
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Open Claude Code in your project"
Write-Host "  2. Try: /edge metrics  (see effectiveness report)"
Write-Host "  3. Try: /edge `"your objective`""
Write-Host ""
Write-Host "v8.0 Features now active:" -ForegroundColor Green
Write-Host "  - Drift Detection (warns on file churn, command repeats)"
Write-Host "  - Context Monitor (warns at 75%+ token usage)"
Write-Host "  - Codebase Knowledge (remembers what fixed errors)"
Write-Host "  - Session Handoffs (passes context between sessions)"
Write-Host "  - Outcome Tracking (learns which fixes actually work)"
Write-Host ""

exit 0
