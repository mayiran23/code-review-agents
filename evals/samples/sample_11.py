import db


def transfer(from_id, to_id, amount):
    db.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", amount, from_id)
    db.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", amount, to_id)
    return True
