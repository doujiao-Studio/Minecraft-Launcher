package com.ncl.launcher.data

import com.google.gson.Gson
import java.io.File

data class ServerEntry(
    var name: String = "",
    var address: String = "",
    var version: String = ""
)

private data class ServerFile(var servers: MutableList<ServerEntry> = mutableListOf())

object ServerStore {

    private val gson = Gson()
    private var cache: ServerFile? = null

    private fun load(): ServerFile {
        cache?.let { return it }
        val f: File = Paths.serversFile()
        val sf = if (f.exists()) {
            runCatching { gson.fromJson(f.readText(), ServerFile::class.java) }.getOrNull() ?: ServerFile()
        } else ServerFile()
        cache = sf
        return sf
    }

    private fun save(sf: ServerFile = load()) {
        cache = sf
        runCatching {
            Paths.serversFile().parentFile?.mkdirs()
            Paths.serversFile().writeText(gson.toJson(sf))
        }
    }

    fun list(): List<ServerEntry> = load().servers

    fun add(e: ServerEntry) {
        val sf = load()
        sf.servers.add(e)
        save(sf)
    }

    fun remove(e: ServerEntry) {
        val sf = load()
        sf.servers.removeAll { it.name == e.name && it.address == e.address }
        save(sf)
    }
}

/**
 * 服务器状态查询（Minecraft 1.7+ 的 Server List Ping 协议）。
 * 失败不抛异常，返回 null，UI 显示“离线”。
 */
object ServerPing {

    data class Status(val online: Boolean, val players: String = "", val version: String = "", val motd: String = "")

    fun query(host: String, port: Int, timeoutMs: Int = 2500): Status {
        return runCatching {
            java.net.Socket().use { sock ->
                sock.connect(java.net.InetSocketAddress(host, port), timeoutMs)
                sock.soTimeout = timeoutMs
                val out = sock.getOutputStream()
                val input = java.net.DataInputStream(sock.getInputStream())

                fun writeVarInt(value: Int) {
                    var v = value
                    while (true) {
                        if ((v and 0x7F) == v) {
                            out.write(v)
                            return
                        }
                        out.write((v and 0x7F) or 0x80)
                        v = v ushr 7
                    }
                }

                val hostBytes = host.toByteArray(Charsets.UTF_8)
                // handshake
                val buf = java.io.ByteArrayOutputStream()
                fun varIntToBuf(value: Int) {
                    var v = value
                    while (true) {
                        if ((v and 0x7F) == v) { buf.write(v); return }
                        buf.write((v and 0x7F) or 0x80)
                        v = v ushr 7
                    }
                }
                varIntToBuf(0x00)
                varIntToBuf(0x2F) // 协议号，够用于握手
                varIntToBuf(hostBytes.size)
                buf.write(hostBytes)
                buf.write((port shr 8) and 0xFF)
                buf.write(port and 0xFF)
                varIntToBuf(1) // next state = status
                writeVarInt(buf.size())
                out.write(buf.toByteArray())
                out.write(0x00) // status request
                out.flush()

                fun readVarInt(): Int {
                    var num = 0
                    var shift = 0
                    while (true) {
                        val b = input.readByte().toInt() and 0xFF
                        num = num or ((b and 0x7F) shl shift)
                        if ((b and 0x80) == 0) break
                        shift += 7
                    }
                    return num
                }
                val len = readVarInt()
                val payload = ByteArray(len)
                input.readFully(payload)
                val text = String(payload, Charsets.UTF_8)
                val jsonIdx = text.indexOf('{')
                if (jsonIdx < 0) return@runCatching Status(true)
                val o = org.json.JSONObject(text.substring(jsonIdx))
                val players = o.optJSONObject("players")
                val ver = o.optJSONObject("version")
                Status(
                    online = true,
                    players = "${players?.optInt("online", 0)}/${players?.optInt("max", 0)}",
                    version = ver?.optString("name", "") ?: "",
                    motd = runCatching { o.optString("description") }.getOrDefault("")
                )
            }
        }.getOrNull() ?: Status(false)
    }
}
