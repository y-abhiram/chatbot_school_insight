"""SELECT-only AST validator and transaction-scoped identity enforcement."""
from functools import lru_cache
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlalchemy import inspect,text
from product.storage import engine
from product.cache import cache_key,get,put
class UnsafeSQL(ValueError):pass

@lru_cache
def catalog(tenant="school-demo"):
    from product.sources import source_for
    schema=source_for(tenant)['view_schema']
    inspector=inspect(engine('query',tenant))
    return {name:{column['name']:str(column['type']) for column in inspector.get_columns(name,schema=schema)} for name in inspector.get_view_names(schema=schema)}
# Functions deliberately exclude settings, networking, files, sleep, sequence and large-object access.
SAFE_FUNCTIONS={'COUNT','SUM','AVG','MIN','MAX','ROUND','COALESCE','NULLIF','LOWER','UPPER','CONCAT','CONCAT_WS','LENGTH','ABS','EXTRACT','DATE_TRUNC','CURRENT_DATE','CAST','GREATEST','LEAST','ROW_NUMBER','RANK','DENSE_RANK','CASE','IF','AND','OR'}

def validate_sql(statement,tenant="school-demo"):
    if len(statement)>15000:raise UnsafeSQL('The query is too long.')
    try:trees=sqlglot.parse(statement,read='postgres')
    except sqlglot.errors.ParseError as error:raise UnsafeSQL('Invalid PostgreSQL syntax.') from error
    if len(trees)!=1 or not isinstance(trees[0],exp.Select):raise UnsafeSQL('Only one SELECT statement is permitted.')
    tree=trees[0]
    blocked=(exp.Insert,exp.Update,exp.Delete,exp.Create,exp.Drop,exp.Alter,exp.Command,exp.Copy,exp.Into,exp.Lock,exp.Union,exp.Intersect,exp.Except)
    if any(isinstance(node,blocked) for node in tree.walk()):raise UnsafeSQL('Write operations, locks, and set operations are not permitted.')
    ctes={cte.alias for cte in tree.find_all(exp.CTE)}
    from product.sources import source_for
    view_schema=source_for(tenant)['view_schema']
    allowed=catalog(tenant)
    tables=list(tree.find_all(exp.Table))
    if not tables:raise UnsafeSQL('A report must use an approved reporting view.')
    for table in tables:
        if table.name in ctes and not table.db:continue
        if table.db not in ('',view_schema) or table.catalog or table.name not in allowed or not isinstance(table.this,exp.Identifier):raise UnsafeSQL('The query references an unapproved schema or relation.')
        table.set('db',exp.Identifier(this=view_schema))
    for node in tree.walk():
        if isinstance(node,exp.Func):
            name=node.name.upper() if isinstance(node,exp.Anonymous) else node.sql_name().upper()
            if name not in SAFE_FUNCTIONS:raise UnsafeSQL('This SQL function is not permitted.')
        if isinstance(node,exp.Cast) and any(x in node.args['to'].sql().lower() for x in ['reg','oid','bytea']):raise UnsafeSQL('This cast is not permitted.')
        if isinstance(node,exp.Dot) and isinstance(node.expression,exp.Func):raise UnsafeSQL('Qualified function calls are not permitted.')
    try:
        tree=qualify(tree,dialect='postgres',schema={view_schema:allowed},validate_qualify_columns=True,quote_identifiers=True,identify=True)
    except Exception as error:raise UnsafeSQL('A selected column is missing or ambiguous. Please rephrase the question.') from error
    # Replace any model-supplied limit with a bounded literal (one extra row detects truncation).
    requested=tree.args.get('limit')
    limit=200
    if requested:
        value=requested.expression
        if not isinstance(value,exp.Literal) or not value.is_int:raise UnsafeSQL('LIMIT must be a positive integer.')
        limit=max(1,min(200,int(value.this)))
    if tree.args.get('offset'):raise UnsafeSQL('Query offsets are not supported. Filter the report instead.')
    tree=tree.limit(limit+1)
    return tree.sql(dialect='postgres'),limit

def run_sql(statement,user,validated=False,use_cache=True):
    sql,limit=validate_sql(statement,user.tenant_id)
    key=cache_key('sql',user.tenant_id,user.user_id,user.role_name,sql)
    cached=get(key) if use_cache and user.role_name=='Admin' else None
    if cached is not None:return cached | {'cached':True}
    with engine('query',user.tenant_id).connect() as conn:
        with conn.begin():
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text("SET LOCAL statement_timeout='3000ms'"))
            conn.execute(text("SET LOCAL lock_timeout='500ms'"))
            conn.execute(text('SET LOCAL search_path=pg_catalog'))
            conn.execute(text("SELECT set_config('insight.tenant',:tenant,true),set_config('insight.role',:role,true),set_config('insight.user_id',:uid,true)"),{'tenant':user.tenant_id,'role':user.role_name,'uid':str(user.user_id)})
            result=conn.execute(text(sql))
            columns=list(result.keys());data=[dict(row) for row in result.mappings().fetchmany(limit+1)]
    payload={'sql':sql,'columns':columns,'rows':data[:limit],'truncated':len(data)>limit,'limit':limit,'cached':False}
    if use_cache and user.role_name=='Admin':put(key,payload)
    return payload
