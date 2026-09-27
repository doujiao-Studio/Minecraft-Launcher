package com.ncl.launcher.mc

import com.google.gson.Gson
import com.ncl.launcher.auth.AccountStore
import com.ncl.launcher.data.Config
import com.ncl.launcher.data.ConfigStore
import com.ncl.launcher.data.Paths
import java.io.File

/**
 * 启动参数拼装（对应桌面版 mcl/launch.py）：
 *   java [jvmArgs] mainClass [gameArgs]
 *
 * Android 与桌面的差异只在环境上：
 *   - 自带 JRE（runtime/bin/java）
 *   - LD_LIBRARY_PATH 里塞入 natives + 渲染器 + JVM 自己的 lib
 *   - os.name 伪装成 Linux（MC 的 natives 规则只认 linux/windows/osx）
 */
object McLauncher {

    private val gson = Gson()

    data class LaunchSpec(
        val argv: List<String>,
        val env: Map<String, String>,
        val workDir: File,
        val versionId: String
    )

    private fun readDetails(versionId: String): Pair<VersionDetails, VersionDetails?> {
        val self = gson.fromJson(Paths.versionJson(versionId).readText(), VersionDetails::class.java)
            ?: throw IllegalStateException("版本 json 损坏：$versionId")
        val parentId = self.inheritsFrom
        val parent = if (!parentId.isNullOrBlank() && Paths.versionJson(parentId).exists()) {
            runCatching {
                gson.fromJson(Paths.versionJson(parentId).readText(), VersionDetails::class.java)
            }.getOrNull()
        } else null
        return Pair(self, parent)
    }

    fun build(versionId: String, width: Int = 0, height: Int = 0): LaunchSpec {
        val cfg = ConfigStore.load()
        val acc = AccountStore.active()
        val (self, parent) = readDetails(versionId)

        val java = File(
            cfg.javaPath.ifBlank { Paths.javaBin().absolutePath }
        )
        require(java.exists()) { "没有 Java 运行时：请在设置里导入或下载 JRE" }

        // ---- classpath ----
        val libs = LinkedHashMap<String, Library>()
        parent?.libraries.orEmpty().forEach { libs[it.name] = it }
        self.libraries.orEmpty().forEach { libs[it.name] = it }
        val libDir = Paths.librariesDir()
        val cp = ArrayList<String>()
        cp.add(Paths.clientJar(versionId).absolutePath)
        libs.values.filter { VersionManifest.libraryApplies(it) }
            .mapNotNull { lib ->
                val path = lib.downloads?.artifact?.path ?: VersionManifest.libraryPath(lib.name)
                File(libDir, path)
            }
            .filter { it.exists() }
            .forEach { cp.add(it.absolutePath) }

        // ---- 变量表 ----
        val gameDir = Paths.gameDir(versionId).apply { mkdirs() }
        val assetsDir = Paths.assetsDir()
        val assetIndex = self.assetIndex ?: parent?.assetIndex
        val tokens = mapOf(
            "auth_player_name" to acc.name,
            "auth_uuid" to acc.uuid,
            "auth_access_token" to acc.accessToken.ifBlank { "0" },
            "auth_session" to acc.accessToken.ifBlank { "0" },
            "user_type" to acc.userType,
            "user_properties" to "{}",
            "version_name" to versionId,
            "version_type" to (self.type.ifBlank { parent?.type ?: "release" }),
            "game_directory" to gameDir.absolutePath,
            "assets_root" to assetsDir.absolutePath,
            "assets_index_name" to (assetIndex?.id ?: self.assets ?: "legacy"),
            "game_assets" to assetsDir.absolutePath,
            "launcher_name" to "NCL",
            "launcher_version" to "1.0.0",
            "natives_directory" to File(Paths.versionDir(versionId), "natives").absolutePath,
            "classpath" to cp.joinToString(":")
        )

        // ---- jvm 参数 ----
        val jvmArgs = ArrayList<String>()
        jvmArgs.addAll(collectArgs(parent, self, "jvm", tokens, width, height))
        jvmArgs.addAll(androidJvmArgs(cfg, versionId, width, height))
        jvmArgs.add("-cp")
        jvmArgs.add(cp.joinToString(":"))

        val mainClass = self.mainClass.ifBlank { parent?.mainClass ?: "net.minecraft.client.main.Main" }

        // ---- game 参数 ----
        val gameArgs = ArrayList<String>()
        val rawGame = collectArgs(parent, self, "game", tokens, width, height)
        if (rawGame.isNotEmpty()) {
            gameArgs.addAll(rawGame)
        } else {
            (self.minecraftArguments ?: parent?.minecraftArguments ?: "").split(" ")
                .filter { it.isNotBlank() }.map { replace(it, tokens) }
                .forEach { gameArgs.add(it) }
        }
        if (width > 0 && height > 0) {
            if (!gameArgs.contains("--width")) gameArgs.addAll(listOf("--width", width.toString()))
            if (!gameArgs.contains("--height")) gameArgs.addAll(listOf("--height", height.toString()))
        }

        val argv = ArrayList<String>()
        argv.add(java.absolutePath)
        argv.addAll(jvmArgs)
        argv.add(mainClass)
        argv.addAll(gameArgs)

        return LaunchSpec(argv, buildEnv(cfg, versionId), gameDir, versionId)
    }

