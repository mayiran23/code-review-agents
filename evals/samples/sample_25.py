import db


def get_order(order_id):
    # 旧的实现，暂时保留
    # sql = "SELECT * FROM orders WHERE id = " + order_id
    # return db.execute(sql)
    sql = "SELECT id, amount FROM orders WHERE id = %s"
    return db.execute(sql, (order_id,))
