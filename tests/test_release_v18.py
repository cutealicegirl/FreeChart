# -*- coding: utf-8 -*-
"""v18 回归：默认看板娘立绘 + 互动气泡（行情 / 操作触发）。

覆盖：
1. 内置 assets/mascot.png 是带透明通道的新立绘；
2. 气泡能显示、定位在人物上方、超时自动消失；
3. 台词占位符替换、涨跌阈值、冷却、方向去重；
4. 关掉 mascot_speech 后不再说话；
5. 主窗口操作（加自选）能触发台词；
6. 设置对话框回传 mascot_speech。

全部离线（临时 APPDATA + offscreen）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v18_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtGui import QImage

from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.mascot import SPEECH, MascotWindow, default_mascot_path
from ui.main_window import MainWindow
from ui.settings_dialog import SettingsDialog

app = QApplication([])


def pump(seconds=0.05):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


# ================= 1. 内置立绘带透明背景 =================
path = default_mascot_path()
assert os.path.isfile(path), path
img = QImage(path)
assert not img.isNull(), "内置看板娘图片应能加载"
assert img.hasAlphaChannel(), "应带透明通道（白底已抠掉）"
assert img.width() > 600 and img.height() > 500, \
    f"立绘分辨率偏低: {img.width()}x{img.height()}"
# 四角必须是透明的（说明背景真的抠掉了）
for x, y in ((2, 2), (img.width() - 3, 2),
             (2, img.height() - 3), (img.width() - 3, img.height() - 3)):
    alpha = img.pixelColor(x, y).alpha()
    assert alpha < 24, f"角落 ({x},{y}) 仍不透明: alpha={alpha}"
print(f"1. 内置立绘 {img.width()}x{img.height()} 带透明通道 OK")

# ================= 2. 气泡显示 / 定位 / 自动消失 =================
cfg = Config()
cfg.set("mascot_enabled", True)
cfg.set("mascot_speech", True)
cfg.set("mascot_image", "")
m = MascotWindow(cfg)
m.apply_config()
pump(0.1)
assert m.isVisible(), "启用后看板娘应可见"

m.say("测试一下气泡位置")
pump(0.35)
assert m._bubble.isVisible(), "say 之后气泡应显示"
assert m._bubble.y() <= m.y(), "气泡应在人物上方"
assert m._bubble.width() >= 96
m._bubble.dismiss()
pump(0.4)
assert not m._bubble.isVisible(), "dismiss 后应隐藏"
print("2. 气泡显示 / 定位于头顶上方 / 可关闭 OK")

# ================= 3. 台词占位符替换 =================
lines = set()
for _ in range(14):
    got = m.react("up", sym="ETH", pct="+3.21%")
    if got:
        lines.add(got)
assert lines, "up 情境应能说出台词"
assert all("{" not in t and "}" not in t for t in lines), \
    f"占位符没替换干净: {lines}"
assert any("ETH" in t for t in lines), f"应替换 {{sym}}: {lines}"
print(f"3. 台词占位符替换 OK（{len(lines)} 句样本）")

# ================= 4. 行情阈值 / 冷却 / 方向去重 =================
m.say("先占个位")
pump(0.05)
m._last_say = 0.0            # 清冷却
m._last_market = None
assert m.react_market("BTC", 0.8) == "", "涨幅 < 2% 不该说话"
big = m.react_market("BTC", 8.5, "Bitcoin", cooldown=0)
assert big, "大涨应触发台词"
assert m.react_market("BTC", 9.0, "Bitcoin", cooldown=0) == "", \
    "同品种同方向不应重复播报"
m._last_say = 0.0
assert m.react_market("BTC", -9.0, "Bitcoin", cooldown=0), \
    "方向反转应重新播报"
print("4. 行情阈值 / 冷却 / 同向去重 OK")

# ================= 5. 关掉互动后不说话 =================
cfg.set("mascot_speech", False)
m.apply_config()
pump(0.05)
m._bubble.dismiss()
pump(0.3)
assert m.react("greet") == "", "关闭互动后不应返回台词"
assert not m._bubble.isVisible()
cfg.set("mascot_speech", True)
m.apply_config()
pump(0.05)
print("5. 关闭 mascot_speech 后静默 OK")

# ================= 6. 主窗口操作触发台词 =================
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.resize(460, 880)
w.prepare_show()
pump(0.1)
assert w.mascot is not None, "主窗口应持有看板娘"
spoke = []
w.mascot.react = lambda kind, **kw: spoke.append(kind) or "ok"
w._add_symbol("ADA")
pump(0.05)
assert "add" in spoke, f"加自选应触发台词，实际 {spoke}"
w._remove_symbol("ADA")
pump(0.05)
assert "remove" in spoke, f"移出自选应触发台词，实际 {spoke}"
print("6. 主窗口操作触发台词 OK（add / remove）")

# ================= 7. 设置对话框回传开关 =================
dlg = SettingsDialog(w, w)
pump(0.05)
assert hasattr(dlg, "chk_mascot_speech"), "设置里应有互动气泡开关"
settings = dlg.get_settings()
assert "mascot_speech" in settings and isinstance(settings["mascot_speech"], bool)
dlg.close()
dlg.deleteLater()
pump(0.05)
print("7. 设置对话框回传 mascot_speech OK")

# 台词库每种情境都不为空
for key in ("greet", "click", "up", "down", "big_up", "big_down",
            "chart", "add", "remove", "market", "theme", "settings", "idle"):
    assert SPEECH.get(key), f"台词库缺少 {key}"

w.scheduler.stop()
w.close()
pump(0.05)
print("\nv18 全部回归测试通过 ✅")
