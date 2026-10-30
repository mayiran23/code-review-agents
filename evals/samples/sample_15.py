import db

MAX_PAGE_SIZE = 100


def list_orders(page, size):
    if page < 1 or size < 1:
        raise ValueError("page 和 size 必须为正数")
    size = min(size, MAX_PAGE_SIZE)
    offset = (page - 1) * size
    return db.query(
        "SELECT id, user_id, amount FROM orders ORDER BY id LIMIT %s OFFSET %s",
        (size, offset),
    )

