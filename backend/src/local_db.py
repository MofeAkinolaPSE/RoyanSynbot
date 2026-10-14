import os
import psycopg2
import psycopg2.extras
import psycopg2.pool
import logging
from urllib.parse import urlparse


class Result:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count if count is not None else len(self.data)


class JsonbValue:
    """Wrap a list/scalar value to force JSONB serialization on insert/update.

    Without this, TableQuery guesses array-vs-jsonb from the value's shape
    (a list of strings looks the same whether the target column is a native
    Postgres text[] or a jsonb array), which breaks for jsonb-typed columns
    holding plain scalar lists (e.g. royan_capability_proposals.required_components).
    """
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


class SqlExpr:
    """Wrap a raw SQL expression for use in update() payloads, e.g.
    `{"used_count": SqlExpr("used_count + 1")}` emits `used_count = used_count + 1`
    instead of binding the string as a literal value via a placeholder.
    Only ever construct this with a fixed, developer-authored string — never
    with user input, since it is interpolated directly into the SQL text.
    """
    __slots__ = ("expr",)

    def __init__(self, expr: str):
        self.expr = expr


class _NotProxy:
    """Supabase-style `.not_.eq(...)` / `.not_.in_(...)` chaining.

    TableQuery only ever exposed the negated filters as direct methods
    (`neq`, `not_in`) — there was never an actual `.not_` attribute, so any
    call site written in the `.not_.eq(...)` / `.not_.in_(...)` style raised
    AttributeError. Several call sites did exactly that (capability_engine's
    proposal-dedup check, the weekly report's active-leads query, two lookups
    in integrations.py) and had the error silently swallowed by a bare
    `except Exception`, so the bug went unnoticed. This proxy makes that
    calling style actually work instead of forcing every call site to be
    rewritten to the direct-method form.
    """
    def __init__(self, query: "TableQuery"):
        self._query = query

    def eq(self, col, val):
        return self._query.neq(col, val)

    def in_(self, col, values):
        return self._query.not_in(col, values)


class TableQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self._select_cols = ["*"]
        self._where = []  # List of (column, operator, value) tuples
        self._order_by = []  # List of (column, desc: bool)
        self._limit = None
        self._offset = None
        self._payload = None
        self._count_mode = None  # "exact" to fetch total count ignoring limit/offset

    def select(self, *cols, count=None):
        if cols:
            self._select_cols = cols
        self._count_mode = count  # Track count mode for execute()
        return self

    def insert(self, payload):
        """Accept a single dict or list of dicts for batch insert."""
        self._payload = payload
        self._action = "insert"
        return self

    def update(self, payload: dict):
        self._payload = payload
        self._action = "update"
        return self

    def upsert(self, payload: dict, on_conflict: str | None = None):
        self._payload = payload
        self._action = "upsert"
        if on_conflict:
            self._upsert_conflict_col = on_conflict
        return self

    def delete(self):
        self._action = "delete"
        return self

    def eq(self, col, val):
        """Equal to (=)"""
        self._where.append((col, "=", val))
        return self

    def neq(self, col, val):
        """Not equal to (!=)"""
        self._where.append((col, "!=", val))
        return self

    def gt(self, col, val):
        """Greater than (>)"""
        self._where.append((col, ">", val))
        return self

    def gte(self, col, val):
        """Greater than or equal to (>=)"""
        self._where.append((col, ">=", val))
        return self

    def lt(self, col, val):
        """Less than (<)"""
        self._where.append((col, "<", val))
        return self

    def lte(self, col, val):
        """Less than or equal to (<=)"""
        self._where.append((col, "<=", val))
        return self

    def is_(self, col, val):
        """IS NULL / IS NOT NULL. Accepts Python None or string 'null' for IS NULL."""
        if val is None or val == "null":
            self._where.append((col, "IS", None))
        else:
            self._where.append((col, "IS_NOT_NULL", val))
        return self

    def ilike(self, col, pattern):
        """Case-insensitive LIKE"""
        self._where.append((col, "ILIKE", pattern))
        return self

    def like(self, col, pattern):
        """Case-sensitive LIKE"""
        self._where.append((col, "LIKE", pattern))
        return self

    def in_(self, col, values):
        """IN (...) filter"""
        self._where.append((col, "IN", list(values)))
        return self

    def not_in(self, col, values):
        """NOT IN (...) filter"""
        self._where.append((col, "NOT_IN", list(values)))
        return self

    @property
    def not_(self) -> "_NotProxy":
        """Supabase-style negation chaining: `.not_.eq(...)` / `.not_.in_(...)`."""
        return _NotProxy(self)

    def or_(self, conditions_str: str):
        """OR filter using PostgREST-style comma-separated condition string.
        e.g. "first_name.ilike.%MOFE%,last_name.ilike.%MOFE%"
        → (first_name ILIKE '%MOFE%' OR last_name ILIKE '%MOFE%')
        """
        self._or_clauses = getattr(self, '_or_clauses', [])
        self._or_clauses.append(conditions_str)
        return self

    def order(self, col, desc=False):
        """Order by column"""
        self._order_by.append((col, desc))
        return self

    def range(self, start, end):
        # Supabase range is inclusive indexes
        self._offset = int(start)
        self._limit = int(end) - int(start) + 1
        return self

    def limit(self, n):
        self._limit = int(n)
        return self

    def execute(self):
        conn = self.client.pool.getconn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            def _is_numeric_list(lst):
                """Check if list contains numeric values (embedding) vs strings (text array)."""
                return lst and all(isinstance(x, (int, float)) for x in lst)

            def _prepare_row_values(row_dict, cols):
                """Prepare values and placeholders for a single row."""
                vals = []
                placeholders = []
                for c in cols:
                    v = row_dict.get(c)
                    if isinstance(v, JsonbValue):
                        import json as _json
                        vals.append(_json.dumps(v.value))
                        placeholders.append('%s::jsonb')
                    elif isinstance(v, (list, tuple)):
                        if _is_numeric_list(v):
                            # Numeric embedding → store as native DOUBLE PRECISION[] array
                            # (pgvector extension not required; cosine similarity is computed in Python)
                            vals.append(list(v))
                            placeholders.append('%s::DOUBLE PRECISION[]')
                        elif v and isinstance(v[0], dict):
                            # List of dicts (e.g., sources JSONB array) → serialize as JSONB
                            import json as _json
                            vals.append(_json.dumps(v))
                            placeholders.append('%s::jsonb')
                        else:
                            # String/scalar array (e.g., roles) → use PostgreSQL array
                            vals.append(list(v))
                            placeholders.append('%s')
                    elif isinstance(v, dict):
                        # JSONB field → serialize to JSON string
                        import json as _json
                        vals.append(_json.dumps(v))
                        placeholders.append('%s::jsonb')
                    else:
                        vals.append(v)
                        placeholders.append('%s')
                return vals, placeholders

            if getattr(self, '_action', None) == 'insert':
                # Handle both single dict and list of dicts (batch insert)
                payload = self._payload
                rows_to_insert = payload if isinstance(payload, list) else [payload]
                
                if not rows_to_insert:
                    return Result([])
                
                # Get columns from first row
                cols = list(rows_to_insert[0].keys())
                
                all_rows = []
                for row in rows_to_insert:
                    vals, placeholders = _prepare_row_values(row, cols)
                    placeholders_sql = ','.join(placeholders)
                    sql = f"INSERT INTO public.{self.table} ({', '.join(cols)}) VALUES ({placeholders_sql}) RETURNING *"
                    cur.execute(sql, vals)
                    inserted = cur.fetchall()
                    all_rows.extend(inserted)
                
                conn.commit()
                return Result(all_rows)

            if getattr(self, '_action', None) == 'update':
                cols = list(self._payload.keys())
                set_parts = []
                params = []
                for c in cols:
                    v = self._payload[c]
                    if isinstance(v, SqlExpr):
                        set_parts.append(f"{c} = {v.expr}")
                    elif isinstance(v, JsonbValue):
                        import json as _json
                        set_parts.append(f"{c} = %s::jsonb")
                        params.append(_json.dumps(v.value))
                    elif isinstance(v, (list, tuple)):
                        if _is_numeric_list(v):
                            set_parts.append(f"{c} = %s::DOUBLE PRECISION[]")
                            params.append(list(v))
                        elif v and isinstance(v[0], dict):
                            import json as _json
                            set_parts.append(f"{c} = %s::jsonb")
                            params.append(_json.dumps(v))
                        else:
                            set_parts.append(f"{c} = %s")
                            params.append(list(v))
                    elif isinstance(v, dict):
                        import json as _json
                        set_parts.append(f"{c} = %s::jsonb")
                        params.append(_json.dumps(v))
                    else:
                        set_parts.append(f"{c} = %s")
                        params.append(v)
                set_clause = ', '.join(set_parts)
                where_clause = ''
                if self._where:
                    # Use new 3-tuple format (col, op, val)
                    conditions = []
                    for col, op, val in self._where:
                        if op == "IS":
                            if val is None:
                                conditions.append(f"{col} IS NULL")
                            else:
                                conditions.append(f"{col} IS NOT NULL")
                        elif op == "IN":
                            if not val:
                                conditions.append("FALSE")
                            else:
                                placeholders = ', '.join(['%s'] * len(val))
                                conditions.append(f"{col} IN ({placeholders})")
                                params.extend(val)
                        elif op == "NOT_IN":
                            if not val:
                                conditions.append("TRUE")
                            else:
                                placeholders = ', '.join(['%s'] * len(val))
                                conditions.append(f"{col} NOT IN ({placeholders})")
                                params.extend(val)
                        else:
                            if isinstance(val, dict):
                                import json as _json
                                conditions.append(f"{col} = %s::jsonb")
                                params.append(_json.dumps(val))
                            else:
                                conditions.append(f"{col} {op} %s")
                                params.append(val)
                    where_clause = ' WHERE ' + ' AND '.join(conditions)
                sql = f"UPDATE public.{self.table} SET {set_clause}{where_clause} RETURNING *"
                cur.execute(sql, params)
                rows = cur.fetchall()
                conn.commit()
                return Result(rows)

            if getattr(self, '_action', None) == 'delete':
                params = []
                where_clause = ''
                if self._where:
                    conditions = []
                    for col, op, val in self._where:
                        if op == "IS":
                            if val is None:
                                conditions.append(f"{col} IS NULL")
                            else:
                                conditions.append(f"{col} IS NOT NULL")
                        elif op == "IN":
                            if not val:
                                conditions.append("FALSE")
                            else:
                                placeholders = ', '.join(['%s'] * len(val))
                                conditions.append(f"{col} IN ({placeholders})")
                                params.extend(val)
                        elif op == "NOT_IN":
                            if not val:
                                conditions.append("TRUE")
                            else:
                                placeholders = ', '.join(['%s'] * len(val))
                                conditions.append(f"{col} NOT IN ({placeholders})")
                                params.extend(val)
                        else:
                            if isinstance(val, dict):
                                import json as _json
                                conditions.append(f"{col} = %s::jsonb")
                                params.append(_json.dumps(val))
                            else:
                                conditions.append(f"{col} {op} %s")
                                params.append(val)
                    where_clause = ' WHERE ' + ' AND '.join(conditions)
                if not where_clause:
                    # Every real call site filters by id/fk before deleting —
                    # a missing WHERE means a bug upstream, not an intentional
                    # "wipe the table" request. Refuse rather than comply.
                    raise ValueError(f"delete() on '{self.table}' called with no filters — refusing unconditional DELETE")
                sql = f"DELETE FROM public.{self.table}{where_clause} RETURNING *"
                cur.execute(sql, params)
                rows = cur.fetchall()
                conn.commit()
                return Result(rows)

            if getattr(self, '_action', None) == 'upsert':
                # Supports both a single dict and a list of dicts (batch upsert).
                conflict_col = getattr(self, '_upsert_conflict_col', None)
                payload = self._payload
                rows_to_upsert = payload if isinstance(payload, list) else [payload]

                if not rows_to_upsert:
                    return Result([])

                if not conflict_col:
                    conflict_col = 'id' if 'id' in rows_to_upsert[0] else None

                cols_all = list(rows_to_upsert[0].keys())
                all_rows = []

                for row_dict in rows_to_upsert:
                    vals, placeholders = _prepare_row_values(row_dict, cols_all)
                    placeholders_sql = ','.join(placeholders)
                    if conflict_col:
                        update_cols = [c for c in cols_all if c != conflict_col]
                        set_clause = ', '.join([f"{c} = EXCLUDED.{c}" for c in update_cols])
                        sql = (
                            f"INSERT INTO public.{self.table} ({', '.join(cols_all)}) "
                            f"VALUES ({placeholders_sql}) "
                            f"ON CONFLICT ({conflict_col}) DO UPDATE SET {set_clause} RETURNING *"
                        )
                    else:
                        sql = (
                            f"INSERT INTO public.{self.table} ({', '.join(cols_all)}) "
                            f"VALUES ({placeholders_sql}) RETURNING *"
                        )
                    cur.execute(sql, vals)
                    all_rows.extend(cur.fetchall())

                conn.commit()
                return Result(all_rows)

            # Default: SELECT
            cols_sql = ', '.join(self._select_cols)
            sql = f"SELECT {cols_sql} FROM public.{self.table}"
            params = []
            where_clause = ''
            
            # Build WHERE clause with operators (col, op, value)
            if self._where:
                conditions = []
                for col, op, val in self._where:
                    if op == "IS":
                        conditions.append(f"{col} IS NULL")
                    elif op == "IS_NOT_NULL":
                        conditions.append(f"{col} IS NOT NULL")
                    elif op == "ILIKE":
                        conditions.append(f"{col} ILIKE %s")
                        params.append(val)
                    elif op == "IN":
                        if not val:
                            conditions.append("FALSE")
                        else:
                            placeholders = ', '.join(['%s'] * len(val))
                            conditions.append(f"{col} IN ({placeholders})")
                            params.extend(val)
                    elif op == "NOT_IN":
                        if not val:
                            conditions.append("TRUE")
                        else:
                            placeholders = ', '.join(['%s'] * len(val))
                            conditions.append(f"{col} NOT IN ({placeholders})")
                            params.extend(val)
                    elif op in ("LIKE",):
                        conditions.append(f"{col} LIKE %s")
                        params.append(val)
                    else:
                        # for dict values serialize to JSONB
                        if isinstance(val, dict):
                            import json as _json
                            conditions.append(f"{col} = %s::jsonb")
                            params.append(_json.dumps(val))
                        else:
                            conditions.append(f"{col} {op} %s")
                            params.append(val)
                where_clause = ' WHERE ' + ' AND '.join(conditions)

            # OR filter block — PostgREST-style "col.op.value,col2.op2.value2"
            or_clauses = getattr(self, '_or_clauses', [])
            if or_clauses:
                all_or_parts = []
                for conditions_str in or_clauses:
                    parts = [p.strip() for p in conditions_str.split(',')]
                    or_parts = []
                    for part in parts:
                        pieces = part.split('.', 2)
                        if len(pieces) != 3:
                            continue
                        col_name, op_str, value = pieces
                        op_upper = op_str.upper()
                        if op_upper == 'ILIKE':
                            or_parts.append(f"{col_name} ILIKE %s")
                            params.append(value)
                        elif op_upper == 'EQ':
                            or_parts.append(f"{col_name} = %s")
                            params.append(value)
                        elif op_upper == 'LIKE':
                            or_parts.append(f"{col_name} LIKE %s")
                            params.append(value)
                        elif op_upper == 'NEQ':
                            or_parts.append(f"{col_name} != %s")
                            params.append(value)
                        elif op_upper in ('IS', 'IS_NULL'):
                            or_parts.append(f"{col_name} IS NULL")
                    if or_parts:
                        all_or_parts.append(f"({' OR '.join(or_parts)})")
                if all_or_parts:
                    or_expr = ' AND '.join(all_or_parts)
                    if where_clause:
                        where_clause += f" AND {or_expr}"
                    else:
                        where_clause = f" WHERE {or_expr}"

            # If count="exact" requested, get total count before applying limit/offset/order
            total_count = None
            if self._count_mode == "exact":
                count_sql = f"SELECT COUNT(*) FROM public.{self.table}" + where_clause
                # Use params without limit/offset for count
                cur.execute(count_sql, params[:])
                total_count = cur.fetchone()["count"]
            
            sql += where_clause
            
            # ORDER BY
            if self._order_by:
                order_parts = []
                for col, desc in self._order_by:
                    order_parts.append(f"{col} {'DESC' if desc else 'ASC'}")
                sql += ' ORDER BY ' + ', '.join(order_parts)
            
            if self._limit is not None:
                sql += ' LIMIT %s'
                params.append(self._limit)
            if self._offset is not None:
                sql += ' OFFSET %s'
                params.append(self._offset)
            cur.execute(sql, params)
            rows = cur.fetchall()
            return Result(rows, count=total_count)
        except Exception as e:
            logging.error(
                f"local_db TableQuery execute error on {self.table!r} "
                f"(action={getattr(self, '_action', 'select')}): {e} | sql={locals().get('sql', '<not built>')!r}"
            )
            try:
                conn.rollback()
            except Exception:
                pass
            # Mutations must not silently fail — re-raise so callers know data was not saved
            if getattr(self, '_action', None) in ('insert', 'update', 'upsert', 'delete'):
                raise
            return Result([])
        finally:
            try:
                cur.close()
            except Exception:
                pass
            try:
                self.client.pool.putconn(conn)
            except Exception:
                pass


