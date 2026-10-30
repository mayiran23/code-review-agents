import logging

log = logging.getLogger(__name__)


def login(phone, password):
    log.info("用户登录：手机号=%s 密码=%s", phone, password)
    return check_password(phone, password)
