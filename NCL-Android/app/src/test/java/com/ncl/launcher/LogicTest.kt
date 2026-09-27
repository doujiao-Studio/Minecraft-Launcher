package com.ncl.launcher

import com.ncl.launcher.data.Config
import com.ncl.launcher.mc.Library
import com.ncl.launcher.mc.Nbt
import com.ncl.launcher.mc.OsRule
import com.ncl.launcher.mc.Rule
import com.ncl.launcher.mc.VersionManifest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.File
import java.util.zip.GZIPOutputStream

/**
 * 纯 JVM 逻辑测试（不依赖 Android 框架）：
 *   ./gradlew :app:testDebugUnitTest
 */
class LogicTest {

    // ------------------------------------------------------------------ NBT
    private fun nbtBytes(name: String, gameType: Int, version: String, lastPlayed: Long): ByteArray {
        val bo = ByteArrayOutputStream()
        val out = DataOutputStream(bo)

        fun str(s: String) {
            out.writeShort(s.toByteArray(Charsets.UTF_8).size)
            out.write(s.toByteArray(Charsets.UTF_8))
        }

        out.writeByte(10)          // root compound
        str("")
        out.writeByte(10)          // Data compound
        str("Data")
        out.writeByte(8); str("LevelName"); str(name)
        out.writeByte(3); str("GameType"); out.writeInt(gameType)
        out.writeByte(10); str("Version")
        out.writeByte(8); str("Name"); str(version)
        out.writeByte(0)           // end Version
        out.writeByte(4); str("LastPlayed"); out.writeLong(lastPlayed)
        out.writeByte(0)           // end Data
        out.writeByte(0)           // end root
        out.flush()
        return bo.toByteArray()
    }

    @Test
    fun nbt_reads_level_dat() {
        val tmp = File.createTempFile("level", ".dat")
        GZIPOutputStream(tmp.outputStream()).use { it.write(nbtBytes("我的生存世界", 0, "1.21.1", 1700000000000L)) }
        val info = Nbt.readLevel(tmp)
        assertEquals("我的生存世界", info?.name)
        assertEquals("生存", info?.gameType)
        assertEquals("1.21.1", info?.version)
        assertEquals(1700000000000L, info?.lastPlayed)
        tmp.delete()
    }

    @Test
    fun nbt_reads_uncompressed() {
        val tmp = File.createTempFile("level-plain", ".dat")
        tmp.writeBytes(nbtBytes("创造世界", 1, "26.1", 42L))
        val info = Nbt.readLevel(tmp)
        assertEquals("创造世界", info?.name)
        assertEquals("创造", info?.gameType)
        tmp.delete()
    }

    @Test
    fun nbt_garbage_returns_null() {
        val tmp = File.createTempFile("broken", ".dat")
        tmp.writeBytes(byteArrayOf(1, 2, 3, 4, 5))
        assertNull(Nbt.readLevel(tmp))
        tmp.delete()
    }

    @Test
    fun nbt_missing_file_returns_null() {
        assertNull(Nbt.readLevel(File("/definitely/not/here/level.dat")))
    }

    // --------------------------------------------------------------- 库路径
    @Test
    fun library_path_converts_maven_name() {
        assertEquals(
            "com/mojang/brigadier/1.0.17/brigadier-1.0.17.jar",
            VersionManifest.libraryPath("com.mojang:brigadier:1.0.17")
        )
        assertEquals(
            "org/lwjgl/lwjgl/3.3.1/lwjgl-3.3.1-natives-linux.jar",
            VersionManifest.libraryPath("org.lwjgl:lwjgl:3.3.1", "natives-linux")
        )
    }

    @Test
    fun library_rules_respect_linux() {
        assertTrue(VersionManifest.libraryApplies(Library(name = "a:b:1")))
        assertTrue(
            VersionManifest.libraryApplies(
                Library(name = "a:b:1", rules = listOf(Rule("allow", OsRule("linux"))))
            )
        )
        assertEquals(
            false,
            VersionManifest.libraryApplies(
                Library(name = "a:b:1", rules = listOf(Rule("allow", OsRule("windows"))))
            )
        )
    }

    // ---------------------------------------------------------------- 配置
    @Test
    fun config_defaults() {
        val c = Config()
        assertEquals(1024, c.memory)
        assertEquals(Config.MIRROR_BMCLAPI, c.mirror)
        assertEquals("offline", c.authMode)
    }
}
