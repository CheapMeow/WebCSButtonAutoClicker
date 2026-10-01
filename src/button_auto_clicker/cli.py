import argparse
import sys
import time
from typing import List, Optional

from . import browser as browser_module
from . import clicker
from . import config
from . import detector
from . import state as state_module


def _add_launch_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default=None, help="要打开的目标页面地址")
    parser.add_argument("--port", type=int, default=None, help="Edge 远程调试端口")
    parser.add_argument("--headless", action="store_true", help="以无界面方式启动，用于自动化冒烟测试")
    parser.add_argument("--show", action="store_true", help="正常显示窗口，默认只是收进任务栏而不抢占焦点")


def _command_launch_edge(arguments: argparse.Namespace) -> int:
    version = browser_module.launch_edge(
        url=arguments.url,
        port=arguments.port,
        headless=arguments.headless,
        minimize=not arguments.show,
    )
    print("Edge devtools ready: {0}".format(version.get("Browser")))
    print("endpoint: {0}".format(config.cdp_endpoint(arguments.port)))
    return 0


def _command_status(arguments: argparse.Namespace) -> int:
    port = arguments.port if arguments.port is not None else config.cdp_port()
    version = browser_module.devtools_online(port)
    if version is None:
        print("Edge devtools offline on port {0}".format(port))
        return 1
    print("Edge devtools online on port {0}: {1}".format(port, version.get("Browser")))
    with browser_module.connect(port) as session:
        pages = browser_module.all_pages(session.browser)
        for page in pages:
            print("page: {0}".format(page.url))
    return 0


def _command_detect(arguments: argparse.Namespace) -> int:
    text = arguments.text if arguments.text is not None else config.primary_button_text()
    with browser_module.connect(arguments.port) as session:
        page = browser_module.find_target_page(session.browser, arguments.marker)
        print("page: {0}".format(page.url))
        candidates = detector.collect_candidates(page, text)
        if not candidates:
            print("no candidate found for text: {0}".format(text))
            return 1
        for index, candidate in enumerate(candidates):
            print("[{0}] {1}".format(index, candidate.describe()))
            print("    html: {0}".format(candidate.outer_html))
        chosen = detector.pick_candidate(candidates)
        print("chosen: {0}".format(chosen.describe()))
    return 0


def _command_click(arguments: argparse.Namespace) -> int:
    text = arguments.text if arguments.text is not None else config.primary_button_text()
    with browser_module.connect(arguments.port) as session:
        page = browser_module.find_target_page(session.browser, arguments.marker)
        candidate = detector.find_button(page, text)
        if candidate is None:
            print("button not found: {0}".format(text))
            return 1
        result = clicker.click_candidate(page, candidate)
        print(result.describe())
    return 0


def _add_cycle_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", type=int, default=None, help="Edge 远程调试端口")
    parser.add_argument("--marker", default=None, help="目标页面地址的特征串，默认取配置里的网址主机名")
    parser.add_argument("--texts", nargs="+", default=None, help="要依次点击的按钮文字，默认取配置里的 button_sequence")
    parser.add_argument(
        "--end-texts",
        nargs="+",
        default=None,
        help="判定终止状态的按钮文字，任一可见即认为可点击，默认取配置里的 end_texts",
    )


def _texts(arguments: argparse.Namespace) -> List[str]:
    return list(arguments.texts) if arguments.texts else config.button_sequence()


def _end_texts(arguments: argparse.Namespace) -> List[str]:
    return list(arguments.end_texts) if arguments.end_texts else config.end_texts()


def _command_state(arguments: argparse.Namespace) -> int:
    end_texts = list(arguments.end_texts) if arguments.end_texts else config.end_texts()
    with browser_module.connect(arguments.port) as session:
        page = browser_module.find_target_page(session.browser, arguments.marker)
        visible = state_module.visible_texts(page, end_texts)
        current = state_module.detect_state(page, end_texts)
        print("page: {0}".format(page.url))
        print("state: {0}".format(state_module.describe_state(current)))
        print("visible buttons: {0}".format(state_module.describe_visible(visible)))
    return 0


def _command_cycle(arguments: argparse.Namespace) -> int:
    texts = _texts(arguments)
    end_texts = _end_texts(arguments)
    with browser_module.connect(arguments.port) as session:
        page = browser_module.find_target_page(session.browser, arguments.marker)
        visible = state_module.visible_texts(page, end_texts)
        before = state_module.detect_state(page, end_texts)
        print("state: {0} | visible buttons: {1}".format(
            state_module.describe_state(before), state_module.describe_visible(visible)
        ))
        if before != state_module.ENDED:
            print("skip: nothing to click in the current state")
            return 1
        results = clicker.run_cycle(page, texts, state_texts=end_texts)
        if not results:
            print("skip: none of {0} is visible".format(" / ".join(texts)))
            return 1
        for result in results:
            print(result.describe())
        after = state_module.detect_state(page, end_texts)
        print("state after: {0}".format(state_module.describe_state(after)))
    return 0


