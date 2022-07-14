from glob import glob
import logging
import os
from time import sleep, time

from pathlib import Path

import requests

from bangumi.database import redisDB
from bangumi.downloader import DownloadState, downloader
from bangumi.entitiy import DownloadItem, WaitDownloadItem
from bangumi.manager import Notification, notification
from bangumi.parser import Parser
from bangumi.rss import RSS
from bangumi.util import Env, move_file, get_relative_path, safe_call

logger = logging.getLogger(__name__)


class Bangumi(object):
    def __init__(self) -> None:
        super().__init__()
        self.rss = RSS()
        self.notification = Notification()

    def rename(self, item: DownloadItem, info: WaitDownloadItem) -> str:
        logger.info(f"Renaming {item.hash} {item.name}...")
        if item.hash != info.hash:
            logger.error(f"Hash mismatch {item.hash} {info.hash}")
            return
        if len(item.files) > 1:
            logger.error(f"Can't rename multi-file torrent {item.hash}")
            return
        if len(item.files) == 0:
            logger.error(f"Can't rename empty torrent {item.hash}")
            return

        file = item.files[0]
        file = get_relative_path(file)

        if not file.exists():
            logger.error(f"File {file} doesn't exist")
            return

        result = Parser.parse_bangumi_name(info.name)
        logger.info(f"Renaming {file.name} to {result.formatted}")
        try:
            move_file(file, result)
            return result.formatted
        except Exception as e:
            logger.error(f"Failed to rename {e}")

    def on_torrent_finished(self, item: DownloadItem):
        ret = self.rename(item, redisDB.get(item.hash))
        if not ret:
            return
        redisDB.remove(item.hash)
        downloader.remove_torrent(item)
        self.notification.call(ret)

    @safe_call
    def check(self, last_dt: int) -> bool:
        logger.info("Checking RSS...")
        items = self.rss.scrape(last_dt)
        logger.info("Found %d items", len(items))
        redisDB.add_to_torrent_queue(items)
        return True

    @safe_call
    def check_complete(self):
        logger.debug("Checking complete...")
        try:
            completed = downloader.get_downloads(DownloadState.FINISHED)
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Failed to get completed torrents {e}")
            return

        if len(completed) == 0:
            return
        logger.info("Found %d completed downloads", len(completed))
        for item in completed:
            self.on_torrent_finished(item)

    @safe_call
    def check_queue(self):
        logger.debug("Checking torrent queue...")
        count = 0
        item = redisDB.pop_torrent_to_download()
        while item:
            info = Parser.parse_bangumi_name(item.name)
            if not (info and redisDB.is_downloaded(info.formatted)):
                redisDB.set_downloaded(info.formatted)
                downloader.add_torrent(item.url)
                logger.info(f"Added {item.url} to downloader")
                count += 1
            item = redisDB.pop_torrent_to_download()
        if count > 0:
            logger.info("Added %d torrents to downloader", count)

    def loop(self):
        INTERVAL = int(os.environ.get(Env.CHECK_INTERVAL.value, 60 * 10))

        while True:
            current = int(time())
            last = redisDB.get_last_checked_time()
            if current - last > INTERVAL and self.check(last):
                redisDB.update_last_checked_time()
            self.check_complete()
            self.check_queue()
            sleep(10)

    def init(self):
        logger.info("init...")
        media = Path(os.environ.get(Env.MEDIA_FOLDER.value, "media"))
        exists = set()
        for item in glob(str(media / "**/*"), recursive=True):
            if not os.path.isfile(item):
                continue
            name, _ = os.path.splitext(os.path.basename(item))
            exists.add(name)
        logger.info("Found %d files that already downloaded", len(exists))
        for name in exists:
            redisDB.set_downloaded(name)

    def load_config(self):
        config_folder = Path(os.environ.get(Env.CONFIG_PATH.value, "/config"))
        rss_config = config_folder / "rss.json"
        if rss_config.exists():
            self.rss.load_config(rss_config)
        else:
            logger.info("No RSS config found, Skip...")
        notification_config = config_folder / "notification.json"
        if notification_config.exists():
            self.notification.load_config(notification_config)
        else:
            logger.info("No notification config found, Skip...")

    def run(self):
        logger.info("Starting...")
        try:
            redisDB.connect()
        except Exception as e:
            logger.error(e)
            return
        downloader.connect()
        self.load_config()
        if redisDB.init():
            self.init()
        self.loop()
