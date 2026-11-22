# -*- coding: utf-8 -*-
"""Free Chart Android APK 构建脚本（无需 Gradle / NDK / Python 运行时）。

只用本机 Android SDK build-tools 34.0.0 与 JDK：
  aapt2 compile/link -> javac -> d8 -> zipalign -> apksigner。
产物：android/dist/Free Chart.apk（可直接安装，minSdk 29 / targetSdk 34）。

运行：python android/build_apk.py
"""
import glob
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SDK = (os.environ.get("ANDROID_HOME")
       or os.environ.get("ANDROID_SDK_ROOT")
       or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk"))
BT = os.path.join(SDK, "build-tools", "34.0.0")
ANDROID_JAR = os.path.join(SDK, "platforms", "android-34", "android.jar")
AAPT2 = os.path.join(BT, "aapt2.exe")
ZIPALIGN = os.path.join(BT, "zipalign.exe")
# build-tools 34.0.0 自带的 d8 (R8 8.2 dev) 在 Windows + JDK21 下处理
# 匿名内部类会抛 NPE（实测 MainActivity$1.class），36.1.0 已修复。
# 资源打包/对齐/签名仍用 34.0.0，只用新版做 class -> dex 转换。
D8_JAR = os.path.join(SDK, "build-tools", "36.1.0", "lib", "d8.jar")
APKSIGNER_JAR = os.path.join(BT, "lib", "apksigner.jar")

BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
OUT = os.path.join(DIST, "Free Chart.apk")


def run(cmd, label):
    print("[%s] %s" % (label, " ".join(str(x) for x in cmd[:6]) + " ..."))
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print((r.stdout or "")[-4000:])
        print((r.stderr or "")[-4000:])
        raise SystemExit("构建失败于 %s (rc=%s)" % (label, r.returncode))
    if r.stdout.strip():
        print("   " + r.stdout.strip()[-600:].replace("\n", "\n   "))
    return r


def check_tools():
    for p in (ANDROID_JAR, AAPT2, ZIPALIGN, D8_JAR, APKSIGNER_JAR):
        if not os.path.exists(p):
            raise SystemExit("缺少工具/文件: %s（请检查 ANDROID_HOME）" % p)
    print("SDK: %s" % SDK)


def main():
    check_tools()
    shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)

    res_zip = os.path.join(BUILD, "res.zip")
    base = os.path.join(BUILD, "base.apk")
    unsigned = os.path.join(BUILD, "unsigned.apk")
    aligned = os.path.join(BUILD, "aligned.apk")
    classes = os.path.join(BUILD, "classes")
    dexdir = os.path.join(BUILD, "dex")
    # 密钥必须放在 build/ 之外：build/ 每次构建都会清空，若 keystore 跟着重建，
    # 新旧 APK 签名不同，覆盖安装会失败 (INSTALL_FAILED_UPDATE_INCONSISTENT)。
    ks = os.path.join(ROOT, "debug.keystore")
    os.makedirs(classes, exist_ok=True)
    os.makedirs(dexdir, exist_ok=True)

    # 1. 编译资源
    run([AAPT2, "compile", "--dir", os.path.join(ROOT, "res"),
         "-o", res_zip], "1/8 aapt2 compile")

    # 2. 链接 APK 骨架（含 assets/ 与 AndroidManifest.xml）
    run([AAPT2, "link", "-o", base, "-I", ANDROID_JAR,
         "--manifest", os.path.join(ROOT, "AndroidManifest.xml"),
         "-R", res_zip, "-A", os.path.join(ROOT, "assets"),
         "--auto-add-overlay", "--min-sdk-version", "29",
         "--target-sdk-version", "34"], "2/8 aapt2 link")

    # 3. 编译 Java（Java 8 字节码，d8 可直接吃）
    run(["javac", "--release", "8", "-encoding", "UTF-8",
         "-cp", ANDROID_JAR, "-d", classes,
         os.path.join(ROOT, "src", "com", "freechart", "app",
                      "MainActivity.java")], "3/8 javac")

    # 4. class -> classes.dex
    files = sorted(glob.glob(os.path.join(
        classes, "com", "freechart", "app", "*.class")))
    if not files:
        raise SystemExit("javac 没有产出 class 文件")
    run(["java", "-cp", D8_JAR, "com.android.tools.r8.D8",
         "--lib", ANDROID_JAR, "--min-api", "29",
         "--output", dexdir] + files, "4/8 d8")

    # 5. 把 dex 加入 APK（assets 已由 aapt2 打进去）
    shutil.copy(base, unsigned)
    with zipfile.ZipFile(unsigned, "a", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(dexdir, "classes.dex"), "classes.dex")

    # 6. 4 字节对齐（签名前必须做）
    run([ZIPALIGN, "-f", "-p", "4", unsigned, aligned], "6/8 zipalign")

    # 7. 生成签名密钥（仅首次）
    if not os.path.exists(ks):
        run(["keytool", "-genkeypair", "-keystore", ks,
             "-storepass", "android", "-keypass", "android",
             "-alias", "freechart", "-keyalg", "RSA", "-keysize", "2048",
             "-validity", "10000", "-storetype", "JKS",
             "-dname", "CN=Free Chart, OU=Dev, O=WorkBuddy, L=CN, ST=CN, C=CN"],
            "7/8 keytool")

    # 8. 签名 + 校验
    signer = ["java", "-jar", APKSIGNER_JAR]
    # 同时写入 v1 / v2 / v3：Android 10+ 走 v3，旧系统可回退 v1，
    # 避免个别 ROM 安装器只认某一种方案时拒绝安装。
    run(signer + ["sign", "--ks", ks, "--ks-pass", "pass:android",
                  "--key-pass", "pass:android",
                  "--min-sdk-version", "29",
                  "--v1-signing-enabled", "true",
                  "--v2-signing-enabled", "true",
                  "--v3-signing-enabled", "true",
                  "--out", OUT, aligned], "8/8 apksigner sign")
    run(signer + ["verify", "--verbose", "--min-sdk-version", "29",
                  "--max-sdk-version", "34", OUT], "verify Android 10-14")
    run(signer + ["verify", "--verbose", "--min-sdk-version", "21",
                  "--max-sdk-version", "23", OUT], "verify legacy fallback")
    print("\nAPK 生成成功: %s (%d 字节)" % (OUT, os.path.getsize(OUT)))


if __name__ == "__main__":
    main()
