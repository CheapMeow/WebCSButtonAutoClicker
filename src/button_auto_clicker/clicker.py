from dataclasses import dataclass
from typing import List, Optional

from playwright.sync_api import Page

from . import config
from .detector import ButtonCandidate, ButtonNotFoundError, find_button, frame_label
from .state import detect_state

HIT_TEST_SCRIPT = r"""
(steps) => {
  let element = document.body;
  for (const index of steps) {
    element = element ? element.children[index] : null;
  }
  if (!element) {
    return { ok: false, reason: "element-removed" };
  }
  const rect = element.getBoundingClientRect();
  const x = rect.x + rect.width / 2;
  const y = rect.y + rect.height / 2;
  if (rect.width <= 0 || rect.height <= 0) {
    return { ok: false, reason: "zero-size" };
  }
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
  if (x < 0 || y < 0 || x > viewportWidth || y > viewportHeight) {
    return { ok: false, reason: "outside-viewport" };
  }
  const hit = document.elementFromPoint(x, y);
  if (!hit) {
    return { ok: false, reason: "no-hit" };
  }
  const related = element.contains(hit) || hit.contains(element) || element === hit;
  return { ok: true, reason: related ? "hit" : "covered", x: x, y: y, hitTag: hit.tagName.toLowerCase() };
}
"""


class ClickRejectedError(RuntimeError):
    pass


class ClickNotConfirmedError(RuntimeError):
    pass


@dataclass
class ClickResult:
    candidate: ButtonCandidate
    x: float
    y: float
    hit_tag: str
    confirmed: bool = False
    state_before: str = ""
    state_after: str = ""

    def describe(self) -> str:
        return "clicked [{0}] at ({1:.1f}, {2:.1f}) on <{3}> | state {4} -> {5} | confirmed={6}".format(
            self.candidate.text,
            self.x,
            self.y,
            self.hit_tag,
            self.state_before,
            self.state_after,
            self.confirmed,
        )


def click_candidate(page: Page, candidate: ButtonCandidate) -> ClickResult:
    if candidate.frame != frame_label(page.main_frame):
        raise ClickRejectedError("button lives in subframe {0}, only the main frame is supported".format(candidate.frame))
    probe = page.evaluate(HIT_TEST_SCRIPT, candidate.steps)
    if not probe.get("ok"):
        raise ClickRejectedError("button not clickable: {0}, element: {1}".format(probe.get("reason"), candidate.path))
    if probe.get("reason") == "covered":
        raise ClickRejectedError(
            "button covered by <{0}>, element: {1}".format(probe.get("hitTag"), candidate.path)
        )

    x = float(probe["x"])
    y = float(probe["y"])
    page.mouse.move(x, y)
    page.mouse.click(x, y)
    return ClickResult(candidate=candidate, x=x, y=y, hit_tag=probe.get("hitTag", ""))


def click_once(page: Page, text: str) -> ClickResult:
    candidate = find_button(page, text)
    if candidate is None:
        raise ButtonNotFoundError(text)
    return click_candidate(page, candidate)


def click_text(page: Page, text: str, state_texts: Optional[List[str]] = None, settle_seconds: float = 1.2) -> ClickResult:
    state_texts = state_texts if state_texts is not None else config.end_texts()
    state_before = detect_state(page, state_texts)
    result = click_once(page, text)
    page.wait_for_timeout(int(settle_seconds * 1000))
    state_after = detect_state(page, state_texts)
    still_visible = find_button(page, text) is not None
    result.state_before = state_before
    result.state_after = state_after
    result.confirmed = (not still_visible) or (state_after != state_before)
    if not result.confirmed:
        raise ClickNotConfirmedError(
            "{0} is still visible and state stayed {1}, the click probably had no effect".format(text, state_after)
        )
    return result


def run_cycle(
    page: Page,
    texts: List[str],
    state_texts: Optional[List[str]] = None,
    settle_seconds: float = 1.2,
) -> List[ClickResult]:
    if not texts:
        raise ButtonNotFoundError("empty button sequence")
    state_texts = state_texts if state_texts is not None else config.end_texts()
    results = []
    for text in texts:
        if find_button(page, text) is None:
            continue
        results.append(click_text(page, text, state_texts=state_texts, settle_seconds=settle_seconds))
    return results
