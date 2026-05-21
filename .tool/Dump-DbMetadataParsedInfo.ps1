param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]
    $MetadataPath,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]
    $DumpedCsPath,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]
    $OutputPath,

    [switch]
    $PauseOnEnd = $false
)

# ── Version ───────────────────────────────────────────────────────────────────
# Derived from current-version.txt that lives alongside global-metadata.dat.
$versionFile    = Join-Path (Split-Path $MetadataPath) 'current-version.txt'
$currentVersion = if (Test-Path $versionFile) { (Get-Content $versionFile -Raw).Trim() } else { 'unknown' }
Write-Host "Version: $currentVersion"

# ── Load existing output to preserve per-query AddedVersion timestamps ────────
# When the script re-runs on a new APK version, SQL statements that already
# exist in the output file keep their original AddedVersion; only brand-new
# statements get stamped with $currentVersion.
$existingSqlVersions = @{}
if (Test-Path $OutputPath) {
    $existing = Get-Content $OutputPath -Raw | ConvertFrom-Json
    if ($existing -is [array]) {
        foreach ($entry in $existing) {
            foreach ($stmt in @($entry.Create) + @($entry.Alter) + @($entry.Drop)) {
                if ($stmt -and $stmt.Sql -and $stmt.AddedVersion) {
                    $existingSqlVersions[$stmt.Sql] = $stmt.AddedVersion
                }
            }
        }
    }
    Write-Host "Loaded $($existingSqlVersions.Count) existing SQL version records"
}

# ── Helpers ───────────────────────────────────────────────────────────────────
function Get-SqlTableName([string]$sql) {
    $name = $null
    if      ($sql -match '(?i)^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?(\w+)"?')    { $name = $Matches[1] }
    elseif  ($sql -match '(?i)^\s*ALTER\s+TABLE\s+"?(\w+)"?')                              { $name = $Matches[1] }
    elseif  ($sql -match '(?i)^\s*DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?"?(\w+)"?')            { $name = $Matches[1] }
    elseif  ($sql -match '(?i)^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+\w+\s+ON\s+"?(\w+)"?')   { $name = $Matches[1] }
    # Table names in this game are always lowercase snake_case; reject anything else
    # (guards against binary noise that happens to follow a SQL keyword)
    if ($name -cmatch '^[a-z][a-z0-9_]+$') { return $name }
    return $null
}

function Get-SqlCategory([string]$sql) {
    if ($sql -match '(?i)^\s*CREATE\b') { return 'Create' }
    if ($sql -match '(?i)^\s*DROP\b')   { return 'Drop'   }
    return 'Alter'
}

# ── 1. Extract SQL DDL from global-metadata.dat ───────────────────────────────
# DDL statements are stored as null-terminated strings in the string pool.
# Each blob may contain multiple semicolon-separated statements.
Write-Host "Reading: $MetadataPath"
$binaryStr = [System.Text.Encoding]::Latin1.GetString(
    [System.IO.File]::ReadAllBytes($MetadataPath))
$nullSplit  = $binaryStr -split [char]0 | Where-Object { $_.Length -gt 0 }

Write-Host "Extracting SQL statements..."
$sqlPattern = '(?:CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)|ALTER\s+TABLE|DROP\s+(?:TABLE|INDEX))[\s\S]+?;'

$allSqlStatements = @($nullSplit |
    Where-Object { $_ -match '\b(CREATE|ALTER|DROP)\s+(TABLE|UNIQUE\s+INDEX|INDEX)\b' } |
    ForEach-Object {
        [regex]::Matches($_, $sqlPattern) | Select-Object -ExpandProperty Value |
            ForEach-Object { $_.Trim() }
    } |
    Sort-Object -Unique)

Write-Host "  $($allSqlStatements.Count) SQL DDL statements"

# Group SQL by table name, then by category (Create / Alter / Drop)
$sqlByTable = @{}
foreach ($sql in $allSqlStatements) {
    $tbl = Get-SqlTableName $sql
    if (-not $tbl) { continue }
    $cat = Get-SqlCategory $sql

    if (-not $sqlByTable.ContainsKey($tbl)) {
        $sqlByTable[$tbl] = @{
            Create = [System.Collections.Generic.List[psobject]]::new()
            Alter  = [System.Collections.Generic.List[psobject]]::new()
            Drop   = [System.Collections.Generic.List[psobject]]::new()
        }
    }
    $version = if ($existingSqlVersions.ContainsKey($sql)) { $existingSqlVersions[$sql] } else { $currentVersion }
    $sqlByTable[$tbl][$cat].Add([PSCustomObject]@{
        Sql          = $sql
        AddedVersion = $version
    })
}
Write-Host "  SQL references $($sqlByTable.Count) distinct tables"

# ── 2. SyncDatabase table names from C# files ─────────────────────────────────
# *SyncDatabase.cs files expose m_TableName as a readable string constant.
Write-Host "Reading SyncDatabase C# files..."
$syncTableNames = @(
    Get-ChildItem -Path $DumpedCsPath -Filter '*SyncDatabase.cs' -Recurse |
    ForEach-Object {
        foreach ($line in Get-Content -Path $_.FullName) {
            if ($line -match 'm_TableName\s*=\s*"([^"]+)"') { $Matches[1] }
        }
    } |
    Sort-Object -Unique)
Write-Host "  $($syncTableNames.Count) SyncDatabase table names"

# ── 3. MasterData table names from MasterDataManagerBase<> subclasses ─────────
# TABLE_NAME is a static readonly field not visible in the C# dump.
# Derive candidates by converting each subclass name to snake_case.
# Two-step algorithm keeps acronyms together (GPPBonus → gpp_bonus, not g_p_p_bonus).
Write-Host "Deriving masterdata table name candidates from *Manager.cs files..."
$masterDataTableNames = @(
    Get-ChildItem -Path $DumpedCsPath -Filter '*Manager.cs' -Recurse |
    ForEach-Object {
        $content = Get-Content -Path $_.FullName -Raw
        if ($content -match '\bMasterDataManagerBase\b') {
            $stripped = $_.BaseName -replace 'DataManager$', '' -replace 'Manager$', ''
            $snake    = $stripped `
                -creplace '([A-Z]+)([A-Z][a-z])', '$1_$2' `
                -creplace '([a-z0-9])([A-Z])',    '$1_$2'
            $snake.TrimStart('_').ToLower()
        }
    } |
    Where-Object { $_ -cmatch '^[a-z][a-z0-9_]{3,79}$' } |
    Sort-Object -Unique)
Write-Host "  $($masterDataTableNames.Count) masterdata table name candidates"

# ── 4. Build output ───────────────────────────────────────────────────────────
$allTableNames = @(
    $syncTableNames +
    $masterDataTableNames +
    @($sqlByTable.Keys)) | Sort-Object -Unique

$output = @($allTableNames | ForEach-Object {
    $name   = $_
    $group  = $sqlByTable[$name]
    $create = if ($group) { @($group.Create) } else { @() }
    $alter  = if ($group) { @($group.Alter)  } else { @() }
    $drop   = if ($group) { @($group.Drop)   } else { @() }

    [PSCustomObject]@{
        TableName = $name
        Create    = $create
        Alter     = $alter
        Drop      = $drop
    }
})

Write-Host "  $($output.Count) total table entries"

# ── Output ────────────────────────────────────────────────────────────────────
$output |
    ConvertTo-Json -Depth 5 |
    Set-Content -Path $OutputPath -Encoding UTF8

Write-Host "Output written to: $OutputPath"

if ($PauseOnEnd) {
    Write-Host "DB metadata parsed info dump is done."
    Read-Host
}
