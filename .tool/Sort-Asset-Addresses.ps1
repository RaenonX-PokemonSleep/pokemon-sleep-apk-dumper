param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]
    $AddressableAssetsPath,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]
    $OutputPath,

    [ValidateNotNullOrEmpty()]
    [switch]
    $PauseOnEnd = $false
)

Get-Content "$AddressableAssetsPath" | `
    Sort-Object | `
    ForEach-Object { ($_ -Replace "").Trim() } | `
    Where-Object { $_ -Like "public const string*" } | `
    Set-Content "$OutputPath"

if ($PauseOnEnd) {
    Write-Host "Asset address sorting is done."
    Read-Host
}