import re

from classification import migration_database
from native import analyze
from sql import parse, statements


def extract_migrations(binary, methods, discovered):
    tables, unresolved = [], []
    for owner in discovered:
        database = migration_database(owner.relative)
        if database is None:
            continue
        for direction in ('Up', 'Down'):
            method = methods.find(owner.relative, f'get_{direction}SQL')
            if method is None:
                continue
            result = analyze(binary, method)
            if len(result.returns) != 1 or None in result.returns or result.issues:
                unresolved.append({'Class': owner.relative, 'Database': database, 'Direction': direction,
                                   'Reason': 'SQL getter did not resolve to one literal'})
                continue
            literal = next(iter(result.returns))
            if not literal.strip():
                continue
            for ordinal, statement in enumerate(statements(literal)):
                data, error = parse(statement)
                if error:
                    unresolved.append({'Class': owner.relative, 'Database': database, 'Direction': direction,
                                       'Ordinal': ordinal, 'Sql': statement, 'Reason': error})
                    continue
                migration = {**data, 'Class': owner.relative, 'Direction': direction,
                             'Ordinal': ordinal}
                del migration['TableName']
                tables.append({
                    'TableName': data['TableName'], 'Database': database, 'Classes': [],
                    'Columns': [], 'Declarations': [], 'Migrations': [migration], 'Unresolved': [],
                })
    return tables, unresolved


def metadata_sql(binary):
    for literal in sorted(set(binary.literals())):
        if re.match(r'\s*(?:CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)|ALTER\s+TABLE|DROP\s+(?:TABLE|INDEX))\b', literal, re.I):
            yield from statements(literal)
