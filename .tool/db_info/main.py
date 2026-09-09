"""Extract the client-observed database catalog from a matching APK/C# dump."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile

from binary import Binary
from classification import verify_connections
from declarations import extract_declarations
from discovery import classes
from history import apply_history
from legacy import seed_history
from managers import extract_managers
from merge import merge_tables, unattributed_sql
from methods import Methods
from migrations import extract_migrations, metadata_sql
from reporting import report_unresolved

SCHEMA_VERSION = 1


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'metadata', 'version-file', 'unity-version-file', 'cpp2il',
                 'cs-dir', 'work-dir', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--legacy-info', type=Path,
                        help='Import legacy AddedVersion values when DbInfo.json does not exist')
    return parser.parse_args()


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, delete=False) as file:
            temporary = file.name
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def run(args):
    logging.getLogger('sqlglot').setLevel(logging.ERROR)
    version = args.version_file.read_text(encoding='utf-8-sig').strip()
    unity = args.unity_version_file.read_text(encoding='utf-8-sig').strip()
    if not version or not unity:
        raise ValueError('APK and Unity versions must not be empty')
    previous = {}
    if args.output.exists():
        previous = json.loads(args.output.read_text(encoding='utf-8-sig'))
        if previous.get('SchemaVersion') != SCHEMA_VERSION:
            raise ValueError('Unsupported previous DbInfo schema')
    binary = Binary(args.binary, args.metadata)
    discovered = list(classes(args.cs_dir))
    if not discovered:
        raise ValueError('No C# database classes found')
    # A fresh directory prevents stale methods from an older APK entering the catalog.
    args.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='db-info-', dir=args.work_dir) as output:
        subprocess.run([
            str(args.cpp2il.resolve()), '--force-binary-path', str(args.binary.resolve()),
            '--force-metadata-path', str(args.metadata.resolve()),
            '--force-unity-version', unity, '--output-as', 'isil', '--output-to', output,
        ], check=True)
        methods = Methods(Path(output) / 'IsilDump/PSMain')
        verify_connections(methods)
        master, unresolved_managers = extract_managers(binary, methods, discovered)
        declared = extract_declarations(discovered)
        migrated, unresolved_migrations = extract_migrations(binary, methods, discovered)
        tables = merge_tables(master + declared + migrated)
        unattributed = unattributed_sql(metadata_sql(binary), tables, unresolved_migrations)
    data = {
        'SchemaVersion': SCHEMA_VERSION, 'ApkVersion': version,
        'Inputs': {'BinarySha256': hashlib.sha256(binary.data).hexdigest(),
                   'MetadataSha256': hashlib.sha256(binary.metadata).hexdigest()},
        'Tables': tables,
        'UnresolvedManagers': unresolved_managers,
        'UnresolvedMigrations': unresolved_migrations,
        'UnresolvedSql': unattributed,
    }
    if not previous and args.legacy_info and args.legacy_info.exists():
        previous = seed_history(data, args.legacy_info, version)
    data = apply_history(data, previous, version)
    atomic_write(args.output, data)
    print(f'Wrote {len(tables)} tables ({len(master)} masterdata managers, '
          f'{len(declared)} declarations, {len(migrated)} migration statements) to {args.output}')
    report_unresolved(data)


if __name__ == '__main__':
    run(arguments())
