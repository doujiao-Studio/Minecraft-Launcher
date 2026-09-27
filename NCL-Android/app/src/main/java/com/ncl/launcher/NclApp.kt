package com.ncl.launcher

import android.app.Application
import com.ncl.launcher.data.Paths

class NclApp : Application() {

    override fun onCreate() {
        super.onCreate()
        // 与桌面版一致：首次启动自动铺开全部目录骨架（静默，不弹任何提示）
        Paths.init(this)
        Paths.ensureLayout()
    }
}
