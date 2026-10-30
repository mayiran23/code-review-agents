import db


def all_orders():
    return db.query("SELECT * FROM orders").all()
