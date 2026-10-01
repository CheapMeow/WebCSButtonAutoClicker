# ButtonAutoClicker

在后台检测并点击目标网页（代称 WebCS）里由本地配置指定的按钮。整个过程中 Edge 窗口不会被激活，前台窗口保持在你正在使用的应用上。

按钮文字与目标页面地址都放在 `config.local.json` 里，这个文件被 `.gitignore` 忽略，不会进入仓库。

## 工作原理

工具通过 Chrome DevTools Protocol 连接到已经打开的 Edge 窗口，在页面里用 JavaScript 找到按钮，再用 CDP 的 `Input.dispatchMouseEvent` 在按钮中心派发一次真实鼠标点击。CDP 派发的输入事件不需要窗口获得焦点，所以点击发生在后台。

Edge 只有在启动时带了 `--remote-debugging-port` 才允许这种连接，因此需要用本工具的 `launch-edge` 启动一个专用 Edge 窗口（独立的 `--user-data-dir`，不影响你日常使用的 Edge）。

### 从 `page.mouse.click` 到 CDP 命令

代码里直接写的是 Playwright 的高层 API（[`src/button_auto_clicker/clicker.py:83`](src/button_auto_clicker/clicker.py)）：

```python
page.mouse.move(x, y)
page.mouse.click(x, y)
```

`Input.dispatchMouseEvent` 是这两行最终发出的协议命令，中间隔着三层：

| 层 | 位置 | 做的事 |
| --- | --- | --- |
| Python API | `playwright/_impl/_input.py` | `move` 发出通道命令 `mouseMove`，`click` 发出 `mouseClick`，只传参数，不发协议包 |
| Node 驱动 | Playwright 自带驱动里的 `RawMouseImpl` | 把通道命令翻译成 `Input.dispatchMouseEvent`：移动是 `type: "mouseMoved"`，按下是 `mousePressed`，抬起是 `mouseReleased` |
| 浏览器 | Edge 的渲染进程 | 通过页面自己的 CDP 会话收到命令并派发输入事件 |

一次点击在驱动里展开成 `move` + `down` + `up`，所以实际是三条 `Input.dispatchMouseEvent`。命中测试的 `page.evaluate` 走的是同一条 CDP 连接，只是用的是 Runtime 域。整个过程中事件由渲染进程直接接收，不经过窗口焦点，因此点击发生在后台。

`Page` 类型来自 `from playwright.sync_api import Page`，只用于类型标注；真正的页面对象由 `connect_over_cdp` 得到。

## 安装

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## 配置

复制模板后填写自己的页面地址与按钮文字：

```powershell
Copy-Item config.example.json config.local.json
```

| 字段 | 说明 |
| --- | --- |
| `target_url` | 目标页面地址，必填 |
| `primary_button_text` | 第一个按钮的文字，必填 |
| `button_sequence` | 每轮依次点击的按钮文字，必填，可见的才点 |
| `end_texts` | 判定终止状态的按钮文字，任一可见即认为可以点击序列，留空时取 `button_sequence` |
| `url_marker` | 识别目标页面的地址特征串，留空时取 `target_url` 的主机名 |
| `cdp_port` | Edge 远程调试端口 |
| `edge_path` | Edge 可执行文件路径 |
| `edge_user_data_dir` | 专用 Edge 窗口的用户数据目录 |
| `poll_interval_seconds` | `watch` 每轮之间的间隔 |

## 使用

```powershell
# 启动专用 Edge 窗口并打开目标页面（默认收进任务栏，不抢占焦点）
.\.venv\Scripts\button-clicker.exe launch-edge
# 需要在这个窗口里完成登录时用 --show 直接显示窗口
.\.venv\Scripts\button-clicker.exe launch-edge --show

# 查看调试端口与页面
.\.venv\Scripts\button-clicker.exe status

# 列出页面上匹配 primary_button_text 的候选元素，用于排查
.\.venv\Scripts\button-clicker.exe detect

# 查看当前状态：可执行序列还是等待中
.\.venv\Scripts\button-clicker.exe state

# 只点击一次某个按钮
.\.venv\Scripts\button-clicker.exe click --text "按钮文字"

# 按 button_sequence 执行一次
.\.venv\Scripts\button-clicker.exe cycle

# 持续循环：等待状态下一直检测，一旦进入终止状态就点完序列
.\.venv\Scripts\button-clicker.exe watch
```

## 状态判定与点击确认

页面只有两种状态，判定依据是 `end_texts` 里的文字有没有任意一个出现在页面上：

| 状态 | 判定依据 | 行为 |
| --- | --- | --- |
| `ended`（终止状态） | `end_texts` 里至少一个按钮可见 | 按顺序检测 `button_sequence` 里的按钮，可见就点击 |
| `running`（进行中） | 这些按钮都不可见 | 不点击，等待 `poll_interval_seconds` 后重新检测 |

进入终止状态后的点击流程是逐个独立判断的，而不是要求序列里的按钮同时存在：

- 先检测序列里的第一个按钮，可见就点击，然后继续往下处理下一个按钮；
- 再检测第二个按钮，可见就点击；
- 某个按钮当前不可见就直接跳过，比如你自己已经点过第一个按钮时，只会点击第二个。

每次点击都会做一次确认：点击后等待 1.2 秒，重新检测这个按钮，只有当按钮消失或者状态发生变化时才算点击生效，日志里显示 `confirmed=True`。按钮仍然可见且状态没变时会判定为 `ClickNotConfirmedError`，日志里记为 `skipped` 并在下一轮重试。

`watch` 的日志形如：

```
[16:19:35] state=ended (sequence ready) -> visible <按钮一>
[16:19:35] clicked [<按钮一>] at (621.7, 1215.2) on <span> | state ended -> ended | confirmed=True
[16:19:35] clicked [<按钮二>] at (710.1, 1217.2) on <span> | state ended -> running | confirmed=True
[16:19:35] state after: running (nothing to click)
[16:19:48] state=running (nothing to click) -> waiting
```

## 打包成单个 exe

```powershell
.\scripts\build_exe.ps1
```

产物是 `dist\button-clicker.exe`，需要把 `config.local.json` 放在 exe 同级目录（或通过环境变量 `BUTTONCLICKER_CONFIG_FILE` 指向配置文件）。

## 已知约束

- 只支持主框架里的按钮，子框架内的按钮会被拒绝点击。
- 按钮必须完整落在视口内，否则会拒绝点击而不会猜测坐标。
