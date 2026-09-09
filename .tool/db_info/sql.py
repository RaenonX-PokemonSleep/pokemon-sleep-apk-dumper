"""Parse SQLite DDL without executing SQL or treating migration history as a schema."""
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError
from sqlglot.tokens import TokenType


def statements(text):
    try:
        tokens = sqlglot.tokenize(text, read='sqlite')
    except TokenError:
        return [text.strip()]
    start, result = 0, []
    for token in tokens:
        if token.token_type == TokenType.SEMICOLON:
            part = text[start:token.end + 1].strip()
            if part:
                result.append(part)
            start = token.end + 1
    if text[start:].strip():
        result.append(text[start:].strip())
    return result


def parse(sql):
    try:
        node = sqlglot.parse_one(sql, read='sqlite')
    except (ParseError, TokenError) as error:
        return None, str(error).splitlines()[0]
    if not isinstance(node, (exp.Create, exp.Alter, exp.Drop)):
        return None, 'Not a supported DDL statement'
    target = node.this
    if isinstance(target, exp.Schema):
        target = target.this
    if isinstance(target, exp.Index):
        target = target.args.get('table')
    if not isinstance(target, exp.Table) or node.args.get('kind') == 'INDEX' and isinstance(node, exp.Drop):
        return None, 'Statement does not identify its owning table'
    return {'TableName': target.name, 'Kind': type(node).__name__, 'Sql': sql}, None


def columns(sql):
    node = sqlglot.parse_one(sql, read='sqlite')
    if not isinstance(node, exp.Create) or not isinstance(node.this, exp.Schema):
        return []
    result = []
    for item in node.this.expressions:
        if not isinstance(item, exp.ColumnDef):
            continue
        constraints = [c.kind.sql(dialect='sqlite') for c in item.constraints]
        result.append({
            'Name': item.name,
            'DeclaredSqlType': declared_type(sql, item),
            'Constraints': constraints,
            'Sources': ['cs_declaration'],
        })
    return result


def declared_type(sql, column):
    # SQLGlot normalizes BIGINT/BOOLEAN to INTEGER in SQLite output. Preserve
    # the type spelling in the declaration, using the parsed identifier span.
    start = column.this.meta['end'] + 1
    tail = sql[start:]
    tokens = sqlglot.tokenize(tail, read='sqlite')
    depth, end = 0, 0
    constraints = {'NOT', 'NULL', 'PRIMARY', 'UNIQUE', 'DEFAULT', 'CHECK',
                   'REFERENCES', 'COLLATE', 'CONSTRAINT', 'GENERATED', 'AS'}
    for token in tokens:
        if depth == 0 and (token.text.upper().split()[0] in constraints or token.text in (',', ')')):
            break
        if token.text == '(':
            depth += 1
        elif token.text == ')':
            depth -= 1
        end = token.end + 1
    return tail[:end].strip() or None


def normalized(sql):
    try:
        return sqlglot.parse_one(sql, read='sqlite').sql(dialect='sqlite')
    except (ParseError, TokenError):
        return sql
