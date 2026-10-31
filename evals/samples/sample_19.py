import logging
import db

log = logging.getLogger(__name__)


def delete_order(user_id, order_id):
    order = db.query("SELECT id, user_id, deleted FROM orders WHERE id = %s", order_id)
    if not order or order[0]["deleted"]:
        raise OrderNotFound(order_id)
    if order[0]["user_id"] != user_id:
        raise PermissionDenied(order_id)
    affected = db.execute("UPDATE orders SET deleted = 1 WHERE id = %s", order_id)
    if affected == 0:
        raise OrderNotFound(order_id)
    log.info("删除订单成功 order_id=%s user_id=%s", order_id, user_id)
