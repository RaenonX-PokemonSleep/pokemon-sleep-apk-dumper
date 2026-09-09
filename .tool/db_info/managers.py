"""Map native static-field writes to declared masterdata column fields."""
import re
from collections import defaultdict

from classification import master_database
from native import analyze


def inherited_id(binary, methods, discovered):
    base = next(c for c in discovered if c.name == 'MasterDataManagerBase`2')
    names = re.findall(r'\bstatic readonly string (\w+);', base.text)
    if names != ['COL_ID']:
        raise ValueError('Shared masterdata string fields changed; cannot identify COL_ID')
    method = methods.find(base.relative, '.cctor')
    if not method:
        raise ValueError('Missing shared masterdata initializer')
    # Generic field offsets in diffable-cs are zero. The sole string static field
    # is identifiable only if there is exactly one distinct assigned string.
    assignments = analyze(binary, method)
    strings = assignments.written_strings
    if len(strings) != 1:
        raise ValueError(f'Cannot resolve inherited COL_ID: {sorted(strings)}')
    return next(iter(strings))


def extract_managers(binary, methods, discovered):
    id_name = inherited_id(binary, methods, discovered)
    tables, unresolved = [], []
    for owner in discovered:
        if not re.search(r': MasterDataManagerBase<', owner.text):
            continue
        fields = owner.fields()
        expected = {key: offset for key, offset in fields.items() if key == 'TABLE_NAME' or key.startswith('COL_')}
        method = methods.find(owner.relative, '.cctor')
        if not method or 'TABLE_NAME' not in expected:
            unresolved.append({'Class': owner.relative, 'Database': master_database(),
                               'Reason': 'Missing initializer or static field offsets'})
            continue
        result = analyze(binary, method)
        groups = defaultdict(dict)
        for (root, offset), values in result.stores.items():
            if len(values) == 1 and None not in values:
                groups[root][offset] = next(iter(values))
        candidates = [group for group in groups.values() if expected['TABLE_NAME'] in group
                      and re.fullmatch(r'[a-z][a-z0-9_]*', group[expected['TABLE_NAME']])]
        if len(candidates) != 1:
            unresolved.append({'Class': owner.relative, 'Database': master_database(),
                               'Reason': 'Table-name assignment is unresolved or ambiguous'})
            continue
        group = candidates[0]
        columns = [] if 'COL_ID' in expected else [
            {'Name': id_name, 'Field': 'COL_ID', 'Sources': ['native_base_initializer']}]
        issues = sorted(result.issues)
        for name, offset in sorted(expected.items(), key=lambda item: item[1]):
            if name == 'TABLE_NAME':
                continue
            literal = group.get(offset)
            if literal is None:
                issues.append(f'Unresolved field: {name}')
            else:
                columns.append({'Name': literal, 'Field': name, 'Sources': ['native_initializer']})
        tables.append({
            'TableName': group[expected['TABLE_NAME']], 'Database': master_database(),
            'Classes': [owner.relative], 'Columns': columns,
            'Declarations': [], 'Migrations': [], 'Unresolved': issues,
        })
    return tables, unresolved
