# -*- coding: utf-8 -*-
"""CryptoTicker 程序入口。

启动参数 --minimized（注册表开机自启写入）：窗口不显示，
只在右下角托盘运行；手动双击 EXE 时仍正常显示窗口。
"""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core import brand
from core.config import Config
from ui.main_window import MainWindow
from ui.theme import apply_global


def _install_error_guard():
    """未捕获异常只写日志，不弹任何系统错误框。

    打包成窗口化 EXE 后，PyInstaller 会给未捕获异常弹一个模态错误框；
    一旦异常发生在定时器/绘制回调里就会反复弹，把界面卡死。这里统一
    接管 sys.excepthook：写 %APPDATA%/CryptoTicker/error.log 后继续运行。
    """
    import os
    import time
    import traceback

    log = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"),
                       "CryptoTicker", "error.log")

    def hook(exc_type, exc, tb):
        try:
            os.makedirs(os.path.dirname(log), exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write("\n===== %s =====\n"
                        % time.strftime("%Y-%m-%d %H:%M:%S"))
                traceback.print_exception(exc_type, exc, tb, file=f)
        except OSError:
            pass

    sys.excepthook = hook


_SERVER_NAME = "CryptoTicker-Single-Instance-v1"
_MUTEX_NAME = "Local\\CryptoTicker_Single_Instance"
_mutex_handle = None


def _acquire_mutex() -> bool:
    """命名互斥量判重。返回 True 表示本进程是主实例。

    不用管道判重：程序若有一份是提权运行的，另一份普通权限去 connect 会
    被「拒绝访问」，判重就失效了，结果还是会开出两个窗口。互斥量由内核
    在进程退出时自动释放，崩溃也不会留下残骸。
    """
    global _mutex_handle
    if _mutex_handle:
        return True                      # 本进程已持有，幂等
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = k32.CreateMutexW(None, False, _MUTEX_NAME)
        if not handle:
            # 创建失败最常见的原因是「已有更高权限的实例持有同名互斥量」
            # （ERROR_ACCESS_DENIED = 5）。这种情况说明确实已经有一个在跑，
            # 必须当从实例退出，否则又会出现两个窗口抢位置。
            return ctypes.get_last_error() != 5
        _mutex_handle = handle
        return ctypes.get_last_error() != 183   # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def _send_wake():
    """尽力把已有实例叫到前台；管道不可用（权限/未监听）时静默跳过。"""
    try:
        from PySide6.QtNetwork import QLocalSocket
    except ImportError:
        return
    sock = QLocalSocket()
    sock.connectToServer(_SERVER_NAME)
    if not sock.waitForConnected(400):
        sock.abort()
        return
    try:
        sock.write(b"wake")
        sock.flush()
        sock.waitForBytesWritten(400)
    finally:
        sock.disconnectFromServer()


def _claim_single_instance(app) -> bool:
    """单实例保护。返回 True 表示本进程是主实例。

    开机自启会在托盘留一个实例，用户再双击图标就会起第二个：两个全屏
    窗口互相抢焦点、两个常驻价格条叠在同一位置、两个托盘图标各自弹气泡，
    表现就是「疯狂弹窗 + 疯狂抖动」。
    """
    if not _acquire_mutex():
        _send_wake()
        return False

    try:
        from PySide6.QtNetwork import QLocalServer
    except ImportError:
        return True
    QLocalServer.removeServer(_SERVER_NAME)
    server = QLocalServer(app)
    try:
        server.listen(_SERVER_NAME)
    except Exception:
        return True
    app._single_server = server
    return True


def _wake_existing(window, server):
    """第二个进程发来「wake」：把主窗口从托盘/最小化恢复到前台。"""
    conn = server.nextPendingConnection()
    if conn is None:
        return
    conn.readAll()
    try:
        window.reveal()
    except RuntimeError:
        pass
    conn.disconnected.connect(conn.deleteLater)


def _sync_shortcut_icon():
    """让桌面 / 开始菜单快捷方式的图标跟随当前 EXE 图标。

    PyInstaller 重打包后 EXE 路径不变，Windows 会继续用图标缓存里的旧图；
    core.shortcut 把 ICO 落到带内容哈希的文件并重写快捷方式指向它。
    失败不影响主程序（只是图标没刷新）。
    """
    try:
        from core.shortcut import sync_shortcuts
        sync_shortcuts()
    except Exception:
        pass


def main():
    _install_error_guard()
    app = QApplication(sys.argv)
    app.setApplicationName(brand.APP_NAME)
    # 托盘常驻时不能因为"最后一个窗口关闭"而退出
    app.setQuitOnLastWindowClosed(False)
    apply_global(app)          # 尽早注册内置 IBM Plex 字体

    config = Config()
    # 先抢单实例锁：已有实例在跑就直接唤醒它，不再重复开窗
    if not _claim_single_instance(app):
        return
    # 老版本写入的开机自启命令没有 --minimized，启动时静默升级一次
    if getattr(sys, "frozen", False):
        from core.autostart import is_enabled, set_enabled
        if is_enabled():
            set_enabled(True)
    window = MainWindow(config)
    server = getattr(app, "_single_server", None)
    if server is not None:
        server.newConnection.connect(lambda: _wake_existing(window, server))

    hidden = "--minimized" in sys.argv[1:] and bool(config.get("start_in_tray"))
    if hidden:
        window.start_minimized()
    else:
        # 构造期间窗口被 WA_DontShowOnScreen 压住，这里才让它上屏
        window.prepare_show()
    # 后台把主流品种的历史 K 线批量落盘，之后浏览直接读本地 SQLite
    window.start_prefetch()
    # 股票真实 logo（公司标志 / 品牌商标）：后台串行抓取并缓存
    window.start_stock_logos()
    if getattr(sys, "frozen", False):
        # 延迟到窗口出来后再同步图标，避免拖慢启动；线程里做文件 / COM 操作
        import threading
        QTimer.singleShot(2000, lambda: threading.Thread(
            target=_sync_shortcut_icon, daemon=True).start())
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
