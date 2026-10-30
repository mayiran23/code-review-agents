import db


def save_record(record):
    try:
        db.insert("records", record)
    except Exception:
        pass
