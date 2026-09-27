package com.ncl.launcher.mc

import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.File
import java.util.zip.GZIPInputStream

/**
 * 极简 NBT 读取器（只够解析存档根目录的 level.dat）。
 * 与桌面版 mcl/ui/version_detail.py 里的 Python 实现思路一致：只读我们需要的字段，
 * 遇到任何异常都安全返回 null，绝不让坏存档崩掉界面。
 */
object Nbt {

    data class LevelInfo(
        val name: String,
        val gameType: String,
        val version: String,
        val lastPlayed: Long,
        val seed: Long = 0L
    )

    fun readLevel(dat: File): LevelInfo? = runCatching {
        val raw = if (isGzip(dat)) {
            GZIPInputStream(dat.inputStream()).use { it.readBytes() }
        } else {
            dat.readBytes()
        }
        val root = Parser(raw).readRoot() ?: return@runCatching null
        val data = root["Data"] as? Map<*, *> ?: root

        val name = data["LevelName"] as? String ?: ""
        val gameType = when (data["GameType"]) {
            0 -> "生存"
            1 -> "创造"
            2 -> "冒险"
            3 -> "旁观"
            is Int -> "未知(${data["GameType"]})"
            else -> "生存"
        }
        val verMap = data["Version"] as? Map<*, *>
        val version = verMap?.get("Name") as? String ?: ""
        val lastPlayed = (data["LastPlayed"] as? Long) ?: 0L
        val seed = (data["WorldGenSettings"] as? Map<*, *>)?.let { it["seed"] as? Long }
            ?: (data["RandomSeed"] as? Long) ?: 0L
        LevelInfo(name.ifBlank { "世界" }, gameType, version, lastPlayed, seed)
    }.getOrNull()

    private fun isGzip(f: File): Boolean {
        val head = ByteArray(2)
        f.inputStream().use { it.read(head) }
        return head[0] == 0x1f.toByte() && head[1] == 0x8b.toByte()
    }

    private class Parser(private val bytes: ByteArray) {

        private var pos = 0

        private fun u1(): Int = bytes[pos++].toInt() and 0xFF
        private fun i2(): Int = ((u1() shl 8) or u1()).let { if (it > 32767) it - 65536 else it }
        private fun i4(): Int = (u1() shl 24) or (u1() shl 16) or (u1() shl 8) or u1()
        private fun i8(): Long = ((i4().toLong() and 0xFFFFFFFFL) shl 32) or (i4().toLong() and 0xFFFFFFFFL)
        private fun str(): String {
            val len = i2()
            val s = String(bytes, pos, len, Charsets.UTF_8)
            pos += len
            return s
        }

        fun readRoot(): Map<String, Any>? {
            u1() // 根 tag 一定是 compound(10)
            str() // 根名字
            return payload(10) as? Map<String, Any>
        }

        private fun payload(tag: Int): Any? = when (tag) {
            0 -> null
            1 -> u1().toByte()
            2 -> i2().toShort()
            3 -> i4()
            4 -> i8()
            5 -> java.lang.Float.intBitsToFloat(i4())
            6 -> java.lang.Double.longBitsToDouble(i8())
            7 -> {
                val n = i4()
                val out = ByteArray(n)
                System.arraycopy(bytes, pos, out, 0, n)
                pos += n
                out
            }
            8 -> str()
            9 -> {
                val itemType = u1()
                val n = i4()
                val list = ArrayList<Any?>(n)
                repeat(n) { list.add(payload(itemType)) }
                list
            }
            10 -> {
                val map = HashMap<String, Any>()
                while (pos < bytes.size) {
                    val t = u1()
                    if (t == 0) break
                    val name = str()
                    val v = payload(t)
                    if (v != null) map[name] = v
                }
                map
            }
            11 -> {
                val n = i4()
                val out = IntArray(n)
                repeat(n) { out[it] = i4() }
                out
            }
            12 -> {
                val n = i4()
                val out = LongArray(n)
                repeat(n) { out[it] = i8() }
                out
            }
            else -> throw IllegalStateException("未知 NBT tag $tag")
        }
    }
}
