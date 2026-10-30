import db


def get_user(uid):
    sql = "SELECT * FROM users WHERE id = " + uid
    return db.execute(sql)
