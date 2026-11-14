# -*- coding: utf-8 -*-
"""把 Python 离线资料库导出成 Android WebView 用的 about.js。

单一数据源：桌面端 data/about.py + data/timeline.py 是唯一的资料库，
手机端不再手工维护一份，避免两边介绍 / 日期不一致（v37）。
生成 android/assets/www/about.js：

    window.ABOUT_DB = { about, market_default, timeline, archive,
                        archive_fields, meta }

用法（项目根目录）：python tools/export_profile_db.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import brand                     # noqa: E402
from data import about as about_db         # noqa: E402
from data import timeline as tl            # noqa: E402

OUT = os.path.join(ROOT, "android", "assets", "www", "about.js")


def build() -> dict:
    return {
        "about": about_db.ABOUT,
        "market_default": about_db._MARKET_DEFAULT,
        "timeline": tl.TIMELINE,
        "archive": tl.ARCHIVE,
        "archive_fields": [list(x) for x in tl.ARCHIVE_FIELDS],
        "meta": {
            "verified_at": tl.VERIFIED_AT,
            "source_note": tl.SOURCE_NOTE,
            "no_data": tl.NO_DATA,
            "stats": tl.stats(),
            "app_name": brand.APP_NAME,
            "app_subtitle": brand.APP_SUBTITLE,
            "app_tagline": brand.APP_TAGLINE,
            "app_version": brand.APP_VERSION,
        },
    }


def main():
    data = build()
    text = ("/* 由 tools/export_profile_db.py 自动生成，请勿手工编辑。\n"
            "   来源：data/about.py + data/timeline.py（离线公开资料，核验于 %s） */\n"
            % tl.VERIFIED_AT)
    text += "window.ABOUT_DB = " + json.dumps(
        data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("written:", OUT)
    print("bytes:", os.path.getsize(OUT))
    print("timeline:", data["meta"]["stats"])


if __name__ == "__main__":
    main()
