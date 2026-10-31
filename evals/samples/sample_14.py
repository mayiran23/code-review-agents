import logging
import db

log = logging.getLogger(__name__)


def get_order(order_id):
    try:
        return db.query("SELECT id, amount FROM orders WHERE id = %s", order_id)
    except db.ConnectionError:
        log.error("数据库连接失败 order_id=%s", order_id)
        raise
