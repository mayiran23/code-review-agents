import db


def get_user_names(user_ids):
    count = []
    for uid in user_ids:
        row = db.query("SELECT name FROM users WHERE id = %s", uid)
        if row:
            count.append(row[0]["name"])
    return count
