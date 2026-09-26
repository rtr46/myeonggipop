# myeonggipop/utils/logger.py
import logging
import sys

from myeonggipop.config.config import APP_NAME

TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")


def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kws)


logging.Logger.trace = trace


def setup_logging():
    # Console code pages on Windows (e.g. cp932/cp949) cannot print Hangul;
    # reconfigure stdout/stderr to UTF-8 with lossy fallback so Korean log
    # lines (e.g. "Looking up: ...") never crash the app.
    for stream_name in ('stdout', 'stderr'):
        stream = getattr(sys, stream_name, None)
        reconfig = getattr(stream, 'reconfigure', None)
        if callable(reconfig):
            try:
                reconfig(encoding='utf-8', errors='replace')
            except Exception:
                pass

    log_formatter = logging.Formatter(
        f"%(asctime)s - [%(levelname)-5s] - [{APP_NAME}] - %(message)s",
        datefmt='%H:%M:%S'
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(log_formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  # logging.INFO or TRACE_LEVEL_NUM

    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)
