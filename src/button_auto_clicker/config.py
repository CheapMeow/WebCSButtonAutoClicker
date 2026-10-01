import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT

CONFIG_FILE_NAME = "config.local.json"
DEFAULT_EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
DEFAULT_CDP_PORT = 9222

_cache: Optional[Dict[str, Any]] = None


class ConfigMissingError(RuntimeError):
    pass


def config_file() -> Path:
    override = os.environ.get("BUTTONCLICKER_CONFIG_FILE")
    return Path(override) if override else base_dir() / CONFIG_FILE_NAME


def load_config() -> Dict[str, Any]:
    global _cache
    if _cache is None:
        path = config_file()
        if not path.exists():
            _cache = {}
        else:
            _cache = json.loads(path.read_text(encoding="utf-8"))
    return _cache


def required_config() -> Dict[str, Any]:
    values = load_config()
    if not values:
        raise ConfigMissingError(
            "缺少配置文件 {0}，请复制 config.example.json 为 {1} 并填写页面地址与按钮文字".format(
                CONFIG_FILE_NAME, config_file()
            )
        )
    return values


def target_url() -> str:
    values = required_config()
    if "target_url" not in values:
        raise ConfigMissingError("配置文件 {0} 缺少 target_url".format(config_file()))
    return str(values["target_url"])


def primary_button_text() -> str:
    values = required_config()
    if "primary_button_text" not in values:
        raise ConfigMissingError("配置文件 {0} 缺少 primary_button_text".format(config_file()))
    return str(values["primary_button_text"])


def button_sequence() -> list:
    values = required_config()
    configured = values.get("button_sequence")
    if not configured:
        raise ConfigMissingError("配置文件 {0} 缺少 button_sequence".format(config_file()))
    return [str(text) for text in configured]


def end_texts() -> list:
    configured = load_config().get("end_texts")
    if configured:
        return [str(text) for text in configured]
    return button_sequence()


def url_marker() -> str:
    marker = load_config().get("url_marker")
    if marker:
        return str(marker)
    hostname = urlparse(target_url()).hostname
    if not hostname:
        raise ConfigMissingError("配置文件 {0} 的 target_url 不是合法网址".format(config_file()))
    return hostname


def cdp_port() -> int:
    return int(load_config().get("cdp_port", DEFAULT_CDP_PORT))


def cdp_endpoint(port: Optional[int] = None) -> str:
    return "http://127.0.0.1:{0}".format(port if port is not None else cdp_port())


def edge_path() -> Path:
    return Path(str(load_config().get("edge_path", DEFAULT_EDGE_PATH)))


def edge_user_data_dir() -> Path:
    configured = load_config().get("edge_user_data_dir")
    return Path(str(configured)) if configured else base_dir() / ".edge-profile"


def poll_interval_seconds() -> float:
    return float(load_config().get("poll_interval_seconds", 1.0))
