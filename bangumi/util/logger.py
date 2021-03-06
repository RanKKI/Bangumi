import logging
import logging.config
import os

import yaml
from bangumi.consts.env import Env


def setup_logger():
    level = Env.get(Env.LOGGER_LEVEL, "INFO")
    level = logging.getLevelName(level=level)
    with open("conf/log.yml", "r") as stream:
        config = yaml.load(stream, Loader=yaml.FullLoader)
    config["root"]["level"] = level
    logging.config.dictConfig(config=config)
