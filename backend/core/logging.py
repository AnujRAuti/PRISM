import logging
import sys
import contextvars

request_id_ctx = contextvars.ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        rid = request_id_ctx.get(None)
        record.request_id = rid or "-"
        return True


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [rid=%(request_id)s] %(message)s"


def setup_logging():
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    # The filter belongs on the handler, not the root logger: ancestor logger
    # filters are not consulted for records propagating up from third-party
    # loggers, and those records then fail to format the [rid=...] field.
    handler.addFilter(RequestIdFilter())
    root.setLevel(logging.INFO)
    root.addHandler(handler)
