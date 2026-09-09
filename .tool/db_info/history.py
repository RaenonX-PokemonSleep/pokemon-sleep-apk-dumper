"""Version dates describe observed content changes, never the time a dump ran."""
from copy import deepcopy

VERSION_FIELDS = {'Added', 'Modified'}


def content(value):
    if isinstance(value, dict):
        return {key: content(item) for key, item in value.items() if key not in VERSION_FIELDS}
    if isinstance(value, list):
        return [content(item) for item in value]
    return value


def stamp(record, previous, version):
    if previous is None:
        record['Added'] = record['Modified'] = version
    else:
        record['Added'] = previous['Added']
        record['Modified'] = previous['Modified'] if content(record) == content(previous) else version


def index_unique(records, key):
    result = {}
    for record in records:
        identity = key(record)
        if identity in result:
            raise ValueError(f'Duplicate history identity: {identity}')
        result[identity] = record
    return result


def column_key(column):
    return ('field', column['Field']) if 'Field' in column else ('name', column['Name'])


def apply_history(current, previous, version):
    output = deepcopy(current)
    old_tables = index_unique(previous.get('Tables', []),
                              lambda table: (table['Database']['Name'], table['TableName']))
    child_keys = {
        'Columns': column_key,
        'Declarations': lambda item: item['Class'],
        'Migrations': lambda item: (item['Class'], item['Direction'], item['Ordinal']),
    }
    for table in output['Tables']:
        old = old_tables.get((table['Database']['Name'], table['TableName']))
        for field, key in child_keys.items():
            old_children = index_unique(old[field], key) if old else {}
            index_unique(table[field], key)
            for record in table[field]:
                stamp(record, old_children.get(key(record)), version)
        stamp(table, old, version)
    for field in ('UnresolvedMigrations', 'UnresolvedSql'):
        if field not in output:
            continue
        key = ((lambda item: (item['Class'], item['Direction'], item.get('Ordinal')))
               if field == 'UnresolvedMigrations' else lambda item: item['Sql'])
        old_records = index_unique(previous.get(field, []), key)
        for record in output[field]:
            old = old_records.get(key(record))
            # Earlier unified exports did not date unresolved SQL records.
            stamp(record, old if old and 'Added' in old else None, version)
    return output
