from typing import List, Optional

from playwright.sync_api import Page

from . import config
from .detector import find_button

ENDED = "ended"
RUNNING = "running"


def visible_texts(page: Page, texts: Optional[List[str]] = None) -> List[str]:
    texts = texts if texts is not None else config.end_texts()
    return [text for text in texts if find_button(page, text) is not None]


def detect_state(page: Page, texts: Optional[List[str]] = None) -> str:
    return ENDED if visible_texts(page, texts) else RUNNING


def describe_state(state: str) -> str:
    if state == ENDED:
        return "ended (sequence ready)"
    return "running (nothing to click)"


def describe_visible(visible: List[str]) -> str:
    return ", ".join(visible) if visible else "none"
