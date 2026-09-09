"""Classify by database access paths and explicit migration namespaces."""

MIGRATION_DATABASES = {
    'Server': ('server', 'user'),
    'Local': ('local', 'local'),
    'System': ('system', 'system'),
    'HealthApp': ('health_app', 'health_app'),
    'MigrationTest': ('migration_test', 'test'),
}


def database(name, category, evidence):
    return {'Name': name, 'Category': category, 'Evidence': evidence}


def verify_connections(methods):
    master = methods.get('MasterDataManagerBase`2')
    if not any('MasterDataLoadManager.GetMasterDataDB' in m.calls for m in master):
        raise ValueError('Cannot verify the masterdata manager database connection')
    sync = methods.find('PS/DB/SyncDatabase`1', 'get_GlobalDB')
    if not sync or 'DataManager.getServerDBInstance' not in sync.calls:
        raise ValueError('Cannot verify the sync database connection')


def master_database():
    return database('masterdata', 'masterdata', 'MasterDataLoadManager.GetMasterDataDB')


def user_database():
    return database('server', 'user', 'PS.DB.SyncDatabase.get_GlobalDB -> DataManager.getServerDBInstance')


def migration_database(relative):
    parts = relative.split('/')
    if len(parts) < 4 or parts[:2] != ['PS', 'Migration']:
        return None
    pair = MIGRATION_DATABASES.get(parts[2])
    return database(*pair, f'namespace PS.Migration.{parts[2]}') if pair else None


def unknown_database():
    return database('unknown', 'unknown', 'unattributed_metadata_sql')
