import logging
import sys

_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_configured = False


def setup_logging(level: str = "INFO") -> None:
    """初始化应用日志：只配置 "app" 命名空间，输出到 stdout(由部署脚本重定向落盘)。"""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    root = logging.getLogger("app")
    root.setLevel(level.upper())
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """获取带 app 前缀的命名 logger，如 get_logger("generate") -> app.generate。"""
    return logging.getLogger(f"app.{name}")
