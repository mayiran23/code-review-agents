import db


def list_orders(user_ids):
    result = []
    for uid in user_ids:
        rows = db.query("SELECT * FROM orders WHERE user_id = %s", uid)
        result.extend(rows)
    return result
