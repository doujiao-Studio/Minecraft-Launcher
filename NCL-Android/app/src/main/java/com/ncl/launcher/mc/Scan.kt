package com.ncl.launcher.mc

import android.graphics.BitmapFactory
import android.text.format.DateUtils
import com.ncl.launcher.data.Paths
import java.io.File
import java.text.SimpleDateFormat
import java.util.Locale

/**
 * 版本详情里四大列表的扫描器，字段与桌面版 version_detail.py 对齐。
 * 全部是纯函数式扫描，UI 层在 IO 线程调用后回主线程刷新。
 */
object Scan {

    enum class Kind { MOD, RESOURCE_PACK, SAVE, DATA_PACK }

    data class Entry(
        val kind: Kind,
        val title: String,
        val sub: String,
        val tail: String = "",
        val path: String = "",
        val iconPath: String = "",
        val enabled: Boolean = true,
        val sortKey: Long = 0L
    )

    private val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault())

    // ---------------------------------------------------------------- 模组
    fun mods(versionId: String): List<Entry> {
        val dir = Paths.modsDir(versionId)
        val out = ArrayList<Entry>()
        dir.listFiles()?.forEach { f ->
            if (!f.isFile) return@forEach
            val enabled = f.name.endsWith(".jar")
            if (!enabled && !f.name.endsWith(".jar.disabled")) return@forEach
            out.add(
                Entry(
                    kind = Kind.MOD,
                    title = f.name.removeSuffix(".disabled").removeSuffix(".jar"),
                    sub = if (enabled) "已启用" else "已禁用",
                    tail = humanSize(f.length()),
                    path = f.absolutePath,
                    enabled = enabled
                )
            )
        }
        return out.sortedWith(compareBy({ !it.enabled }, { it.title.lowercase() }))
    }

    // ------------------------------------------------------------ 资源包
    fun resourcePacks(versionId: String): List<Entry> {
        val out = ArrayList<Entry>()
        val dirs = listOf(Paths.resourcePacksDir(versionId), Paths.globalResourcePacksDir())
        for (dir in dirs) {
            dir.listFiles()?.forEach { f ->
                when {
                    f.isFile && f.name.endsWith(".zip", true) ->
                        out.add(entry(Kind.RESOURCE_PACK, f, "资源包（zip）"))
                    f.isDirectory && File(f, "pack.mcmeta").exists() ->
                        out.add(entry(Kind.RESOURCE_PACK, f, "资源包（文件夹）"))
                }
            }
        }
        return out.sortedBy { it.title.lowercase() }
    }

    // -------------------------------------------------------------- 存档
    fun saves(versionId: String): List<Entry> {
        val dir = Paths.savesDir(versionId)
        val out = ArrayList<Entry>()
        dir.listFiles()?.filter { it.isDirectory }?.forEach { d ->
            val dat = File(d, "level.dat")
            val info = if (dat.exists()) Nbt.readLevel(dat) else null
            val icon = File(d, "icon.png")
            val size = dirSize(d)
            val last = info?.lastPlayed ?: d.lastModified()
            val sub = buildString {
                if (info != null) {
                    append(info.gameType)
                    if (info.version.isNotBlank()) append(" · ${info.version}")
                } else {
                    append("存档")
                }
                append(" · ").append(humanSize(size))
                if (last > 0) append(" · ").append(fmtTime(last))
            }
            out.add(
                Entry(
                    kind = Kind.SAVE,
                    title = info?.name?.takeIf { it.isNotBlank() } ?: d.name,
                    sub = sub,
                    tail = "",
                    path = d.absolutePath,
                    iconPath = icon.takeIf { it.exists() }?.absolutePath ?: "",
                    sortKey = last
                )
            )
        }
        return out.sortedByDescending { it.sortKey }
    }

    // ------------------------------------------------------------ 数据包
    fun dataPacks(versionId: String): List<Entry> {
        val out = ArrayList<Entry>()
        Paths.globalDataPacksDir().listFiles()?.forEach { f ->
            if (isDataPack(f)) out.add(entry(Kind.DATA_PACK, f, "全局数据包"))
        }
        Paths.savesDir(versionId).listFiles()?.filter { it.isDirectory }?.forEach { save ->
            File(save, "datapacks").listFiles()?.forEach { f ->
                if (isDataPack(f)) out.add(entry(Kind.DATA_PACK, f, "存档「${save.name}」"))
            }
        }
        return out.sortedBy { it.title.lowercase() }
    }

    private fun isDataPack(f: File): Boolean =
        (f.isFile && f.name.endsWith(".zip", true)) ||
            (f.isDirectory && File(f, "pack.mcmeta").exists())

    private fun entry(kind: Kind, f: File, tag: String): Entry = Entry(
        kind = kind,
        title = if (f.isDirectory) f.name else f.nameWithoutExtension,
        sub = tag,
        tail = humanSize(if (f.isFile) f.length() else dirSize(f)),
        path = f.absolutePath
    )

    // ------------------------------------------------------------ 工具
    /** 目录大小，超过 cap 个文件就停（防止超大存档把界面卡死） */
    fun dirSize(dir: File, cap: Int = 30000): Long {
        if (!dir.exists()) return 0
        if (dir.isFile) return dir.length()
        var total = 0L
        var count = 0
        dir.walkTopDown().onFail { _, _ -> }.forEach { f ->
            if (++count > cap) return total
            if (f.isFile) runCatching { total += f.length() }
        }
        return total
    }

    fun humanSize(n: Long): String {
        if (n <= 0) return "0B"
        val units = arrayOf("B", "KB", "MB", "GB", "TB")
        var v = n.toDouble()
        var i = 0
        while (v >= 1024 && i < units.lastIndex) {
            v /= 1024
            i++
        }
        return if (i == 0) "${n}B" else String.format(Locale.getDefault(), "%.1f%s", v, units[i])
    }

    fun fmtTime(ms: Long): String =
        runCatching { sdf.format(java.util.Date(ms)) }.getOrDefault("")

    fun fmtRelative(ms: Long): String =
        DateUtils.getRelativeTimeSpanString(ms, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS)
            .toString()

    /** 模组禁用 / 启用：.jar <-> .jar.disabled（与桌面版一致） */
    fun toggleMod(path: String): Boolean {
        val f = File(path)
        if (!f.exists()) return false
        val target = if (f.name.endsWith(".jar")) File(f.parentFile, f.name + ".disabled")
        else File(f.parentFile, f.name.removeSuffix(".disabled"))
        return f.renameTo(target)
    }

    fun delete(path: String): Boolean {
        val f = File(path)
        return if (f.isDirectory) f.deleteRecursively() else f.delete()
    }

    /** 存档缩略图（icon.png），失败返回 null */
    fun loadIcon(path: String, maxPx: Int = 96): android.graphics.Bitmap? =
        runCatching {
            val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(path, opts)
            val scale = maxOf(1, maxOf(opts.outWidth, opts.outHeight) / maxPx)
            BitmapFactory.decodeFile(path, BitmapFactory.Options().apply { inSampleSize = scale })
        }.getOrNull()
}
