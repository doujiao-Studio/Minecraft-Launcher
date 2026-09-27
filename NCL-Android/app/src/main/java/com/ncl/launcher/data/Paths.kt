package com.ncl.launcher.data

import android.content.Context
import java.io.File

/**
 * 目录布局，与桌面版 NCL 保持一一对应：
 *
 *   <数据根>/NCLData/versions/<id>/...    版本 jar / 库 / 资源索引
 *   <数据根>/.minecraft/<id>/...          该版本的存档 / 模组 / 资源包
 *   <数据根>/NCLData/config.json          配置
 *   <数据根>/NCLData/accounts.json        账户
 *
 * 首次启动（ensureLayout）会自动创建全部目录，不弹任何提示。
 */
object Paths {

    @Volatile
    var initialized: Boolean = false
        private set

    lateinit var root: File          // NCLData
        private set
    lateinit var minecraftRoot: File // .minecraft
        private set
    lateinit var dataRoot: File      // NCLData 的父目录（一般是 /sdcard/Android/data/<pkg>/files）
        private set

    fun init(context: Context) {
        if (initialized && ::root.isInitialized) return
        val base: File = context.getExternalFilesDir(null) ?: context.filesDir
        dataRoot = base
        root = File(base, "NCLData")
        minecraftRoot = File(base, ".minecraft")
        initialized = true
    }

    /** 目录骨架：返回本次是否为首次运行。 */
    fun ensureLayout(): Boolean {
        val marker = File(root, ".initialized")
        val firstRun = !marker.exists()

        listOf("versions", "servers", "relay", "logs", "cache", "runtime", "tmp").forEach {
            File(root, it).mkdirs()
        }
        listOf(
            "saves", "mods", "resourcepacks", "shaderpacks",
            "screenshots", "config", "logs", "crash-reports"
        ).forEach {
            File(minecraftRoot, it).mkdirs()
        }
        runCatching { marker.createNewFile() }
        return firstRun
    }

    // ---- 版本相关 ----
    fun versionDir(versionId: String): File = File(root, "versions/$versionId")
    fun versionJson(versionId: String): File = File(versionDir(versionId), "version.json")
    fun clientJar(versionId: String): File = File(versionDir(versionId), "client.jar")
    fun librariesDir(): File = File(root, "libraries")
    fun assetsDir(): File = File(root, "assets")

    /** 某版本的游戏目录（存档 / 模组 都在这里） */
    fun gameDir(versionId: String): File = File(minecraftRoot, versionId)
    fun modsDir(versionId: String): File = File(gameDir(versionId), "mods")
    fun savesDir(versionId: String): File = File(gameDir(versionId), "saves")
    fun resourcePacksDir(versionId: String): File = File(gameDir(versionId), "resourcepacks")
    fun dataPacksDir(versionId: String): File = File(gameDir(versionId), "datapacks")

    /** 全局资源 / 数据包目录（跨版本共享） */
    fun globalResourcePacksDir(): File = File(minecraftRoot, "resourcepacks")
    fun globalDataPacksDir(): File = File(minecraftRoot, "datapacks")

    fun runtimeDir(): File = File(root, "runtime")
    fun javaBin(): File = File(runtimeDir(), "bin/java")
    fun glDir(): File = File(root, "gl")

    fun logDir(): File = File(root, "logs")
    fun cacheDir(): File = File(root, "cache")

    fun configFile(): File = File(root, "config.json")
    fun accountsFile(): File = File(root, "accounts.json")
    fun serversFile(): File = File(root, "servers.json")

    /** 已安装版本：目录里同时有 version.json 与 client.jar 才算完整 */
    fun installedVersions(): List<String> =
        (File(root, "versions").listFiles()?.filter {
            it.isDirectory && File(it, "version.json").exists()
        }?.map { it.name } ?: emptyList()).sorted()
}
