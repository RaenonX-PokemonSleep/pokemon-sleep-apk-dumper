param(
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

$files = Get-ChildItem -Path $DumpedCsPath -Filter "*SyncDatabase.cs" -Recurse

$entries = @(foreach ($file in $files) {
    $tableName            = $null
    $createTableStatement = $null
    $primaryKey           = $null
    $createIndexStatement = $null
    $columns              = [System.Collections.Generic.List[string]]::new()
    $inColumnClass        = $false
    $braceDepth           = -1

    foreach ($line in Get-Content -Path $file.FullName) {
        if (-not $inColumnClass) {
            if ($line -match '^\s*internal static class Column\b') {
                $inColumnClass = $true
                $braceDepth    = -1
            } elseif ($line -match 'private const string m_TableName = "(.+)";') {
                $tableName = $Matches[1]
            } elseif ($line -match 'private const string m_CreateTableStatement = "(.+)";') {
                $createTableStatement = $Matches[1]
            } elseif ($line -match 'private const string LIST_PRIMARY_KEY = "(.*)";') {
                $primaryKey = $Matches[1]
            } elseif ($line -match 'private const string LIST_CREATE_INDEX_STATEMENT = "(.*)";') {
                $createIndexStatement = $Matches[1]
            }
        } else {
            $opens       = ([regex]::Matches($line, '\{')).Count
            $closes      = ([regex]::Matches($line, '\}')).Count
            $braceDepth += $opens - $closes

            if ($braceDepth -lt 0) {
                $inColumnClass = $false
                continue
            }

            if ($line -match '^\s*public static readonly string (\w+);\s*$') {
                $columns.Add($Matches[1])
            }
        }
    }

    if ($null -eq $tableName -or $null -eq $createTableStatement -or
        $null -eq $primaryKey -or $null -eq $createIndexStatement -or
        $columns.Count -eq 0) {
        continue
    }

    [PSCustomObject]@{
        m_TableName                 = $tableName
        m_CreateTableStatement      = $createTableStatement
        LIST_PRIMARY_KEY            = $primaryKey
        LIST_CREATE_INDEX_STATEMENT = $createIndexStatement
        Column                      = $columns.ToArray()
    }
})

$entries |
    Sort-Object -Property m_TableName -Unique |
    ConvertTo-Json -Depth 5 |
    Set-Content -Path $OutputPath -Encoding UTF8

if ($PauseOnEnd) {
    Write-Host "DB CS defined info dump is done."
    Read-Host
}
