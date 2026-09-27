package com.ncl.launcher.data

import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import java.io.File

data class Config(
    @SerializedName("memory") var memory: Int = 1024,
    @SerializedName("java_path") var javaPath: String = "",
    @SerializedName("renderer") var renderer: String = RENDERER_AUTO,
    @SerializedName("mirror") var mirror: String = MIRROR_BMCLAPI,
    @SerializedName("last_version") var lastVersion: String = "",
    @SerializedName("resolution_scale") var resolutionScale: Int = 100,
    @SerializedName("auth_mode") var authMode: String = "offline",
    @SerializedName("ygg_server") var yggServer: String = "",
    @SerializedName("relay_host") var relayHost: String = "",
    @SerializedName("relay_port") var relayPort: Int = 25565,
    @SerializedName("room") var room: String = "",
    @SerializedName("local_port") var localPort: Int = 25565
) {
    companion object {
        const val RENDERER_AUTO = "auto"
        const val RENDERER_GL4ES = "gl4es"
        const val RENDERER_MOBILEGLUES = "mobileglues"
        const val RENDERER_VULKAN = "vulkan"

        const val MIRROR_MOJANG = "mojang"
        const val MIRROR_BMCLAPI = "bmclapi"
    }
}

object ConfigStore {

    private val gson = Gson()
    private var cache: Config? = null

    fun load(): Config {
        cache?.let { return it }
        val f: File = Paths.configFile()
        val cfg = if (f.exists()) {
            runCatching { gson.fromJson(f.readText(), Config::class.java) }.getOrNull() ?: Config()
        } else {
            Config()
        }
        f.parentFile?.mkdirs()
        if (!f.exists()) save(cfg)
        cache = cfg
        return cfg
    }

    fun save(cfg: Config = load()) {
        cache = cfg
        val f = Paths.configFile()
        runCatching {
            f.parentFile?.mkdirs()
            f.writeText(gson.toJson(cfg))
        }
    }

    fun edit(block: (Config) -> Unit) {
        val c = load()
        block(c)
        save(c)
    }
}
