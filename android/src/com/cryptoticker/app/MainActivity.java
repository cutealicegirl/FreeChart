package com.cryptoticker.app;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.Charset;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Free Chart Android 壳（纯 Java，无 Gradle / NDK / Python 运行时）。
 *
 * 选择理由：PySide6/Qt 在本机没有可用的 Android Qt 运行时与 CPython wheel，
 * 用 Qt for Android 会牺牲稳定性。这里改为「原生 WebView + 本地 HTML/JS UI」，
 * 网络与持久化由 Java 桥提供：
 *   - 真实行情请求在后台线程池执行（不阻塞 UI、绕过浏览器 CORS、可解 GBK）；
 *   - SharedPreferences 使用与桌面端一致的键名，便于配置迁移。
 * UI 层是单列、竖屏、触摸优先，完全不依赖桌面运行环境。
 */
public class MainActivity extends Activity {

    private WebView web;
    private SharedPreferences prefs;
    private final ExecutorService pool = Executors.newFixedThreadPool(3);

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        prefs = getSharedPreferences("cryptoticker", MODE_PRIVATE);

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        // 本地 file:// 页面要加载同目录的 js/css；不同系统版本默认值不同，显式打开
        s.setAllowFileAccessFromFileURLs(true);
        s.setAllowUniversalAccessFromFileURLs(true);
        s.setJavaScriptCanOpenWindowsAutomatically(false);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        s.setTextZoom(100);
        web.addJavascriptInterface(new Bridge(), "Native");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                return false;
            }
        });
        setContentView(web);
        web.loadUrl("file:///android_asset/www/index.html");
    }

    @Override
    public void onBackPressed() {
        // 统一返回：先由页面内部逐级回退，页面在最顶层时才交给系统
        web.evaluateJavascript("window.__androidBack && window.__androidBack()", null);
    }

    @Override
    protected void onDestroy() {
        pool.shutdownNow();
        super.onDestroy();
    }

    private static String quote(String value) {
        return JSONObject.quote(value == null ? "" : value);
    }

    private final class Bridge {

        @JavascriptInterface
        public String get(String key) {
            return prefs.getString(key, "");
        }

        @JavascriptInterface
        public void set(String key, String value) {
            prefs.edit().putString(key, value).apply();
        }

        /** 页面已回到最顶层时，由 JS 触发系统级退出。 */
        @JavascriptInterface
        public void finish() {
            runOnUiThread(new Runnable() {
                @Override public void run() { MainActivity.this.finish(); }
            });
        }

        @JavascriptInterface
        public String version() {
            return "1.3.0";
        }

        @JavascriptInterface
        public void toast(final String msg) {
            runOnUiThread(new Runnable() {
                @Override public void run() {
                    Toast.makeText(MainActivity.this, msg, Toast.LENGTH_SHORT).show();
                }
            });
        }

        /** 导出配置：把 JSON 放进系统剪贴板。 */
        @JavascriptInterface
        public void copy(final String text) {
            runOnUiThread(new Runnable() {
                @Override public void run() {
                    try {
                        ClipboardManager cm = (ClipboardManager)
                                getSystemService(Context.CLIPBOARD_SERVICE);
                        cm.setPrimaryClip(ClipData.newPlainText("Free Chart", text));
                    } catch (Exception ignored) { }
                }
            });
        }

        /** 导入配置：读取系统剪贴板文本（读不到返回空串）。 */
        @JavascriptInterface
        public String paste() {
            try {
                ClipboardManager cm = (ClipboardManager)
                        getSystemService(Context.CLIPBOARD_SERVICE);
                ClipData clip = cm.getPrimaryClip();
                if (clip != null && clip.getItemCount() > 0) {
                    CharSequence s = clip.getItemAt(0).getText();
                    return s == null ? "" : s.toString();
                }
            } catch (Exception ignored) { }
            return "";
        }

        /** 异步 HTTP GET：cb 是 JS 侧回调 id，返回 (body, error)。 */
        @JavascriptInterface
        public void http(final String url, final String charset, final String cb) {
            pool.execute(new Runnable() {
                @Override public void run() {
                    String body = "", err = "";
                    try {
                        body = fetch(url, charset);
                    } catch (Exception e) {
                        err = String.valueOf(e.getMessage());
                    }
                    final String b = body, e2 = err;
                    runOnUiThread(new Runnable() {
                        @Override public void run() {
                            web.evaluateJavascript(
                                    "window.__nativeCb&&window.__nativeCb("
                                            + quote(cb) + "," + quote(b) + ","
                                            + quote(e2) + ")", null);
                        }
                    });
                }
            });
        }
    }

    private static String fetch(String urlStr, String charsetName) throws Exception {
        HttpURLConnection conn = null;
        try {
            URL u = new URL(urlStr);
            conn = (HttpURLConnection) u.openConnection();
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(12000);
            conn.setRequestMethod("GET");
            conn.setRequestProperty("User-Agent",
                    "Mozilla/5.0 (Linux; Android 10) FreeChart/1.2");
            conn.setRequestProperty("Accept", "*/*");
            conn.setInstanceFollowRedirects(true);
            int code = conn.getResponseCode();
            InputStream in = (code >= 200 && code < 400)
                    ? conn.getInputStream() : conn.getErrorStream();
            if (in == null) {
                throw new Exception("HTTP " + code);
            }
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
            in.close();
            Charset cs;
            try {
                cs = Charset.forName(charsetName == null ? "UTF-8" : charsetName);
            } catch (Exception e) {
                cs = Charset.forName("UTF-8");
            }
            return new String(out.toByteArray(), cs);
        } finally {
            if (conn != null) conn.disconnect();
        }
    }
}
