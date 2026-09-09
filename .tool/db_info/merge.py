"""Merge evidence within a database; keep unattributed SQL out of current schemas."""
from copy import deepcopy

from classification import unknown_database
from sql import normalized, parse


def merge_tables(records):
    tables = {}
    for incoming in records:
        key = (incoming['Database']['Name'], incoming['TableName'])
        if key not in tables:
            table = deepcopy(incoming)
            table['Database']['Evidence'] = [table['Database']['Evidence']]
            tables[key] = table
            continue
        table = tables[key]
        if table['Database']['Category'] != incoming['Database']['Category']:
            raise ValueError(f'Conflicting database categories: {key}')
        table['Database']['Evidence'].append(incoming['Database']['Evidence'])
        for field in ('Classes', 'Declarations', 'Migrations', 'Unresolved'):
            table[field].extend(deepcopy(incoming[field]))
        existing_columns = {column['Name']: column for column in table['Columns']}
        for column in incoming['Columns']:
            existing = existing_columns.get(column['Name'])
            if existing is None:
                table['Columns'].append(deepcopy(column))
                existing_columns[column['Name']] = table['Columns'][-1]
                continue
            for field, value in column.items():
                if field == 'Sources':
                    existing[field] = sorted(set(existing[field] + value))
                elif field not in existing:
                    existing[field] = deepcopy(value)
                elif existing[field] != value:
                    raise ValueError(f'Conflicting column evidence: {key}, {column["Name"]}, {field}')
    for table in tables.values():
        table['Database']['Evidence'] = sorted(set(table['Database']['Evidence']))
        table['Classes'] = sorted(set(table['Classes']))
        table['Unresolved'] = sorted(set(table['Unresolved']))
        table['Declarations'].sort(key=lambda item: item['Class'])
        table['Migrations'].sort(key=lambda item: (item['Class'], item['Direction'], item['Ordinal']))
        table['Columns'].sort(key=lambda item: item['Name'])
    return [tables[key] for key in sorted(tables)]


def unattributed_sql(statements, tables, unresolved_migrations):
    known = {normalized(record['Sql']) for table in tables
             for field in ('Declarations', 'Migrations') for record in table[field]}
    # Keep native SQL with a known owner even when the SQL parser rejects it.
    known.update(normalized(item['Sql']) for item in unresolved_migrations if 'Sql' in item)
    result = []
    for statement in sorted(set(statements)):
        if normalized(statement) in known:
            continue
        parsed, error = parse(statement)
        result.append({'Sql': statement, 'Database': unknown_database(),
                       'TableName': parsed['TableName'] if parsed else None,
                       'Reason': error or 'Database and declaration/migration ownership unresolved'})
    return result
