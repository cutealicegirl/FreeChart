# -*- coding: utf-8 -*-
"""Windows 任务栏定位：把常驻实时价格贴到通知区左侧，像任务栏小工具。

Windows 11 已移除 DeskBand（任务栏工具栏）扩展机制，第三方「内存/网速」
小工具普遍采用：无边框置顶窗 + 与任务栏同高 + 紧靠通知区左侧。本模块
只负责算位置与配色，不创建窗口：

- 任务栏矩形用 Qt 的 screen.geometry() 与 availableGeometry() 的差值得到，
  天然是逻辑像素，避免 GetWindowRect 的 DPI 换算问题；
- 通知区左边界用 Win32 FindWindowEx("TrayNotifyWnd") 精确定位，
  Win11 XAML 任务栏取不到时按固定宽度估算；
- **避让其它小工具**：枚举贴在任务栏区域的第三方顶层小窗（内存 / 网速 /
  流量监控等），把自己的位置放到它们左侧，避免叠字；
- 系统浅色 / 深色主题从注册表读取，决定文字用深色还是浅色。
"""
import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import QRect

_DEFAULT_NOTIFY_WIDTH = 190   # 逻辑像素；取不到 TrayNotifyWnd 时的估算宽度
_GAP = 8                      # 与通知区 / 其它小工具之间的间隙
BADGE_TITLE = "__CT_PRICE_BADGE__"   # 自己的窗口标题标记，用于多实例时互不避让

# 系统自身的任务栏 / 桌面窗口类名：不算「别的小工具」
_SHELL_CLASSES = {
    "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW",
    "Shell_InputSwitchTopLevelWindow", "MultitaskingViewFrame",
    "ForegroundStaging", "XamlExplorerHostIslandWindow",
    "TopLevelWindowForOverflowXamlIsland", "Windows.UI.Core.CoreWindow",
    "ApplicationManager_DesktopShellWindow",
    "TaskListThumbnailWnd", "NotifyIconOverflowWindow",
}


def taskbar_rect(full: QRect, avail: QRect) -> QRect:
    """由全屏矩形与可用区矩形反推任务栏矩形（四种贴边方向）。"""
    if avail.bottom() < full.bottom() - 2:      # 底部（最常见）
        return QRect(full.left(), avail.bottom() + 1, full.width(),
                     full.bottom() - avail.bottom())
    if avail.top() > full.top() + 2:            # 顶部
        return QRect(full.left(), full.top(), full.width(),
                     avail.top() - full.top())
    if avail.left() > full.left() + 2:          # 左侧
        return QRect(full.left(), full.top(),
                     avail.left() - full.left(), full.height())
    if avail.right() < full.right() - 2:        # 右侧
        return QRect(avail.right() + 1, full.top(),
                     full.right() - avail.right(), full.height())
    # 无任务栏（离屏测试 / 自动隐藏）：按底部 40px 处理
    return QRect(full.left(), full.bottom() - 40, full.width(), 40)


def notify_left(screen) -> int | None:
    """通知区左边界（逻辑像素）；Win11 取不到子窗口时返回 None。"""
    try:
        u = ctypes.windll.user32
        tray = u.FindWindowW("Shell_TrayWnd", None)
        if not tray:
            return None
        child = u.FindWindowExW(tray, 0, "TrayNotifyWnd", None)
        if not child:
            return None
        r = wintypes.RECT()
        if not u.GetWindowRect(child, ctypes.byref(r)):
            return None
        dpr = screen.devicePixelRatio() or 1.0
        return int(r.left / dpr)
    except Exception:
        return None


