# -*- coding: utf-8 -*-
"""统一品牌常量（v37 起程序更名 Free Chart）。

名字为什么改：旧名 CryptoTicker 只说了「加密行情」，但程序早已覆盖
A 股 / 港股 / 美股 / 链上合约，而且最花功夫的是 K 线的自由缩放与平移，
外加品种详情与发展历程档案。Free Chart 直接点出主打能力。

兼容性约定（**不要改这几项**）：

  - APP_ID / EXE 文件名 / %APPDATA% 目录 / 注册表自启动值名 / APK 包名
    仍沿用 CryptoTicker。改动会让桌面快捷方式指向失效、用户配置与
    Android 升级数据丢失（历史版本已经踩过一次这个坑）。
  - 只有「用户看得见的文案」使用 APP_NAME / APP_TITLE。
"""
from __future__ import annotations

APP_NAME = "Free Chart"
APP_SUBTITLE = "全市场行情 · 品种档案"
APP_TITLE = "Free Chart · 全市场行情"
APP_TAGLINE = "自由缩放 K 线 · 跨市场行情 · 品种发展历程"
APP_VERSION = "1.5.0"

# 内部标识：文件名 / 配置目录 / 单实例锁 / 包名 / 注册表键名
APP_ID = "CryptoTicker"

TRAY_TOOLTIP = "Free Chart · 行情看板"
BADGE_TOOLTIP = "Free Chart 实时价格 · 右键设置 · 双击打开主窗口"
TRAY_START_TIP = "Free Chart 已启动并隐藏到托盘，单击图标可显示窗口"


def window_title(suffix: str = "") -> str:
    """主窗口标题；suffix 用于价格条模式的品种名。"""
    return f"{APP_TITLE}{(' · ' + suffix) if suffix else ''}"


def about_text() -> str:
    """关于 / 设置页底部的一段说明。"""
    return (f"{APP_NAME} {APP_VERSION}\n{APP_TAGLINE}\n"
            "品种发展历程为离线公开资料整理，核验于 2026-11-14；"
            "行情数值来自公开接口，未返回的字段一律标注缺失，不构成投资建议。")
