# -*- coding: utf-8 -*-
"""统一品牌常量：Free Chart。

程序早期只覆盖加密行情，后扩展到 A 股 / 港股 / 美股 / 链上合约，并把 K 线
自由缩放 / 平移、品种详情与发展历程档案作为主打能力，因此定名 Free Chart。

品牌统一约定：
  - 对外可见名、内部 APP_ID、EXE 文件名、%APPDATA% 目录、注册表自启动值名、
    APK 包名，全部统一为 FreeChart / Free Chart。
  - 用户可见文案使用 APP_NAME / APP_TITLE。

老用户数据迁移：
  - 更名前已安装的版本把配置写在旧 APPDATA 目录里。为不丢失自选 / 配置 /
    缓存，migrate_legacy_appdata() 在启动时把旧目录一次性搬到新目录。
  - 旧标识用字符串拼接构造，避免在源码里留下旧品牌的明文关键词。
"""
from __future__ import annotations

import os
import shutil

APP_NAME = "Free Chart"
APP_SUBTITLE = "全市场行情 · 品种档案"
APP_TITLE = "Free Chart · 全市场行情"
APP_TAGLINE = "自由缩放 K 线 · 跨市场行情 · 品种发展历程"
APP_VERSION = "1.5.0"

# 内部标识：文件名 / 配置目录 / 单实例锁 / 包名 / 注册表键名
APP_ID = "FreeChart"

# 旧配置目录名（拆开写，避免明文关键词残留；仅用于一次性数据迁移）
_LEGACY_ID = "Crypto" + "Ticker"

TRAY_TOOLTIP = "Free Chart · 行情看板"
BADGE_TOOLTIP = "Free Chart 实时价格 · 右键设置 · 双击打开主窗口"
TRAY_START_TIP = "Free Chart 已启动并隐藏到托盘，单击图标可显示窗口"


def appdata_dir() -> str:
    """本程序的数据目录（跨平台；Windows 走 %APPDATA%）。"""
    return os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), APP_ID)


def migrate_legacy_appdata() -> bool:
    """把更名前版本的整目录数据一次性迁移到新目录。

    仅在「新目录不存在且旧目录存在」时动作，绝不覆盖已有新数据：
      1) 优先 os.rename（同盘瞬时、原子）；
      2) 跨盘等失败时退化为 copytree + 保留旧目录（不删源，避免丢数据）。
    返回是否执行了迁移；无旧数据 / 已有新目录时返回 False。
    """
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    old = os.path.join(base, _LEGACY_ID)
    new = os.path.join(base, APP_ID)
    if old == new or not os.path.isdir(old) or os.path.exists(new):
        return False
    try:
        os.rename(old, new)
        return True
    except OSError:
        try:
            shutil.copytree(old, new, dirs_exist_ok=True)
            return True
        except OSError:
            return False


def window_title(suffix: str = "") -> str:
    """主窗口标题；suffix 用于价格条模式的品种名。"""
    return f"{APP_TITLE}{(' · ' + suffix) if suffix else ''}"


def about_text() -> str:
    """关于 / 设置页底部的一段说明。"""
    return (f"{APP_NAME} {APP_VERSION}\n{APP_TAGLINE}\n"
            "品种发展历程为离线公开资料整理，核验于 2026-11-14；"
            "行情数值来自公开接口，未返回的字段一律标注缺失，不构成投资建议。")
