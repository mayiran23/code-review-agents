ALLOWED_TABLES = {"users", "orders", "products"}


def build_query(table):
    if table not in ALLOWED_TABLES:
        raise ValueError("非法表名")
    return f"SELECT * FROM {table}"
