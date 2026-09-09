"""Report incomplete extraction as Azure warnings without changing exit status."""
import os


def report_unresolved(data):
    counts = {
        'masterdata managers': len(data['UnresolvedManagers']),
        'migration statements/getters': len(data['UnresolvedMigrations']),
        'unattributed SQL statements': len(data['UnresolvedSql']),
        'tables with partially resolved columns': sum(bool(t['Unresolved']) for t in data['Tables']),
    }
    prefix = ('##vso[task.logissue type=warning;]'
              if os.environ.get('TF_BUILD', '').lower() == 'true' else 'Warning: ')
    for label, count in counts.items():
        if count:
            print(f'{prefix}DB extraction: {count} unresolved {label}. See DbInfo.json for details.')
