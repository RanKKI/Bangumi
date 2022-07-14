import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

import bs4
import requests

from bangumi.entitiy import WaitDownloadItem

logger = logging.getLogger(__name__)


class RSSParser(ABC):
    def request_rss(self, url: str) -> bs4.BeautifulSoup:
        ret = requests.get(url)
        if ret.status_code != 200:
            raise Exception(f"resp status code {ret.status_code}")
        return bs4.BeautifulSoup(ret.text, "xml")

    @abstractmethod
    def is_matched(self, url: str) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def parse(self, content) -> List[WaitDownloadItem]:
        raise NotImplementedError()