class RPCQuery:
    def __init__(self, client, name, payload=None):
        self.client = client
        self.name = name
        self.payload = payload

    def execute(self):
        conn = self.client.pool.getconn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            # Special-case: match_documents — Python-side cosine similarity
            # (avoids requiring pgvector extension; embeddings stored as DOUBLE PRECISION[])
            if self.name == 'match_documents' and isinstance(self.payload, dict):
                import numpy as np

                query_vec = self.payload.get('query_embedding')
                thr = float(self.payload.get('match_threshold') or 0.0)
                cnt = int(self.payload.get('match_count') or 1)

                if query_vec is None:
                    return Result([])

                q_arr = np.asarray(query_vec, dtype=np.float32)
                q_norm = np.linalg.norm(q_arr)
                if q_norm == 0:
                    return Result([])
                q_unit = q_arr / q_norm

                cur.execute(
                    "SELECT id, question, answer, embedding FROM public.qna WHERE embedding IS NOT NULL"
                )
                rows = cur.fetchall()

                ranked = []
                for row in rows:
                    emb = row.get('embedding')
                    if emb is None:
                        continue
                    try:
                        d_arr = np.asarray(emb, dtype=np.float32)
                        d_norm = np.linalg.norm(d_arr)
                        if d_norm == 0:
                            continue
                        sim = float(np.dot(q_unit, d_arr / d_norm))
                        if sim > thr:
                            ranked.append({
                                'id': row['id'],
                                'question': row['question'],
                                'answer': row['answer'],
                                'similarity': sim,
                            })
                    except Exception:
                        continue

                ranked.sort(key=lambda r: r['similarity'], reverse=True)
                return Result(ranked[:cnt])

            # Special-case: match_agent_memories — same Python-side cosine
            # similarity approach as match_documents above, scoped to one
            # agent's own memories (AgentMemory.recall() in agent_memory.py).
            if self.name == 'match_agent_memories' and isinstance(self.payload, dict):
                import numpy as np

                agent_name = self.payload.get('p_agent_name')
                query_vec = self.payload.get('query_embedding')
                thr = float(self.payload.get('match_threshold') or 0.0)
                cnt = int(self.payload.get('match_count') or 1)

                if query_vec is None or not agent_name:
                    return Result([])

                q_arr = np.asarray(query_vec, dtype=np.float32)
                q_norm = np.linalg.norm(q_arr)
                if q_norm == 0:
                    return Result([])
                q_unit = q_arr / q_norm

                cur.execute(
                    "SELECT id, content, embedding FROM public.royan_agent_memory "
                    "WHERE agent_name = %s AND embedding IS NOT NULL",
                    (agent_name,),
                )
                rows = cur.fetchall()

                ranked = []
                for row in rows:
                    emb = row.get('embedding')
                    if emb is None:
                        continue
                    try:
                        d_arr = np.asarray(emb, dtype=np.float32)
                        d_norm = np.linalg.norm(d_arr)
                        if d_norm == 0:
                            continue
                        sim = float(np.dot(q_unit, d_arr / d_norm))
                        if sim > thr:
                            ranked.append({
                                'id': row['id'],
                                'content': row['content'],
                                'similarity': sim,
                            })
                    except Exception:
                        continue

                ranked.sort(key=lambda r: r['similarity'], reverse=True)
                return Result(ranked[:cnt])

            # Generic single-json param RPC
            # Treat None or empty dict as "no arguments" — empty dict is the
            # conventional no-op placeholder used by callers like generate_mrn({}).
            if not self.payload:
                cur.execute(f"select * from public.{self.name}()")
                rows = cur.fetchall()
                return Result(rows)
            else:
                cur.execute(f"select * from public.{self.name}(%s)", (psycopg2.extras.Json(self.payload),))
                rows = cur.fetchall()
                return Result(rows)
        except Exception as e:
            logging.error(f"local_db RPC execute error ({self.name}): {e}")
            try:
                conn.rollback()
            except Exception:
                pass
            return Result([])
        finally:
            try:
                cur.close()
            except Exception:
                pass
            try:
                self.client.pool.putconn(conn)
            except Exception:
                pass