    /** 从 parent + self 的 arguments 里取指定段，处理 rules 与变量替换 */
    private fun collectArgs(
        parent: VersionDetails?, self: VersionDetails, section: String,
        tokens: Map<String, String>, width: Int, height: Int
    ): List<String> {
        val out = ArrayList<String>()
        val raw = (parent?.arguments?.get(section) ?: emptyList()) +
                (self.arguments?.get(section) ?: emptyList())
        for (item in raw) {
            when (item) {
                is String -> out.add(replace(item, tokens))
                is Map<*, *> -> {
                    @Suppress("UNCHECKED_CAST")
                    val m = item as Map<String, Any>
                    if (!argAllowed(m, width, height)) continue
                    val value = m["value"]
                    when (value) {
                        is String -> out.add(replace(value, tokens))
                        is List<*> -> value.filterIsInstance<String>().forEach { out.add(replace(it, tokens)) }
                    }
                }
            }
        }
        return out
    }

    private fun argAllowed(m: Map<String, Any>, width: Int, height: Int): Boolean {
        val rules = m["rules"] as? List<*> ?: return true
        var allow = false
        for (r in rules) {
            val rm = r as? Map<*, *> ?: continue
            val action = rm["action"] as? String ?: "allow"
            val os = rm["os"] as? Map<*, *>
            val features = rm["features"] as? Map<*, *>
            var match = true
            if (os != null) {
                val name = os["name"] as? String
                if (name != null && name != "linux") match = false
            }
            if (features != null) {
                for ((k, v) in features) {
                    val want = v as? Boolean ?: false
                    val have = when (k as? String) {
                        "is_demo_user" -> false
                        "has_custom_resolution" -> width > 0 && height > 0
                        "has_quick_plays_support", "is_quick_play_singleplayer",
                        "is_quick_play_multiplayer", "is_quick_play_realms" -> false
                        else -> false
                    }
                    if (want != have) match = false
                }
            }
            if (match) allow = action == "allow"
        }
        return allow
    }

    /** Android 上必须额外注入的一堆 JVM 参数 */
    private fun androidJvmArgs(cfg: Config, versionId: String, width: Int, height: Int): List<String> {
        val runtime = Paths.runtimeDir()
        val tmp = File(Paths.root, "tmp").apply { mkdirs() }
        val args = mutableListOf(
            "-Xmx${cfg.memory}M",
            "-Xms${(cfg.memory / 3).coerceAtLeast(128)}M",
            "-XX:+UseG1GC",
            "-XX:MaxGCPauseMillis=100",
            "-Djava.home=${runtime.absolutePath}",
            "-Djava.io.tmpdir=${tmp.absolutePath}",
            "-Duser.home=${Paths.root.absolutePath}",
            "-Duser.language=zh",
            "-Duser.country=CN",
            "-Dos.name=Linux",
            "-Dos.version=Android",
            "-Dorg.lwjgl.system.allocator=system",
            "-Dlog4j2.formatMsgNoLookups=true",
            "-Dminecraft.launcher.brand=NCL",
            "-Dminecraft.launcher.version=1.0.0"
        )
        // 分辨率缩放：控制 GPU 压力
        if (cfg.resolutionScale in 25..100 && cfg.resolutionScale != 100 && width > 0) {
            args.add("-Dorg.lwjgl.system.windowScale=${cfg.resolutionScale / 100f}")
        }
        return args
    }

    private fun buildEnv(cfg: Config, versionId: String): Map<String, String> {
        val runtime = Paths.runtimeDir()
        val natives = File(Paths.versionDir(versionId), "natives")
        val gl = Paths.glDir()
        val env = LinkedHashMap<String, String>()

        val ld = listOf(
            gl.absolutePath,
            natives.absolutePath,
            File(runtime, "lib").absolutePath,
            File(runtime, "lib/jli").absolutePath,
            File(runtime, "lib/server").absolutePath,
            "/system/lib64", "/vendor/lib64"
        ).joinToString(":")

        env["LD_LIBRARY_PATH"] = ld
        env["PATH"] = File(runtime, "bin").absolutePath + ":" + (System.getenv("PATH") ?: "/system/bin")
        env["HOME"] = Paths.root.absolutePath
        env["TMPDIR"] = File(Paths.root, "tmp").absolutePath
        env["JAVA_HOME"] = runtime.absolutePath

        // 渲染器环境变量（gl4es / MobileGlues 都认这几个）
        when (cfg.renderer) {
            Config.RENDERER_GL4ES -> {
                env["LIBGL_ES"] = "2"
                env["NCL_GL_LIB"] = File(gl, "libgl4es_114.so").absolutePath
            }
            Config.RENDERER_MOBILEGLUES -> {
                env["NCL_GL_LIB"] = File(gl, "libMobileGlues.so").absolutePath
            }
            Config.RENDERER_VULKAN -> {
                env["NCL_GL_LIB"] = File(gl, "libvulkan-wrapper.so").absolutePath
            }
            else -> {
                env["LIBGL_ES"] = "2"
            }
        }
        return env
    }

    private fun replace(s: String, tokens: Map<String, String>): String {
        var out = s
        tokens.forEach { (k, v) -> out = out.replace("\${$k}", v) }
        return out
    }
}
