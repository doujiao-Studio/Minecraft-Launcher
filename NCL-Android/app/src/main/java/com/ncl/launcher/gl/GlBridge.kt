package com.ncl.launcher.gl

import android.view.Surface

/**
 * 把 Android 的 Surface 交给 native 层，渲染器（gl4es / MobileGlues / Vulkan wrapper）
 * 才能把 OpenGL 画面画到我们的窗口上。这是 PojavLauncher 同款的桥接思路。
 */
object GlBridge {

    init {
        System.loadLibrary("nclgl")
    }

    /** 绑定游戏窗口；必须在启动 JVM 之前调用 */
    external fun setSurface(surface: Surface)

    external fun clearSurface()

    /** 载入外部渲染器 .so（设置页可导入），成功返回 true */
    external fun setRenderer(path: String): Boolean

    /** 通知 native 窗口尺寸变化 */
    external fun setWindowSize(width: Int, height: Int)
}
