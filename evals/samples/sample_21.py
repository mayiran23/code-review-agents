import db


def process(users):
    for u in users:
        if u.get("active"):
            try:
                order = db.query("SELECT * FROM orders WHERE uid = " + u["id"])
                if order:
                    return order[0]
            except Exception:
                continue
