#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Free Chart APK 静态可安装性预检。

用法:  python android/check_installable.py

覆盖 Android PackageManager 在安装阶段会检查的全部静态条件：
清单、SDK 区间、启动 Activity、导出标志、资源引用、签名方案、
4 字节对齐、DEX 入口类、assets 完整性、前端脚本语法。

【重要边界】这是静态预检，不是实机安装测试。
真机 ROM 的安装策略（未知来源、纯净模式、签名证书信任、
WebView 运行时行为）无法在本机模拟，仍需 adb install 验证。
"""
import os
import re
import sys
import glob
import shutil
import struct
import zipfile
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
APK = os.path.join(ROOT, "dist", "Free Chart.apk")
WWW = os.path.join(ROOT, "assets", "www")


def find_build_tools():
    roots = [
        os.environ.get("ANDROID_SDK_ROOT"),
        os.environ.get("ANDROID_HOME"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk"),
    ]
    for r in roots:
        if not r:
            continue
        hits = sorted(glob.glob(os.path.join(r, "build-tools", "*")))
        for h in reversed(hits):
            if os.path.exists(os.path.join(h, "aapt.exe")) or os.path.exists(os.path.join(h, "aapt")):
                return h
    return ""


BT = find_build_tools()


def exe(name):
    p = os.path.join(BT, name)
    return p if os.path.exists(p) else (p + ".exe" if os.path.exists(p + ".exe") else "")


def run(args):
    try:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=90).stdout.decode("utf-8", "replace")
    except Exception as e:
        return "ERROR: %s" % e


RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("%-4s %-38s %s" % ("PASS" if ok else "FAIL", name, detail))
    return ok


def main():
    print("APK: %s" % APK)
    print("build-tools: %s\n" % (BT or "未找到"))

    # 1. 基本文件
    size = os.path.getsize(APK) if os.path.isfile(APK) else 0
    check("1. APK 文件存在", size > 0, "%d 字节" % size)
    if not size:
        return finish()
    try:
        z = zipfile.ZipFile(APK)
        names = z.namelist()
        bad = z.testzip()
    except Exception as e:
        check("2. ZIP 结构", False, str(e))
        return finish()
    check("2. ZIP 结构完整", bad is None, "bad=%s, %d entries" % (bad, len(names)))

    # 3. 必需条目
    # 签名块文件名由 keystore 的 alias 决定（历史 keystore 可能沿用旧 alias），
    # 因此只校验 META-INF 下存在 .SF/.RSA，不依赖具体 alias 名。
    sf = [n for n in names if n.startswith("META-INF/") and n.endswith(".SF")]
    rsa = [n for n in names if n.startswith("META-INF/") and
           (n.endswith(".RSA") or n.endswith(".DSA") or n.endswith(".EC"))]
    need = ["AndroidManifest.xml", "classes.dex", "resources.arsc",
            "META-INF/MANIFEST.MF"]
    miss = [n for n in need if n not in names]
    check("3. 安装必需条目", not miss and bool(sf) and bool(rsa),
          "缺失: %s, 签名块: %s" % (miss or "无", (sf + rsa) or "无"))

    # 4. badging
    if not BT:
        check("4-9. SDK 工具", False, "未找到 Android build-tools")
    else:
        badging = run([exe("aapt"), "dump", "badging", APK])
        pkg = re.search(r"package: name='([^']+)'", badging)
        sdk = re.search(r"sdkVersion:'(\d+)'", badging)
        tgt = re.search(r"targetSdkVersion:'(\d+)'", badging)
        act = re.search(r"launchable-activity: name='([^']+)'", badging)
        label = re.search(r"application-label:'([^']+)'", badging)
        icon = re.search(r"application:.*?icon='([^']*)'", badging)
        check("4. 包名 / 版本", bool(pkg) and pkg.group(1) == "com.freechart.app",
              pkg.group(1) if pkg else "解析失败")
        check("5. minSdk / targetSdk",
              bool(sdk and tgt and sdk.group(1) == "29" and tgt.group(1) == "34"),
              "min=%s target=%s" % (sdk.group(1) if sdk else "?", tgt.group(1) if tgt else "?"))
        check("6. 可启动 Activity", bool(act) and act.group(1) == "com.freechart.app.MainActivity",
              act.group(1) if act else "无 LAUNCHER")
        check("7. 应用标签与图标", bool(label) and bool(icon) and icon.group(1) != "",
              "label=%s icon=%s" % (label.group(1) if label else "?",
                                    (icon.group(1) if icon else "?") or "空"))
        perms = re.findall(r"uses-permission: name='([^']+)'", badging)
        check("8. 权限声明", "android.permission.INTERNET" in perms, ", ".join(perms))

        # 9. 二进制清单关键属性
        xml = run([exe("aapt2"), "dump", "xmltree", "--file", "AndroidManifest.xml", APK])
        ok_xml = all(s in xml for s in [
            "minSdkVersion(0x0101020c)=29", "targetSdkVersion(0x01010270)=34",
            "exported(0x01010010)=true", "android.intent.action.MAIN",
            "android.intent.category.LAUNCHER", "screenOrientation(0x0101001e)=1"])
        check("9. 清单属性(导出/竖屏/LAUNCHER)", ok_xml, "exported=true, portrait, MAIN+LAUNCHER")

        # 10. 资源引用可解析
        res = run([exe("aapt"), "dump", "resources", APK])
        ok_res = ("style/AppTheme" in res and "mipmap/ic_launcher" in res
                  and "string/app_name" in res)
        check("10. 主题/图标/名称资源可解析", ok_res, "AppTheme / ic_launcher / app_name")

        # 11. 签名：Android 10-14 走 v3
        signer = ["java", "-jar", os.path.join(BT, "lib", "apksigner.jar")]
        v = run(signer + ["verify", "--verbose", "--min-sdk-version", "29",
                          "--max-sdk-version", "34", APK])
        check("11. 签名验证 (Android 10-14)",
              "Verifies" in v and "v3 scheme (APK Signature Scheme v3): true" in v,
              re.search(r"Number of signers: \d+", v).group(0) if "Number of signers" in v else v[:80])
        # 12. 旧系统 v1 回退
        v1 = run(signer + ["verify", "--verbose", "--min-sdk-version", "21",
                           "--max-sdk-version", "23", APK])
        check("12. v1 签名回退", "Verifies" in v1 and
              "v1 scheme (JAR signing): true" in v1, "旧系统可回退 JAR 签名")

        # 13. zipalign
        al = run([exe("zipalign"), "-c", "-v", "4", APK])
        check("13. 4 字节对齐", "Verification succesful" in al or "Verification successful" in al,
              "zipalign -c -v 4")

    # 14. APK Signing Block 的 v2 / v3 块
    b = open(APK, "rb").read()
    has_v2 = b"\x1a\x87\x09\x71" in b
    has_v3 = b"\xc0\x68\x53\xf0" in b
    check("14. v2 + v3 签名块", has_v2 and has_v3,
          "v2=%s v3=%s" % (has_v2, has_v3))

    # 15. DEX 入口类与桥注解
    dex = z.read("classes.dex")
    need_dex = [b"Lcom/freechart/app/MainActivity;",
                b"Lcom/freechart/app/MainActivity$Bridge;",
                b"Landroid/webkit/JavascriptInterface;",
                b"file:///android_asset/www/index.html"]
    miss_d = [s.decode() for s in need_dex if s not in dex]
    check("15. DEX 入口类 / JS 桥 / 资源 URL", not miss_d, "缺失: %s" % (miss_d or "无"))

    # 16. assets 完整性 + HTML 引用闭环
    assets = [n for n in names if n.startswith("assets/www/")]
    html = z.read("assets/www/index.html").decode("utf-8", "replace")
    refs = re.findall(r'<script[^>]+src="([^"]+)"', html) + \
           re.findall(r'<link[^>]+href="([^"]+)"', html)
    miss_a = [r for r in refs if "assets/www/" + r not in names]
    check("16. assets 与 HTML 引用闭环", len(assets) >= 6 and not miss_a,
          "%d 个资源, 缺失引用: %s" % (len(assets), miss_a or "无"))

    # 17. 前端语法
    node = shutil.which("node")
    if node:
        syn = run([node, "--check", os.path.join(WWW, "app.js")])
        check("17. app.js 语法", syn.strip() == "", syn.strip()[:100] or "OK")
    else:
        check("17. app.js 语法", False, "本机无 node，跳过（非致命）")

    finish()


def finish():
    total = len(RESULTS)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 66)
    print("静态预检: %d 项，通过 %d，失败 %d" % (total, total - len(failed), len(failed)))
    if failed:
        print("失败项: " + ", ".join(failed))
    print("结论: " + ("所有静态安装条件满足，可由 PackageManager 解析。" if not failed
                     else "存在不满足项，安装可能被拒绝。"))
    print("边界: 本检查不覆盖真机 ROM 安装策略、证书信任、WebView 运行时；")
    print("      仍需在有 Android 10+ 设备/模拟器时执行 adb install -r 验证。")
    print("=" * 66)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
