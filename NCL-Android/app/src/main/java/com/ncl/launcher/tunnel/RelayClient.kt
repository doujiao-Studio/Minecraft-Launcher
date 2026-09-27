package com.ncl.launcher.tunnel

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/**
 * 内网穿透：把本地游戏端口通过中继服务器暴露出去。
 *
 * 协议极简（与桌面版 mcl/tunnel/relay.py 的思路一致）：
 *   连上中继先发一行 "JOIN <房间码>\n"，之后就是裸 TCP 双向转发；
 *   好友侧同样连中继并报同一个房间码，两端数据互转。
 */
class RelayClient(
    private val host: String,
    private val port: Int,
    private val room: String,
    private val localPort: Int,
    private val onLog: (String) -> Unit
) {

    private val running = AtomicBoolean(false)
    private var job: Job? = null
    @Volatile
    private var relay: Socket? = null
    @Volatile
    private var local: Socket? = null

    fun start(scope: CoroutineScope) {
        if (running.getAndSet(true)) return
        job = scope.launch(Dispatchers.IO) {
            runCatching { loop() }.onFailure { onLog("穿透异常：${it.message}") }
            closeAll()
            running.set(false)
        }
    }

    fun stop() {
        running.set(false)
        closeAll()
        job?.cancel()
        job = null
        onLog("已停止穿透")
    }

    val isRunning: Boolean get() = running.get()

    private fun closeAll() {
        runCatching { local?.close() }
        runCatching { relay?.close() }
    }

    private fun loop() {
        onLog("连接中继 $host:$port …")
        val r = Socket()
        relay = r
        r.connect(InetSocketAddress(host, port), 8000)
        r.soTimeout = 0
        val out = r.getOutputStream()
        out.write("JOIN $room\n".toByteArray(Charsets.UTF_8))
        out.flush()
        onLog("已注册房间码：$room（本地端口 $localPort）")

        val l = Socket()
        local = l
        l.connect(InetSocketAddress("127.0.0.1", localPort), 5000)
        onLog("已连接本地游戏端口 $localPort，开始转发")

        val t1 = thread(name = "relay->local") { pump(r.getInputStream(), l.getOutputStream()) }
        val t2 = thread(name = "local->relay") { pump(l.getInputStream(), r.getOutputStream()) }
        t1.join()
        t2.join()
    }

    private fun pump(input: InputStream, out: OutputStream) {
        val buf = ByteArray(64 * 1024)
        try {
            while (running.get()) {
                val n = input.read(buf)
                if (n <= 0) break
                out.write(buf, 0, n)
                out.flush()
            }
        } catch (e: IOException) {
            if (running.get()) onLog("转发结束：${e.message ?: "连接关闭"}")
        }
    }
}
