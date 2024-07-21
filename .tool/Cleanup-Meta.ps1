param(
    [Parameter(mandatory=$true)]
    [ValidateNotNullOrEmpty()]
    [string]
    $CsFileDir,

    [ValidateNotNullOrEmpty()]
    [switch]
    $PauseOnEnd = $false
)

$ReplaceTargetRegexList = @(
    # [Token(Token = "0x4002C36")]
    '.*\[Token\(Token = "0x.*"\)\]\r\n'
    # # [Address(RVA = "0x44E8F94", Offset = "0x44E8F94", VA = "0x44E8F94")]
    '.*\[Address\(RVA = "0x.*", Offset = "0x.*", VA = "0x.*"\)\]\r\n'
    # [CompilerGenerated]
    '.*\[CompilerGenerated\]\r\n'
    # [DebuggerHidden]
    '.*\[DebuggerHidden\]\r\n'
    # [SerializeField]
    '.*\[SerializeField\]\r\n'
    # [SyncField]
    '.*\[SyncField\]\r\n'
	# [SyncList(DataType = typeof(UserMainDreamGiftDataUnit), AlwaysInsert = true)]
    '.*\[SyncList.*\]\r\n'
    # [SyncBinder]
    '.*\[SyncBinder\]\r\n'
    # [SyncListIdentifier]
    # [SyncListIdentifier(IsPrimaryKey = true)]
    '.*\[SyncListIdentifier.*\]\r\n'
    # [SyncBindedIdentifier]
    '.*\[SyncBindedIdentifier\]\r\n'
    # [IgnoreDataMember]
    '.*\[IgnoreDataMember\]\r\n'
    # [FieldOffset(Offset = "0x60")]
    '.*\[FieldOffset\(Offset = "0x.*"\)\]\r\n'
    # [StructLayout(3)]
    '.*\[StructLayout\(.*\)\]\r\n'
    # [Il2CppDummyDll.FieldOffset(Offset = "0x0")]
    '.*\[Il2CppDummyDll.FieldOffset\(Offset = "0x.*"\)\]\r\n'
    # [Obsolete("UIMaterial component is deprecated. Please use UIMaterialValue instead.")]
    '.*\[Obsolete\(".*"\)\]\r\n'
    # [Tooltip("Line mode only")]
    '.*\[Tooltip\(".*"\)\]\r\n'
    # [RequireComponent(typeof(DraggableCamera))]
    '.*\[RequireComponent\(".*"\)\]\r\n'
    # [Space(5f)]
    '.*\[Space\(.*\)\]\r\n'
    # [DisallowMultipleComponent]
    '.*\[DisallowMultipleComponent\]\r\n'
)

function Format-File {
    param (
        [Parameter(mandatory=$true)]
        [ValidateNotNullOrEmpty()]
        [string]
        $FilePath
    )

    Write-Host -ForegroundColor Cyan "Cleaning up $FilePath"

    foreach ($private:ReplaceTargetRegex in $ReplaceTargetRegexList) {
        (Get-Content -Path $FilePath -Raw) -Replace $private:ReplaceTargetRegex, "" | Set-Content $FilePath
    }

    # Remove all ending newlines
    (Get-Content -Path $FilePath -Raw).TrimEnd() | Set-Content $FilePath
}

Get-ChildItem -Path "$CsFileDir\*" -Include "*.cs" -Force -Recurse | ForEach-Object {
    Format-File -FilePath $_.FullName
}

if ($PauseOnEnd) {
    Write-Host "C# file dump cleanup is done."
    Read-Host
}