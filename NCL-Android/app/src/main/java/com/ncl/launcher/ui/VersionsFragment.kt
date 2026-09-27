package com.ncl.launcher.ui

import android.content.Intent
import android.os.Bundle
import android.view.View
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.ncl.launcher.R
import com.ncl.launcher.data.Paths
import com.ncl.launcher.databinding.FragmentVersionsBinding
import com.ncl.launcher.mc.Scan
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** 版本管理：已安装版本列表，双击/点「查看详情」进入详情（模组 / 资源包 / 存档 / 数据包） */
class VersionsFragment : Fragment(R.layout.fragment_versions) {

    private var _b: FragmentVersionsBinding? = null
    private val b get() = _b!!

    private lateinit var adapter: SimpleAdapter
    private var selectedVersion: String = ""

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        _b = FragmentVersionsBinding.bind(view)

        adapter = SimpleAdapter(
            onClick = { item -> selectedVersion = item.payload as? String ?: "" },
            onLongClick = { item ->
                selectedVersion = item.payload as? String ?: ""
                openDetail()
                true
            }
        )
        b.rv.layoutManager = LinearLayoutManager(requireContext())
        b.rv.adapter = adapter

        b.btnRefresh.setOnClickListener { refresh() }
        b.btnDetail.setOnClickListener { openDetail() }
        b.btnDir.setOnClickListener {
            if (selectedVersion.isBlank()) toast("先选一个版本")
            else requireContext().openDir(Paths.gameDir(selectedVersion).absolutePath)
        }
        b.btnDel.setOnClickListener { deleteSelected() }

        refresh()
    }

    /** 扫描目录大小可能耗时，放 IO 线程算，回主线程刷新 */
    private fun refresh() {
        lifecycleScope.launch {
            val rows = withContext(Dispatchers.IO) {
                val list = Paths.installedVersions()
                list.map { vid ->
                    val dir = Paths.versionDir(vid)
                    val jar = Paths.clientJar(vid)
                    val mods = Paths.modsDir(vid).listFiles()?.count {
                        it.name.endsWith(".jar") || it.name.endsWith(".jar.disabled")
                    } ?: 0
                    val saves = Paths.savesDir(vid).listFiles()?.count { it.isDirectory } ?: 0
                    RowItem(
                        title = vid,
                        sub = "模组 $mods · 存档 $saves · ${Scan.humanSize(Scan.dirSize(dir))}",
                        tail = if (jar.exists()) "就绪" else "缺本体",
                        payload = vid
                    )
                }
            }
            val ids = rows.mapNotNull { it.payload as? String }
            selectedVersion = ids.firstOrNull { it == selectedVersion } ?: ids.firstOrNull() ?: ""
            _b?.tvEmpty?.visibility = if (rows.isEmpty()) View.VISIBLE else View.GONE
            adapter.submitList(rows)
        }
    }

    private fun openDetail() {
        if (selectedVersion.isBlank()) {
            toast("先选一个版本")
            return
        }
        startActivity(
            Intent(requireContext(), VersionDetailActivity::class.java)
                .putExtra(VersionDetailActivity.EXTRA_VERSION, selectedVersion)
        )
    }

    private fun deleteSelected() {
        val vid = selectedVersion
        if (vid.isBlank()) {
            toast("先选一个版本")
            return
        }
        android.app.AlertDialog.Builder(requireContext())
            .setTitle("删除版本？")
            .setMessage("将删除 $vid 的本体与库文件，存档不会被删除。")
            .setNegativeButton("取消", null)
            .setPositiveButton("删除") { _, _ ->
                Paths.versionDir(vid).deleteRecursively()
                refresh()
                toast("已删除 $vid")
            }
            .show()
    }

    override fun onResume() {
        super.onResume()
        if (::adapter.isInitialized) refresh()
    }

    override fun onDestroyView() {
        _b = null
        super.onDestroyView()
    }
}