def busy_widget_lefts(screen, exclude=()) -> list[int]:
    """贴在任务栏区域的「别的程序小工具」左边界（逻辑像素，升序）。

    内存 / 网速 / 流量监控这类工具通常是「无边框置顶小窗」，不一定挂
    在任务栏子窗口里，因此用 EnumWindows 扫描顶层窗口，按以下条件挑选：
    可见、未最小化、不是本进程、不是系统外壳窗口、尺寸与任务栏条带匹配、
    位于屏幕右半侧。返回值用来把自己的小工具摆到它们左侧。
    """
    try:
        u = ctypes.windll.user32
    except Exception:
        return []
    full = screen.geometry()
    tb = taskbar_rect(full, screen.availableGeometry())
    if tb.width() < tb.height():        # 竖向任务栏的特殊排版，暂不避让
        return []
    dpr = screen.devicePixelRatio() or 1.0
    screen_w = int(full.width() * dpr)
    tb_top = int(tb.top() * dpr)
    tb_bottom = int(tb.bottom() * dpr)
    tb_h = max(1, tb_bottom - tb_top)
    exclude = {int(h) for h in exclude if h}
    pid = os.getpid()

    def _class_name(hwnd):
        buf = ctypes.create_unicode_buffer(128)
        u.GetClassNameW(hwnd, buf, 128)
        return buf.value

    def _title(hwnd):
        buf = ctypes.create_unicode_buffer(128)
        u.GetWindowTextW(hwnd, buf, 128)
        return buf.value

    def _pid_of(hwnd):
        p = wintypes.DWORD(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        return int(p.value)

    out = []
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        if hwnd in exclude or not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
            return True
        if _pid_of(hwnd) == pid:
            return True
        if _class_name(hwnd) in _SHELL_CLASSES:
            return True
        if _title(hwnd) == BADGE_TITLE:
            return True                       # 另一个实例的同类价格条，互不避让
        r = wintypes.RECT()
        if not u.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w = r.right - r.left
        h = r.bottom - r.top
        if w < 24 or h < 16:
            return True
        if w > screen_w * 0.35 or h > tb_h * 2.2:
            return True                       # 普通应用窗口，不是任务栏小工具
        if r.right < screen_w * 0.55:
            return True                       # 左半侧不是小工具常驻区
        if r.bottom < tb_top + 2 or r.top > tb_bottom + tb_h:
            return True                       # 没有贴着任务栏条带
        found.append((r.left, r.top, w, h))
        return True

    try:
        u.EnumWindows(_cb, 0)
    except Exception:
        return []
    for left, _top, _w, _h in found:
        out.append(int(left / dpr))
    return sorted(set(out))


def system_is_light() -> bool:
    """任务栏是否浅色主题（决定小工具文字用深色还是浅色）。"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        return int(val) == 1
    except Exception:
        return False


def dock_geometry(screen, width: int, max_height: int = 46,
                  exclude=(), shift: int = 0):
    """返回 (x, y, w, h)：与任务栏同高，位于其它小工具与通知区左侧。

    exclude: 自己的窗口句柄，避免把自己当成「别的小工具」；
    shift:   用户手动微调的左移像素（正数左移），用于自动避让之外的微调。
    """
    full = screen.geometry()
    tb = taskbar_rect(full, screen.availableGeometry())
    horizontal = tb.width() >= tb.height()
    if horizontal:
        h = max(26, min(max_height, tb.height() - 2))
        w = width
        nl = notify_left(screen)
        if nl is None or not (full.left() + w < nl < full.right() - 20):
            nl = full.right() - _DEFAULT_NOTIFY_WIDTH
        # 先避让通知区，再避让别的小工具：谁更靠左就贴在谁左边
        limit = int(nl)
        for left in busy_widget_lefts(screen, exclude):
            if full.left() + w + 12 < left < limit:
                limit = left
        x = max(full.left() + 4, limit - w - _GAP)
        if shift:
            x = max(full.left() + 4, x - int(shift))
        # 不要盖住最右侧的时钟 / 显示桌面按钮
        if x + w > full.right() - 36:
            x = full.right() - w - 36
        y = tb.top() + (tb.height() - h) // 2
    else:
        w = max(80, min(width, tb.width() - 2))
        h = max(26, min(max_height, 40))
        x = tb.left() + (tb.width() - w) // 2
        y = tb.bottom() - h - 6 - max(0, int(shift))
    return x, y, w, h
