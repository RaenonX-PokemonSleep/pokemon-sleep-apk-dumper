"""Seed observation history from the previous metadata export on the first run."""
import json
import re

from history import apply_history


def version_key(version):
    match = re.fullmatch(r'v?(\d+(?:\.\d+)*)', version)
    if not match:
        raise ValueError(f'Invalid legacy AddedVersion: {version!r}')
    return tuple(int(part) for part in match[1].split('.'))


def sql_key(sql):
    # Preserve identifier case, literals, types, and internal whitespace. Only
    # outer whitespace and the optional final semicolon differ across exporters.
    return sql.strip().removesuffix(';').rstrip()


def seed_history(current, path, version):
    legacy = json.loads(path.read_text(encoding='utf-8-sig'))
    versions = {}
    for table in legacy:
        for kind in ('Create', 'Alter', 'Drop'):
            records = table.get(kind) or []
            if isinstance(records, dict):
                records = [records]
            for record in records:
                added = record.get('AddedVersion')
                if not added or not record.get('Sql'):
                    continue
                version_key(added)
                key = sql_key(record['Sql'])
                if key not in versions or version_key(added) < version_key(versions[key]):
                    versions[key] = added
    output = apply_history(current, {}, version)
    imported = 0

    def seed(record):
        nonlocal imported
        added = versions.get(sql_key(record['Sql']))
        if added:
            record['Added'] = record['Modified'] = added
            imported += 1

    for table in output['Tables']:
        for kind in ('Declarations', 'Migrations'):
            for record in table[kind]:
                seed(record)
        children = [record for kind in ('Columns', 'Declarations', 'Migrations') for record in table[kind]]
        if children:
            table['Added'] = min((record['Added'] for record in children), key=version_key)
            table['Modified'] = max((record['Modified'] for record in children), key=version_key)
    for kind in ('UnresolvedMigrations', 'UnresolvedSql'):
        for record in output.get(kind, []):
            if 'Sql' in record:
                seed(record)
    print(f'Imported legacy AddedVersion for {imported} SQL records from {path}')
    return output