def _command_watch(arguments: argparse.Namespace) -> int:
    texts = _texts(arguments)
    end_texts = _end_texts(arguments)
    interval = arguments.interval if arguments.interval is not None else config.poll_interval_seconds()
    print("watching {0} every {1}s on {2}".format(" -> ".join(texts), interval, config.cdp_endpoint(arguments.port)))
    print("the sequence runs when any of these is visible: {0}".format(" / ".join(end_texts)))
    with browser_module.connect(arguments.port) as session:
        while True:
            stamp = time.strftime("%H:%M:%S")
            try:
                page = browser_module.find_target_page(session.browser, arguments.marker)
                visible = state_module.visible_texts(page, end_texts)
                current = state_module.detect_state(page, end_texts)
                if current != state_module.ENDED:
                    print("[{0}] state={1} -> waiting".format(stamp, state_module.describe_state(current)), flush=True)
                else:
                    print(
                        "[{0}] state={1} -> visible {2}".format(
                            stamp, state_module.describe_state(current), state_module.describe_visible(visible)
                        ),
                        flush=True,
                    )
                    results = clicker.run_cycle(page, texts, state_texts=end_texts)
                    if not results:
                        print("[{0}] none of {1} is visible".format(stamp, " / ".join(texts)), flush=True)
                    for result in results:
                        print("[{0}] {1}".format(stamp, result.describe()), flush=True)
                    print(
                        "[{0}] state after: {1}".format(
                            stamp, state_module.describe_state(state_module.detect_state(page, end_texts))
                        ),
                        flush=True,
                    )
            except clicker.ButtonNotFoundError as error:
                print("[{0}] waiting: {1}".format(stamp, error), flush=True)
            except (clicker.ClickRejectedError, clicker.ClickNotConfirmedError) as error:
                print("[{0}] skipped: {1}".format(stamp, error), flush=True)
            time.sleep(interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="button-clicker", description="在后台检测并点击目标网页里的按钮，不激活 Edge 窗口")
    subparsers = parser.add_subparsers(dest="command", required=True)

    launch = subparsers.add_parser("launch-edge", help="启动带调试端口的独立 Edge 窗口")
    _add_launch_arguments(launch)
    launch.set_defaults(handler=_command_launch_edge)

    status = subparsers.add_parser("status", help="查看 Edge 调试端口与页面列表")
    status.add_argument("--port", type=int, default=None, help="Edge 远程调试端口")
    status.set_defaults(handler=_command_status)

    detect = subparsers.add_parser("detect", help="列出页面上匹配按钮文字的候选元素")
    detect.add_argument("--port", type=int, default=None, help="Edge 远程调试端口")
    detect.add_argument("--marker", default=None, help="目标页面地址的特征串，默认取配置里的网址主机名")
    detect.add_argument("--text", default=None, help="按钮文字")
    detect.set_defaults(handler=_command_detect)

    click = subparsers.add_parser("click", help="检测并点击一次按钮，不激活 Edge 窗口")
    click.add_argument("--port", type=int, default=None, help="Edge 远程调试端口")
    click.add_argument("--marker", default=None, help="目标页面地址的特征串，默认取配置里的网址主机名")
    click.add_argument("--text", default=None, help="按钮文字")
    click.set_defaults(handler=_command_click)

    state = subparsers.add_parser("state", help="查看当前状态：可执行序列还是等待中")
    state.add_argument("--port", type=int, default=None, help="Edge 远程调试端口")
    state.add_argument("--marker", default=None, help="目标页面地址的特征串，默认取配置里的网址主机名")
    state.add_argument("--end-texts", nargs="+", default=None, help="判定终止状态的按钮文字，任一可见即认为可点击")
    state.set_defaults(handler=_command_state)

    cycle = subparsers.add_parser("cycle", help="按顺序检测并点击一次按钮序列")
    _add_cycle_arguments(cycle)
    cycle.set_defaults(handler=_command_cycle)

    watch = subparsers.add_parser("watch", help="循环检测并点击按钮序列，不激活 Edge 窗口")
    _add_cycle_arguments(watch)
    watch.add_argument("--interval", type=float, default=None, help="每轮检测之间的间隔秒数")
    watch.set_defaults(handler=_command_watch)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = build_parser()
    arguments = parser.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return arguments.handler(arguments)
    except KeyboardInterrupt:
        print("stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
