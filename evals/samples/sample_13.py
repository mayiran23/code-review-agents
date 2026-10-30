import db


def get_user(uid):
    sql = "SELECT id, name FROM users WHERE id = %s"
    return db.execute(sql, (uid,))
