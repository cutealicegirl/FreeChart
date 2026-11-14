# -*- coding: utf-8 -*-
"""v26 回归：阶段 1「完善品种详情信息」。

验收点（全部离线，不依赖网络、不编造数据）：
1. profile v2 固定 schema：字段齐全、拿不到的数值为 None、不再出现假时间；
2. 离线资料库结构化分区：背景 / 业务 / 核心特点 / 用途有据可依，
   发展前景 / 代币分配 / 解锁 / 协议收入 / 营收 / 利润一律留空；
3. 详情抽屉分层：新增供应成交卡、进阶数据卡、数据来源卡；
4. 缺失字段统一显示「— 暂无公开数据」，不得填 0 或估算值；
5. 注入真实字段后能正确渲染来源、采集时间与各项数值；
6. 资料卡也有来源与更新时间标注。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v26_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication, QLabel

from data import fundamentals
from data.api_base import Ticker
from ui.detail_dialog import MISSING, SymbolDetailDialog
from ui.info_panel import SymbolInfoPanel

app = QApplication([])


def pump(sec=0.05):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


# ============ 1. profile v2：字段齐全、无假数据 ============
p = fundamentals.profile("BTC", 67891.0)
assert p.get("schema") == 2
for k in fundamentals.PROFILE_FIELDS:
    assert k in p, f"v2 缺少字段 {k}"
for k in ("cap", "float_cap", "pe", "pb", "supply_total", "supply_max",
          "volume_24h", "turnover_rate", "liquidity", "revenue", "profit",
          "token_allocation", "unlock_schedule", "protocol_revenue"):
    assert p.get(k) is None, f"离线状态不得编造 {k}：{p.get(k)}"
assert "刚刚" not in (p.get("updated_text") or ""), \
    "「刚刚」是没有依据的假时间，必须去掉"
blank = fundamentals.blank_profile("ETH")
assert blank["schema"] == 2 and blank["cap"] is None
assert fundamentals._fmt_time(0) == "—"
assert fundamentals._parse_quote_ts("20261112161452") > 0
assert fundamentals._parse_quote_ts("not-a-time") == 0.0
print("1. profile v2 schema / 不编造数据 / 真实时间解析 OK")

# ============ 2. 离线资料库结构化分区 ============
a = fundamentals.about("BTC", "Bitcoin")
for k in ("background", "business", "highlights", "purpose"):
    assert a.get(k), f"应有已核实内容的分区 {k}"
assert "中本聪" in a["background"]
for k in ("outlook", "token_allocation", "unlock_schedule",
          "protocol_revenue", "revenue", "profit", "liquidity"):
    assert a.get(k) is None, f"无依据的分区必须留空：{k}"
assert a["covered"] is True
fb = fundamentals.about("US:ZZZZ", "未知公司")
assert fb["covered"] is False
assert fb.get("summary") and fb.get("category")
assert fb["outlook"] is None
assert "1999 成立 / 2001 上市 创立 / 上市" not in \
    (fundamentals.about("SH:600519").get("background") or ""), \
    "「成立/上市」文案不能叠床架屋"
print("2. 背景/业务/核心特点/用途分区 + 无依据项留空 OK")

# ============ 3. 详情抽屉分层与缺失标注 ============
btc = Ticker("BTC", "Bitcoin", 67891.23, 2.35,
             70000.0, 66000.0, 1.7e9)
dlg = SymbolDetailDialog("BTC", "Bitcoin", btc)
assert len(dlg._supply_cells) == 6 and len(dlg._extra_cells) == 6
labels = [x.text() for x in dlg.findChildren(QLabel)]
assert "项目用途 · 代币经济学" in labels, "加密详情应有代币经济学分区"
assert "供应 · 成交 · 流动性" in labels
assert "数据来源与更新时间" in labels
assert dlg._is_crypto is True
assert "刚刚" not in dlg._fund_cells["updated"].val.text()
assert MISSING in dlg._fund_cells["updated"].val.text()
assert "数值来源" in dlg.lbl_source.text()
assert "中本聪" in dlg.lbl_about.text()
assert "【发展前景】— 暂无公开资料" in dlg.lbl_about.text()
for key in ("sc", "st", "sm", "vol", "turnover", "liquidity"):
    assert MISSING in dlg._supply_cells[key].val.text(), \
        f"缺数据时 {key} 应明确标注"
for key in ("allocation", "unlock", "protocol_rev", "outlook"):
    assert MISSING in dlg._extra_cells[key].val.text(), \
        f"缺数据时 {key} 应明确标注"
print("3. 详情抽屉 6 张分区卡 / 缺失字段统一标注 OK")

# ============ 4. 注入真实字段后正确渲染 ============
prof = fundamentals.blank_profile("BTC")
prof.update({
    "cap": 1.43e12, "float_cap": 1.43e12,
    "shares": 19970852.0, "float_shares": 19970852.0,
    "supply_circulating": 19970852.0,
    "supply_total": 19970852.0, "supply_max": 21000000.0,
    "volume_24h": 1.06e11, "volume_unit": "USD（24h 成交额）",
    "source": "CoinLore", "source_url": "https://api.coinlore.net/api/tickers/",
    "source_note": "CoinLore 全球市值榜（前 300）",
    "updated_text": "2026-11-13 00:09:54", "updated_kind": "本地采集时间",
})
dlg._profile = prof
dlg._render_profile()
assert "1997" in dlg._supply_cells["sc"].val.text(), \
    dlg._supply_cells["sc"].val.text()
assert "2100" in dlg._supply_cells["sm"].val.text()
assert "亿" in dlg._supply_cells["vol"].val.text()
assert dlg._fund_cells["updated"].val.text() == "2026-11-13 00:09:54"
assert "CoinLore" in dlg.lbl_source.text()
assert "2026-11-13 00:09:54" in dlg.lbl_source.text()
assert "本地采集时间" in dlg.lbl_source.text()
print("4. 真实供应量 / 成交额 / 来源 / 采集时间渲染 OK")

# ============ 5. 股票详情：财务分区与 PB ============
stock = Ticker("SH:600519", "贵州茅台", 1410.27, 0.57,
               1411.0, 1388.11, 4.5e9)
d2 = SymbolDetailDialog("SH:600519", "贵州茅台", stock)
assert d2._is_crypto is False
assert "revenue" in d2._extra_cells and "profit" in d2._extra_cells
sp = fundamentals.blank_profile("SH:600519")
sp.update({"pe": 21.46, "pb": 6.5, "volume_24h": 32373.0,
           "volume_unit": "手（成交量）", "turnover_rate": 0.26,
           "source": "腾讯行情", "source_note": "腾讯行情单只快照",
           "updated_text": "2026-11-12 16:14:52",
           "updated_kind": "行情源时间"})
d2._profile = sp
d2._render_profile()
assert "21.46" in d2._fund_cells["pe"].val.text()
assert "6.50" in d2._extra_cells["pb"].val.text()
assert "手" in d2._supply_cells["vol"].val.text()
assert "0.26%" in d2._supply_cells["turnover"].val.text()
assert "行情源时间" in d2.lbl_source.text()
assert MISSING in d2._extra_cells["revenue"].val.text(), \
    "未接财报源时营收必须留白"
print("5. 股票 PE/PB/成交量/换手率/行情源时间 + 营收留白 OK")

# ============ 6. 资料卡也有来源与时间 ============
panel = SymbolInfoPanel()
assert hasattr(panel, "lbl_source")
panel.set_symbol("BTC", "Bitcoin")
panel.set_profile(prof)
assert "CoinLore" in panel.lbl_source.text()
assert "2026-11-13 00:09:54" in panel.lbl_source.text()
assert "中本聪" in panel.lbl_about.text()
pump(0.15)      # 让后台离线兜底线程回来
assert "CoinLore" in panel.lbl_source.text(), \
    "离线兜底不得覆盖已有的真实来源"
print("6. 资料卡来源 / 更新时间 / 创始人介绍 + 离线兜底不覆盖 OK")

# ============ 收尾 ============
pump(0.05)
from qt_exit import finish
print("\nv26 全部回归测试通过 ✅")
finish()
