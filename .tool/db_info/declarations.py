from classification import user_database
from sql import columns


def extract_declarations(discovered):
    tables = []
    for owner in discovered:
        name = owner.constant('m_TableName')
        statement = owner.constant('m_CreateTableStatement')
        if 'SyncDatabase<' not in owner.text or name is None or statement is None:
            continue
        declaration = {
            'Class': owner.relative, 'Sql': statement,
            'PrimaryKey': owner.constant('LIST_PRIMARY_KEY'),
            'CreateIndexSql': owner.constant('LIST_CREATE_INDEX_STATEMENT'),
        }
        tables.append({
            'TableName': name, 'Database': user_database(), 'Classes': [owner.relative],
            'Columns': columns(statement), 'Declarations': [declaration],
            'Migrations': [], 'Unresolved': [],
        })
    return tables
