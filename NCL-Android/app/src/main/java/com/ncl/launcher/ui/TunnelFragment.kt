package com.ncl.launcher.ui

import android.os.Bundle
import android.view.View
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.ncl.launcher.R
import com.ncl.launcher.data.ConfigStore
import com.ncl.launcher.databinding.FragmentTunnelBinding
import com.ncl.launcher.tunnel.RelayClient
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** 内网穿透：把本地游戏端口通过中继服务器暴露给好友 */
class TunnelFragment : Fragment(R.layout.fragment_tunnel) {

    private var _b: FragmentTunnelBinding? = null
    private val b get() = _b!!

    private var relay: RelayClient? = null

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        _b = FragmentTunnelBinding.bind(view)
        val cfg = ConfigStore.load()

        b.etHost.setText(cfg.relayHost)
        b.etPort.setText(if (cfg.relayPort > 0) cfg.relayPort.toString() else "")
        b.etRoom.setText(cfg.room)
        b.etLocal.setText(if (cfg.localPort > 0) cfg.localPort.toString() else "25565")

        b.btnStart.setOnClickListener { start() }
        b.btnStop.setOnClickListener { relay?.stop(); relay = null }
    }

    private fun start() {
        val host = b.etHost.text.toString().trim()
        val port = b.etPort.text.toString().toIntOrNull() ?: 0
        val room = b.etRoom.text.toString().trim()
        val localPort = b.etLocal.text.toString().toIntOrNull() ?: 25565
        if (host.isBlank() || port <= 0 || room.isBlank()) {
            toast("请填写中继地址、端口和房间码")
            return
        }
        ConfigStore.edit {
            it.relayHost = host
            it.relayPort = port
            it.room = room
            it.localPort = localPort
        }
        relay?.stop()
        relay = RelayClient(host, port, room, localPort) { line -> log(line) }
        relay?.start(lifecycleScope)
        log("启动穿透：$room -> $host:$port（本地 $localPort）")
    }

    private fun log(line: String) {
        activity?.runOnUiThread {
            val time = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            _b?.tvLog?.append("$time  $line\n")
        }
    }

    override fun onDestroyView() {
        relay?.stop()
        relay = null
        _b = null
        super.onDestroyView()
    }
}
