import logging
from logging.handlers import TimedRotatingFileHandler
import os

def setup_logger(name: str = __name__) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.hasHandlers():  # 避免重复添加 handler
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )

        # 控制台 handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 文件 handler：每天生成一个日志文件，保留7天
        os.makedirs("logs", exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            filename="logs/app.log",
            when="midnight",        # 每天0点创建新文件
            interval=1,             # 间隔1天
            backupCount=7,          # 最多保留7个历史文件
            encoding='utf-8',
            utc=False               # 使用本地时间
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger