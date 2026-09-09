# DB information dump

`main.py` combines generated C# declarations, native masterdata field assignments,
and migration SQL into `DbInfo.json`. It replaces `Dump-DbCsDefinedInfo.ps1` and
`Dump-DbMetadataParsedInfo.ps1`. No APK/game code or extracted SQL is executed.

## Run

Use Python 3.12+ and install the dependencies into the selected interpreter:

```powershell
python -m pip install -r .tool/db_info/requirements.txt
python .tool/db_info/main.py `
  --binary libil2cpp.so `
  --metadata global-metadata.dat `
  --version-file current-version.txt `
  --unity-version-file current-version-unity.txt `
  --cpp2il .tool/Cpp2IL-d526068.exe `
  --cs-dir .cppDump/DiffableCs/PSMain `
  --work-dir .cppDump/db-info-work `
  --legacy-info ../pokemon-sleep-dumped-cs/DbMetadataParsedInfo.json `
  --output ../pokemon-sleep-dumped-cs/DbInfo.json
```

Generate the C# input using the existing pipeline's Cpp2IL `diffable-cs` command
from the **same binary, metadata, and Unity version**. Pass the original output,
before `Cleanup-Meta.ps1` removes field offsets. The extractor generates fresh
ISIL output in a temporary directory on every invocation, then removes it.

The Azure job selects Python with `UsePythonVersion@0`, installs dependencies
globally with `python -m pip install`, and runs `python .tool/db_info/main.py`.
`Cache@2` restores pip downloads using OS, Python version, and requirements hash.
Installation runs on cache hits too: downloaded wheels are not installed packages.
Both publishing steps exit successfully without committing or pushing when the
staged diff is empty. Git checkout, staging, commit, and push errors still fail.

## JSON contract

- `SchemaVersion`: output format version; currently 1.
- `ApkVersion` and `Inputs`: source version and SHA256 fingerprints.
- `Tables`: sorted by `(Database.Name, TableName)`. Identical table names in
  different databases are separate records. Column names are case-preserving.
- `Database`: connection family, logical category, and supporting evidence.
  Masterdata and user classification is checked against the base classes' native
  database calls. Other classifications identify explicit migration namespaces;
  they do not claim the table is present in a currently deployed database.
- `Columns`: client columns from native static fields or C# CREATE declarations.
  Sorted by name, **not physical database order**. Native-only columns do not
  invent SQL types, constraints, or property mappings. Declared type spelling is
  preserved instead of replacing BIGINT, BOOLEAN, etc. with SQLite affinities.
- `Declarations`: original generated CREATE SQL, key/index declarations, and class.
- `Migrations`: original SQL, owner class, Up/Down direction, and statement ordinal.
  They are historical code observations, not an automatically reconstructed current
  schema. A rollback DROP does not mark a currently used table as deleted.
- `Unresolved`: table-local extraction limitations.
- `UnresolvedManagers`, `UnresolvedMigrations`, `UnresolvedSql`: retained evidence
  that cannot safely be assigned or parsed. Unknown SQL ownership stays unknown;
  no class-name-to-snake-case table names are generated.

## Added and Modified

Tables, columns, declarations, and migration statements have `Added` and `Modified`.
New records get the current APK version in **both** fields. Matching records retain
`Added`; `Modified` changes only when record content changes. Version annotations
themselves are excluded from comparison. A child change also modifies its table;
a different APK version or binary address alone does not modify a table.

Identity is database + table name, then column field (or declared column name),
declaration class, or migration class + direction + statement ordinal. Renaming a
table is a new identity. Removing a column modifies its table; removed records are
not emitted as current observations. Reordering migration statements can change
their ordinal identity.

On the first run without `DbInfo.json`, `--legacy-info` imports `AddedVersion`
from `DbMetadataParsedInfo.json`. Matching SQL records receive that version in
both `Added` and `Modified`, including unresolved SQL. Matches ignore only outer
whitespace and an optional final semicolon; identifier case, types, and literal
values are preserved. A matching table starts with the earliest child `Added`
and latest child `Modified`. New records and columns without their own legacy
dates start at the current version; table-name guesses alone never backdate them.
These remain first-observed dates, not proof of a schema's introduction date.

The legacy file is read only when there is no unified catalog. Later runs read
and atomically replace `DbInfo.json`, preserving imported dates. A missing legacy
file simply establishes the baseline at the current APK version.

## Native extraction limits

Supports little-endian ARM64 ELF and IL2CPP metadata v31. Uses pyelftools for ELF
segments/relocations and Capstone for actual native instruction decoding. Cpp2IL
provides method locations and named calls; its displayed disassembly bytes are
not used because that build misaddresses some ELF instruction ranges.

The reader propagates literals through registers and stack slots, joins branch
states conservatively, and matches static stores to declared field offsets.
Unsupported register writes invalidate values. Encrypted table names, unresolved
branches, computed strings, and unsupported SQL stay explicit limitations.
Each nonempty unresolved category (including partially resolved tables) emits an
Azure `task.logissue` warning when `TF_BUILD=true`, and a console warning locally.
These cases exit successfully and keep the partial JSON available for review.
Malformed inputs, missing base database connections, conflicting confirmed column
evidence, and incompatible previous schemas fail before replacing the output.

Python bytecode is excluded by `__pycache__/` and `*.py[cod]` Git ignore rules.
