from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from playwright.sync_api import Frame, Page

from . import config

CANDIDATE_SCRIPT = r"""
(wanted) => {
  const normalize = (value) => (value || "").replace(/\s+/g, " ").trim();
  const target = normalize(wanted);

  const isVisible = (element) => {
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return false;
    }
    const style = getComputedStyle(element);
    if (style.visibility === "hidden" || style.display === "none") {
      return false;
    }
    if (parseFloat(style.opacity) === 0) {
      return false;
    }
    return true;
  };

  const isClickable = (element) => {
    const tag = element.tagName.toLowerCase();
    const role = (element.getAttribute("role") || "").toLowerCase();
    if (tag === "button" || tag === "a" || role === "button") {
      return true;
    }
    if (element.hasAttribute("onclick")) {
      return true;
    }
    return getComputedStyle(element).cursor === "pointer";
  };

  const stepsOf = (element) => {
    const steps = [];
    let node = element;
    while (node && node.parentElement && node !== document.body) {
      steps.unshift(Array.from(node.parentElement.children).indexOf(node));
      node = node.parentElement;
    }
    return steps;
  };

  const describe = (element) => {
    const parts = [];
    let current = element;
    while (current && current.nodeType === 1 && current.tagName.toLowerCase() !== "html") {
      let part = current.tagName.toLowerCase();
      if (current.id) {
        part += "#" + CSS.escape(current.id);
      }
      const classes = (current.className || "").toString().split(/\s+/).filter((name) => name.length > 0);
      if (classes.length > 0) {
        part += "." + classes.map((name) => CSS.escape(name)).join(".");
      }
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter((child) => child.tagName === current.tagName);
        if (siblings.length > 1) {
          part += ":nth-of-type(" + (siblings.indexOf(current) + 1) + ")";
        }
      }
      parts.unshift(part);
      current = current.parentElement;
    }
    return parts.join(" > ");
  };

  const results = [];
  for (const element of document.querySelectorAll("body *")) {
    if (!isVisible(element)) {
      continue;
    }
    if (normalize(element.textContent) !== target) {
      continue;
    }
    const rect = element.getBoundingClientRect();
    results.push({
      path: describe(element),
      steps: stepsOf(element),
      tag: element.tagName.toLowerCase(),
      text: normalize(element.textContent),
      clickable: isClickable(element),
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      outerHTML: element.outerHTML.slice(0, 300),
    });
  }
  return results;
}
"""


class ButtonNotFoundError(RuntimeError):
    pass


@dataclass
class ButtonCandidate:
    frame: str
    path: str
    steps: List[int]
    tag: str
    text: str
    clickable: bool
    x: float
    y: float
    width: float
    height: float
    outer_html: str

    @property
    def center(self) -> tuple:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    def describe(self) -> str:
        return "{0} | {1} | clickable={2} | center=({3:.1f}, {4:.1f}) | size={5:.1f}x{6:.1f}".format(
            self.frame, self.path, self.clickable, self.center[0], self.center[1], self.width, self.height
        )


def frame_label(frame: Frame) -> str:
    return frame.name if frame.name else frame.url


def collect_candidates(page: Page, text: Optional[str] = None) -> List[ButtonCandidate]:
    text = text if text is not None else config.primary_button_text()
    candidates: List[ButtonCandidate] = []
    for frame in page.frames:
        raw: List[Dict[str, Any]] = frame.evaluate(CANDIDATE_SCRIPT, text)
        for item in raw:
            candidates.append(
                ButtonCandidate(
                    frame=frame_label(frame),
                    path=item["path"],
                    steps=[int(step) for step in item["steps"]],
                    tag=item["tag"],
                    text=item["text"],
                    clickable=bool(item["clickable"]),
                    x=float(item["x"]),
                    y=float(item["y"]),
                    width=float(item["width"]),
                    height=float(item["height"]),
                    outer_html=item["outerHTML"],
                )
            )
    return candidates


def pick_candidate(candidates: List[ButtonCandidate]) -> Optional[ButtonCandidate]:
    if not candidates:
        return None
    clickable = [item for item in candidates if item.clickable]
    pool = clickable if clickable else candidates
    return min(pool, key=lambda item: item.width * item.height)


def find_button(page: Page, text: Optional[str] = None) -> Optional[ButtonCandidate]:
    return pick_candidate(collect_candidates(page, text))
