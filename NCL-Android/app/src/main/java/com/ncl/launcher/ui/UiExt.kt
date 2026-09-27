package com.ncl.launcher.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.fragment.app.Fragment
import java.io.File

/** 小工具：Toast / 目录打开 / 主线程切换糖 */
fun Fragment.toast(msg: String) {
    view?.post { Toast.makeText(requireContext(), msg, Toast.LENGTH_SHORT).show() }
}

fun Context.toast(msg: String) {
    Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
}

/**
 * “打开目录”：Android 没有可靠的目录跳转，优先唤起文件管理器，
 * 失败就把路径复制到剪贴板并提示用户。
 */
fun Context.openDir(path: String) {
    val file = File(path)
    file.mkdirs()
    val tried = runCatching {
        val uri = Uri.parse("content://com.android.externalstorage.documents/document/primary:" +
            file.absolutePath.removePrefix("/storage/emulated/0/"))
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "vnd.android.document/directory")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(intent)
        true
    }.getOrDefault(false)
    if (!tried) {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
        cm?.setPrimaryClip(ClipData.newPlainText("path", path))
        toast("已复制路径：$path")
    }
}
