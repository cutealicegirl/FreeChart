# -*- coding: utf-8 -*-
"""开机启动开关。

通过写注册表 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
实现当前用户的开机自启，无需管理员权限。

v38：注册表值名（任务管理器「启动应用」里能看到的名字）随品牌改为
`Free Chart`，并在每次设置时清理旧名 `CryptoTicker` 的残留项，避免旧值
仍指向更名前的 EXE 造成重复启动或失效。
"""
import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Free Chart"
LEGACY_NAMES = ("CryptoTicker",)


def _command() -> str:
    """开机启动命令行：带 --minimized，让程序启动后直接进托盘。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后的 exe
        return f'"{sys.executable}" --minimized'
    return (f'"{sys.executable}" '
            f'"{os.path.join(_app_dir(), "main.py")}" --minimized')


def _app_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cleanup_legacy(key) -> None:
    """删除更名前遗留的旧注册表值（不存在时静默忽略）。"""
    import winreg
    for old in LEGACY_NAMES:
        try:
            winreg.DeleteValue(key, old)
        except OSError:
            pass


def is_enabled() -> bool:
    """检查当前用户是否已设置开机启动（兼容更名前写入的旧值名）。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            for name in (APP_NAME,) + LEGACY_NAMES:
                try:
                    winreg.QueryValueEx(key, name)
                    return True
                except OSError:
                    continue
            return False
    except (OSError, ImportError):
        return False


def set_enabled(enable: bool) -> bool:
    """设置或取消开机启动。返回是否成功。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            _cleanup_legacy(key)
            if enable:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass  # 本来就没有，视为成功
        return True
    except OSError:
        return False