class WaitingConnectionPool(psycopg2.pool.ThreadedConnectionPool):
    """A pool that WAITS (up to PG_POOL_WAIT seconds) for a free connection instead of failing.

    psycopg2's ThreadedConnectionPool raises "connection pool exhausted" the instant every connection
    is in use, which turned a short burst (one page firing ten requests, a few laptops at once) into
    500 errors and blank pages. Waiting a moment turns the burst into a queue. The semaphore counts
    connections handed out; it is released only for connections this pool actually lent."""

    def __init__(self, minconn: int, maxconn: int, wait_seconds: float, *args, **kwargs):
        super().__init__(minconn, maxconn, *args, **kwargs)
        import threading
        self._slots = threading.BoundedSemaphore(maxconn)
        self._wait = wait_seconds

    def getconn(self, key=None):
        if not self._slots.acquire(timeout=self._wait):
            raise psycopg2.pool.PoolError(f"connection pool exhausted (waited {self._wait:g}s)")
        try:
            return super().getconn(key)
        except Exception:
            self._slots.release()
            raise

    def putconn(self, conn=None, key=None, close=False):
        lent = conn is not None and id(conn) in self._rused
        try:
            super().putconn(conn, key, close)
        finally:
            if lent:
                self._slots.release()


class LocalDBClient:
    def __init__(self, database_url: str | None = None):
        if database_url is None:
            database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise RuntimeError('DATABASE_URL is required for LocalDBClient')
        # psycopg2 accepts the URL directly. Use a threaded connection pool to reduce overhead.
        try:
            # Sized to the request threads (the server runs up to 40 requests at once, each may need
            # a connection) and kept well under Postgres's max_connections (100). Waits instead of failing.
            maxconn = int(os.getenv('PG_MAX_CONN', '40'))
            wait = float(os.getenv('PG_POOL_WAIT', '20'))
            self.pool = WaitingConnectionPool(2, maxconn, wait, dsn=database_url)
        except Exception:
            # Fallback to direct connection to preserve compatibility
            conn = psycopg2.connect(database_url)
            class _SimplePool:
                def __init__(self, conn):
                    self._conn = conn
                def getconn(self):
                    return self._conn
                def putconn(self, c):
                    return
            self.pool = _SimplePool(conn)
            self.conn = conn

    def table(self, table_name: str) -> TableQuery:
        return TableQuery(self, table_name)

    def rpc(self, name: str, payload=None) -> RPCQuery:
        return RPCQuery(self, name, payload)

    def raw(self, expr: str) -> SqlExpr:
        """Build a raw SQL expression for an update() payload value, e.g.
        `db.raw("used_count + 1")`. See SqlExpr for the safety caveat."""
        return SqlExpr(expr)
