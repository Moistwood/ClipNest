# ClipNest

一个只在你本机运行的 Windows 剪贴板历史工具。按一次热键，最近复制过的文字、图片、文件全在里面，选中就能粘回去。

**不联网。不上传。不注册账号。** 数据只写在你自己的 `%APPDATA%\ClipNest` 目录里。

## 它做什么

- 后台记录你复制的**文本、图片、文件路径**，不打断任何操作
- 全局热键呼出居中面板，键盘上下选、回车即粘贴
- 支持模糊搜索，中文可直接搜
- 重复内容自动去重并置顶，不会堆一堆一样的条目
- 密码管理器标记为「不要记录」的内容会被自动跳过
- 托盘常驻，可随时暂停监听

## 为什么又一个剪贴板工具

Windows 自带的 Win+V 没有搜索、没有收藏、条数少、重启就丢，图片支持也弱。Ditto 功能全但界面停在二十年前。ClipNest 的目标很简单：**长得像 Win11 自带的，用起来比 Win+V 强**。

## 状态

开发中，接口和数据结构还会变。当前版本可编译、可运行，尚未打包发布。

## 环境要求

- Windows 10 1809 及以上（圆角和 Mica 毛玻璃需要 Win11 22H2+，低版本会自动降级为纯色圆角）
- Python 3.11+

## 本地运行

```bash
git clone https://github.com/Moistwood/ClipNest.git
cd ClipNest
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

启动后程序驻留托盘，按 `Ctrl+Alt+V` 呼出面板。

## 打包

```bash
pip install nuitka
python -m nuitka --standalone --enable-plugin=pyside6 ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=assets/app.ico run.py
```

## 已知限制

- **目标窗口以管理员身份运行时，粘贴注入会失效**（Windows 的 UIPI 隔离机制）。如果需要往管理员窗口里粘贴，ClipNest 本身也必须以管理员身份运行。
- 带有 `ExcludeClipboardContentFromMonitorProcessing` 标记的内容不会被记录，这是刻意行为。
- 目前所有数据库写入都在主线程完成。文字复制无感知，超大图片（>20MB）可能有几十毫秒延迟。

## 隐私

ClipNest 没有任何网络代码。你可以用防火墙或者抓包工具验证这一点，这是这个项目唯一重要的承诺。如果哪天你发现它有联网行为，那一定是被篡改了。

## 协议

GPL-3.0。你可以随意使用、修改、分发，但衍生作品必须同样开源。
