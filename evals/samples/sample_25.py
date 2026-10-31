import db


def get_order(order_id):
    sql = "SELECT id, amount FROM orders WHERE id = %s"
    return db.execute(sql, (order_id,))
