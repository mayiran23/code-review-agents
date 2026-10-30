import logging
import db

log = logging.getLogger(__name__)


def create_order(user_id, amount):
    order_id = db.insert("orders", {"user_id": user_id, "amount": amount})
    log.info("创建订单成功 order_id=%s user_id=%s", order_id, user_id)
    return order_id
