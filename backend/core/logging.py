import logging
import sys
import contextvars

request_id_ctx = contextvars.ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        rid = request_id_ctx.get(None)
        record.request_id = rid or "-"
        return True


def setup_logging():
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s %(levelname)s %(name)s [rid=%(request_id)s] %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addFilter(RequestIdFilter())
