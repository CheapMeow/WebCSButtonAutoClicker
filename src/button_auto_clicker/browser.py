import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from . import config


class EdgeUnavailableError(RuntimeError):
    pass


class TargetPageNotFoundError(RuntimeError):
    pass


class CdpSession:
    def __init__(self, playwright: Playwright, browser: Browser):
        self._playwright = playwright
        self.browser = browser

    def close(self) -> None:
        self.browser.close()
        self._playwright.stop()

    def __enter__(self) -> "CdpSession":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def devtools_online(port: int) -> Optional[dict]:
    request = urllib.request.Request("http://127.0.0.1:{0}/json/version".format(port))
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def wait_for_devtools(port: int, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        version = devtools_online(port)
        if version is not None:
            return version
        time.sleep(0.3)
    raise EdgeUnavailableError(
        "Edge 的调试端口 {0} 在 {1} 秒内没有就绪，请检查 Edge 是否以 --remote-debugging-port={0} 启动".format(port, timeout)
    )


SW_SHOWMINNOACTIVE = 7


def _startup_info(minimize: bool) -> Optional[subprocess.STARTUPINFO]:
    if not minimize or not hasattr(subprocess, "STARTUPINFO"):
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = SW_SHOWMINNOACTIVE
    return info


def launch_edge(
    url: Optional[str] = None,
    port: Optional[int] = None,
    headless: bool = False,
    user_data_dir: Optional[Path] = None,
    edge: Optional[Path] = None,
    extra_args: Optional[List[str]] = None,
    minimize: bool = True,
) -> dict:
    port = port if port is not None else config.cdp_port()
    edge = Path(edge) if edge is not None else config.edge_path()
    user_data_dir = Path(user_data_dir) if user_data_dir is not None else config.edge_user_data_dir()
    url = url if url is not None else config.target_url()

    if not edge.exists():
        raise EdgeUnavailableError("没有找到 Edge 可执行文件：{0}，请通过环境变量 BUTTONCLICKER_EDGE_PATH 指定".format(edge))

    if devtools_online(port) is not None:
        return devtools_online(port)

    user_data_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(edge),
        "--remote-debugging-port={0}".format(port),
        "--remote-allow-origins=*",
        "--user-data-dir={0}".format(user_data_dir),
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-features=Translate,OptimizationHints",
    ]
    if headless:
        command.append("--headless=new")
    if extra_args:
        command.extend(extra_args)
    command.append(url)

    subprocess.Popen(
        command,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
        startupinfo=_startup_info(minimize and not headless),
    )
    return wait_for_devtools(port)


def connect(port: Optional[int] = None) -> CdpSession:
    port = port if port is not None else config.cdp_port()
    version = devtools_online(port)
    if version is None:
        raise EdgeUnavailableError(
            "调试端口 {0} 上没有 Edge，请先运行 button-clicker launch-edge 启动专用 Edge 窗口".format(port)
        )
    playwright = sync_playwright().start()
    browser = playwright.chromium.connect_over_cdp(config.cdp_endpoint(port))
    return CdpSession(playwright, browser)


def all_pages(browser: Browser) -> List[Page]:
    pages: List[Page] = []
    for context in browser.contexts:
        pages.extend(context.pages)
    return pages


def find_target_page(browser: Browser, marker: Optional[str] = None) -> Page:
    marker = marker if marker is not None else config.url_marker()
    for page in all_pages(browser):
        if marker in page.url:
            return page
    raise TargetPageNotFoundError(
        "没有在 Edge 里找到地址包含 {0} 的页面，当前页面：{1}".format(
            marker, [page.url for page in all_pages(browser)]
        )
    )
