# ClipNest

一个只在你本机运行的 Windows 剪贴板历史工具。按一次热键，最近复制过的文字、图片、文件全在里面，选中就能粘回去。

**不联网。不上传。不注册账号。** 数据只写在你自己的 `%APPDATA%\ClipNest` 目录里。

| 浅色 | 深色 |
|---|---|
| ![浅色](docs/screenshots/light.png) | ![深色](docs/screenshots/dark.png) |

## 它做什么

- 后台记录你复制的**文本、图片、文件路径**，不打断任何操作
- 全局热键 `Ctrl+Alt+V` 呼出居中面板，键盘上下选、回车即粘贴
- 支持搜索，中文可直接搜；重复内容自动去重并置顶
- 密码管理器标记为「不要记录」的内容会被自动跳过
- 托盘常驻，可随时暂停监听

## 快捷键

| 操作 | 按键 |
|---|---|
| 呼出面板 | `Ctrl+Alt+V` |
| 选择 | `↑` `↓` 或直接点击 |
| 粘贴 | `Enter` |
| 只复制不粘贴 | `Ctrl+Enter` |
| 直接粘贴第 N 条 | `Ctrl+1` ~ `Ctrl+9` |
| 固定 / 取消固定 | `Ctrl+P` |
| 删除当前条目 | `Delete` |
| 关闭面板 | `Esc` |

## 为什么又一个剪贴板工具

Windows 自带的 Win+V 没有搜索、没有固定、条数少、重启就丢，图片支持也弱。Ditto 功能全但界面停在二十年前。ClipNest 的目标很简单：**长得像 Win11 自带的，用起来比 Win+V 强**。

## 环境要求

- Windows 10 1809 及以上
- Python 3.11+（仅源码运行需要）

## 本地运行

```bash
git clone https://github.com/Moistwood/ClipNest.git
cd ClipNest
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

启动后程序驻留托盘，按 `Ctrl+Alt+V` 呼出面板。配置文件在 `%APPDATA%\ClipNest\config.json`，改完热键需要重启生效。

## 测试

```bash
set QT_QPA_PLATFORM=offscreen
python -m unittest discover -s tests -v
```

界面测试用 offscreen 平台渲染整窗，不需要真实显示器；存储层测试不依赖 Qt。

## 打包

双击 `build.bat`，或者手动：

```bash
python -m nuitka --standalone --enable-plugin=pyside6 ^
  --windows-console-mode=disable --output-dir=build run.py
```

产物在 `build\run.dist\`，整个目录一起分发。推 `v*` 标签时 GitHub Actions 会自动打包并发布 Release。

## 已知限制

- **目标窗口以管理员身份运行时，粘贴注入会失效**（Windows 的 UIPI 隔离机制）。需要往管理员窗口粘贴时，ClipNest 自己也得提权运行。
- 带有 `ExcludeClipboardContentFromMonitorProcessing` 标记的内容不会被记录，这是刻意行为。
- 数据库写入目前在主线程完成。文字复制无感知，超大图片可能有几十毫秒延迟。
- 不记录富文本格式，HTML/RTF 会被降级成纯文本。

## 隐私

ClipNest 没有任何网络代码。你可以用防火墙或者抓包工具验证这一点，这是这个项目唯一重要的承诺。如果哪天你发现它有联网行为，那一定是被篡改了。

## 协议

GPL-3.0。你可以随意使用、修改、分发，但衍生作品必须同样开源。
