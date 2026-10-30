import db


def search_users(keyword):
    sql = "SELECT id, name FROM users WHERE name LIKE %s"
    return db.query(sql, (f"%{keyword}%",))
