#include <jni.h>
#include <android/native_window.h>
#include <android/native_window_jni.h>
#include <android/log.h>
#include <dlfcn.h>
#include <mutex>
#include <string>
#include <vector>

#define LOG_TAG "nclgl"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

namespace {

std::mutex g_mutex;
ANativeWindow *g_window = nullptr;
void *g_renderer = nullptr;
int g_width = 0;
int g_height = 0;

// 不同渲染器导出的“设置窗口”函数名都不一样，逐个尝试，找不到就安全降级
const char *kWindowSymbols[] = {
        "ncl_set_native_window",
        "setNativeWindow",
        "gl4es_setNativeWindow",
        "MobileGluesSetNativeWindow",
        "setupNativeWindow",
};

void applyWindow() {
    if (!g_renderer) return;
    for (const char *sym: kWindowSymbols) {
        auto fn = reinterpret_cast<void (*)(ANativeWindow *)>(dlsym(g_renderer, sym));
        if (fn) {
            fn(g_window);
            LOGI("renderer window set via %s", sym);
            return;
        }
    }
    LOGI("renderer has no known window symbol; relying on env only");
}

}  // namespace

extern "C" {

/**
 * 供渲染器 / 其他 native 库主动取窗口（声明即可用：extern ANativeWindow* ncl_get_native_window();）
 */
JNIEXPORT ANativeWindow *ncl_get_native_window() {
    std::lock_guard<std::mutex> lock(g_mutex);
    return g_window;
}

JNIEXPORT void JNICALL
Java_com_ncl_launcher_gl_GlBridge_setSurface(JNIEnv *env, jobject thiz, jobject surface) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_window) {
        ANativeWindow_release(g_window);
        g_window = nullptr;
    }
    if (!surface) return;
    g_window = ANativeWindow_fromSurface(env, surface);
    LOGI("surface attached: %p", g_window);
    applyWindow();
}

JNIEXPORT void JNICALL
Java_com_ncl_launcher_gl_GlBridge_clearSurface(JNIEnv *env, jobject thiz) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_window) {
        ANativeWindow_release(g_window);
        g_window = nullptr;
    }
}

JNIEXPORT jboolean JNICALL
Java_com_ncl_launcher_gl_GlBridge_setRenderer(JNIEnv *env, jobject thiz, jstring path) {
    std::lock_guard<std::mutex> lock(g_mutex);
    const char *p = env->GetStringUTFChars(path, nullptr);
    std::string lib(p);
    env->ReleaseStringUTFChars(path, p);
    if (lib.empty()) return JNI_FALSE;
    void *h = dlopen(lib.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!h) {
        LOGE("dlopen failed: %s (%s)", lib.c_str(), dlerror());
        return JNI_FALSE;
    }
    g_renderer = h;
    LOGI("renderer loaded: %s", lib.c_str());
    applyWindow();
    return JNI_TRUE;
}

JNIEXPORT void JNICALL
Java_com_ncl_launcher_gl_GlBridge_setWindowSize(JNIEnv *env, jobject thiz, jint w, jint h) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_width = w;
    g_height = h;
    if (g_window && w > 0 && h > 0) {
        ANativeWindow_setBuffersGeometry(g_window, w, h, AHARDWAREBUFFER_FORMAT_R8G8B8A8_UNORM);
    }
    applyWindow();
}

}  // extern "C"
