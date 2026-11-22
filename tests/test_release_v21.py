# -*- coding: utf-8 -*-
"""v21 回归：工具条悬停自动展开/收纳 + 看板娘重现后继续说话。

覆盖：
1. 旧配置 chart_tools_open=True（固定展开）不再让悬停行为彻底失效；
2. 鼠标扫过工具条 -> 展开，移开 -> 自动收纳；
3. Enter 事件被顶层悬浮窗吞掉时，坐标轮询仍能展开/收纳；
4. 看板娘被 K 线挡住隐藏后重现，会自动补一句台词（含日语）；
5. 让位期间攒下的台词，重现时优先补说；
6. 气泡到点自动消失，且旧句子的延迟关闭不会误伤新气泡。

全部离线（临时 APPDATA + offscreen）。
"""
import json
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v21_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# 预置「脏配置」：用户上次把工具条固定展开了
os.makedirs(os.path.join(_TMP, "FreeChart"), exist_ok=True)
with open(os.path.join(_TMP, "FreeChart", "config.json"),
          "w", encoding="utf-8") as f:
    json.dump({"chart_tools_open": True, "mascot_enabled": False,
               "mascot_speech": True, "price_badge": False}, f)

from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from core.config import Config
from ui.main_window import MainWindow
from ui.mascot import SPEECH, MascotWindow

app = QApplication([])


def pump(sec=0.1):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


# ================= 1~3. 工具条悬停 =================
cfg = Config()
assert cfg.get("chart_tools_open") is True, "测试应带上脏配置"
w = MainWindow(cfg)
w.resize(900, 760)
w.prepare_show()
pump(0.3)
cv = w.chart_view

sym = next(iter(w.rows))
w._open_chart(sym)
pump(0.3)
assert cv._tools_pinned is False, "启动不该继承旧的固定展开"
assert not cv.tools_panel.isVisible(), "工具条默认应收起"
assert Config().get("chart_tools_open") is False, "脏配置应被纠正"
print("1. 旧的 chart_tools_open=True 不再卡住工具条 OK")

head = cv.tools_head
center = head.mapToGlobal(QPoint(head.width() // 2, head.height() // 2))
away = w.mapToGlobal(QPoint(6, w.height() - 6))

# 1) 正常事件通道
QTest.mouseMove(w, head.mapTo(w, QPoint(head.width() // 2,
                                       head.height() // 2)))
pump(0.08)
assert cv.tools_panel.isVisible(), "鼠标移到细条上应自动展开"
QTest.mouseMove(w, QPoint(6, w.height() - 6))
pump(0.5)
assert not cv.tools_panel.isVisible(), "鼠标移开应自动收纳"
print("2. 鼠标扫过展开 / 离开收纳 OK")

# 2) 去掉事件过滤器，模拟顶层悬浮窗吞掉 Enter/Leave，只留坐标轮询
for hw in (cv.tools_head, cv.tools_panel):
    hw.removeEventFilter(cv)
QCursor.setPos(away)
cv._poll_tools_hover()
pump(0.45)
assert not cv.tools_panel.isVisible()
QCursor.setPos(center)
cv._poll_tools_hover()
pump(0.08)
assert cv.tools_panel.isVisible(), "没有 Enter 事件时坐标轮询也要能展开"
QCursor.setPos(away)
cv._poll_tools_hover()
pump(0.5)
assert not cv.tools_panel.isVisible(), "没有 Leave 事件时也要能收纳"
for hw in (cv.tools_head, cv.tools_panel):
    hw.installEventFilter(cv)
print("3. Enter/Leave 被吞掉时，坐标轮询兜底仍能展开/收纳 OK")

# 3) 手动固定后鼠标离开，自动解除固定，不会卡在展开态
cv.btn_tools.setChecked(True)
pump(0.05)
assert cv.tools_panel.isVisible(), "点按钮应能临时固定展开"
cv._set_tools_hover(True)
cv._set_tools_hover(False)
pump(0.5)
assert cv._tools_pinned is False, "鼠标离开应自动解除固定"
assert not cv.tools_panel.isVisible()
assert "周期" in cv.btn_tools.text()
print("4. 手动固定随鼠标离开放开，不会卡住 OK")

# 卸载事件过滤器 / 停掉轮询：offscreen 下进程退出时 Qt 仍会派发一轮
# Hide/Leave 事件，若过滤器还挂在半销毁的控件上会触发访问违例。
for hw in (cv.tools_head, cv.tools_panel):
    hw.removeEventFilter(cv)
cv._tools_hover_timer.stop()
cv._tools_leave_timer.stop()
try:
    w.live.shutdown()
except Exception:
    pass
w.scheduler.stop()
w.mascot._reappear_timer.stop()
w.close()
pump(0.1)

# ================= 4~6. 看板娘重现说话 / 气泡生命周期 =================
mcfg = Config()
mcfg.set("mascot_enabled", True)
mcfg.set("mascot_speech", True)
mcfg.set("mascot_image", "")
m = MascotWindow(mcfg)
m.apply_config()
m._scene_ok = True
m._opacity = 100
m._enabled = True
m._hidden_by_overlap = False
m._sync_visible()
m._apply_opacity()
pump(0.15)
assert m.isVisible()

# 隐藏（被 K 线压住）→ 重现 → 自动开口
m.set_overlap(0.35)
pump(0.3)
assert not m.isVisible(), "重叠应完全消失"
assert not m._bubble.isVisible(), "隐藏时气泡应收起"
m.set_overlap(0.0)
pump(0.55)
assert m.isVisible(), "离开重叠区应重现"
assert m._bubble.isVisible(), "重现后应该重新说话"
assert m._bubble._text in SPEECH["return"], \
    f"重现应说回来台词，实际：{m._bubble._text}"
assert any(ord(ch) > 0x3040 for ch in m._bubble._text), \
    "重现台词应带日文假名"
print("5. 隐藏后重现会重新开口（含日语）：%s OK" % m._bubble._text)

# 让位期间攒下的台词优先补说
m.set_overlap(0.35)
pump(0.3)
assert m.say("排队台词：ただいま〜") is True, "让位期间台词应被接收"
m.set_overlap(0.0)
pump(0.55)
assert m._bubble.isVisible()
assert m._bubble._text == "排队台词：ただいま〜", \
    f"应优先补说排队台词，实际：{m._bubble._text}"
assert m._pending_line == "", "补说后应清空队列"
print("6. 让位期间的台词重现时补说 OK")

# 气泡到点自动淡出
m._bubble.dismiss()
m._bubble.say("短句测试", m.frameGeometry(), 700)
pump(0.1)
assert m._bubble.isVisible()
pump(1.2)
assert not m._bubble.isVisible(), "气泡到点应自动消失"
print("7. 气泡到点自动消失 OK")

# 旧句子的延迟关闭不能误伤新气泡
m._bubble.say("A 旧台词", m.frameGeometry(), 700)
pump(0.75)
m._bubble.say("B 新台词", m.frameGeometry(), 4200)
pump(0.35)
assert m._bubble.isVisible(), "旧句子的延迟 hide 不该关掉新气泡"
assert m._bubble._text == "B 新台词"
print("8. 旧气泡延迟关闭不会误伤新气泡 OK")

m._reappear_timer.stop()
m._bubble.dismiss()
m._bubble._timer.stop()
if m._fade is not None:
    m._fade.stop()
    m._fade = None
m.hide()
m.close()
from qt_exit import finish           # 跳过 offscreen 的 Qt 卸载竞态
print("\nv21 全部回归测试通过 ✅")
finish()
