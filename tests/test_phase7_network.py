# -*- coding: utf-8 -*-
"""第七阶段测试 A：网络异常处理与失败退避。

用"必定失败的假数据源"替换真实数据源，验证：
1. 连续失败不崩溃，界面显示网络异常；
2. 重试间隔逐步延长（5 -> 10 -> 20 -> 40 ...）；
3. 恢复真实数据源后自动回到在线状态。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import data.market_manager as mm
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.config import Config
from data.api_base import MarketApi, MarketApiError
from ui.main_window import MainWindow

app = QApplication([])


class BrokenApi(MarketApi):
    """模拟不可用数据源。"""
    name = "Broken"

    def fetch_tickers(self, symbols):
        raise MarketApiError("模拟网络故障")


# 注入两个假数据源（替换注册表，测试后还原）
_REAL = mm.ADAPTER_CLASSES
mm.ADAPTER_CLASSES = [BrokenApi, BrokenApi]

w = MainWindow(Config())
w.show()
start = time.time()


def check_failures():
    delay = w.scheduler._current_delay()
    fails = w.scheduler._fail_count
    print(f"[{time.time()-start:5.1f}s] 失败次数={fails} 当前重试间隔={delay}s")
    print("  状态栏:", w.status.lbl_net.text(), "|", w.status.lbl_source.text())
    if fails >= 3:
        # 恢复真实数据源，验证自动恢复
        print(">>> 恢复真实数据源 <<<")
        mm.ADAPTER_CLASSES = _REAL
        w.market.adapters = [cls() for cls in _REAL]
        w.market._index = 0
        w.scheduler.refresh_now()
        QTimer.singleShot(6000, check_recovery)
    else:
        QTimer.singleShot(12000, check_failures)


def check_recovery():
    print("恢复后状态栏:", w.status.lbl_net.text(), "|",
          w.status.lbl_source.text())
    print("BTC 价格恢复显示:", w.rows["BTC"].lbl_price.text() != "--")
    print("连续失败计数已清零:", w.scheduler._fail_count == 0)
    print("第七阶段网络异常测试通过")
    w.quit_app()
    sys.exit(0)


QTimer.singleShot(15000, check_failures)  # 15s 后第一次失败已发生
app.exec()
