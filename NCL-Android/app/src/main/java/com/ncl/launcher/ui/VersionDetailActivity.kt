package com.ncl.launcher.ui

import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.viewpager2.adapter.FragmentStateAdapter
import com.google.android.material.tabs.TabLayoutMediator
import com.ncl.launcher.R
import com.ncl.launcher.data.Paths
import com.ncl.launcher.databinding.ActivityVersionDetailBinding
import com.ncl.launcher.databinding.FragmentPageListBinding
import com.ncl.launcher.mc.Scan
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * 版本详情：模组 / 资源包 / 存档 / 数据包 四个列表页，
 * 对应桌面版的 VersionDetailWindow。
 */
class VersionDetailActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_VERSION = "version"
    }

    private lateinit var binding: ActivityVersionDetailBinding
    private lateinit var vid: String

    /** 当前 tab 选中项（按页下标保存） */
    private val selected = HashMap<Int, Scan.Entry>()

    private val kinds = listOf(
        Scan.Kind.MOD, Scan.Kind.RESOURCE_PACK, Scan.Kind.SAVE, Scan.Kind.DATA_PACK
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vid = intent.getStringExtra(EXTRA_VERSION) ?: ""
        if (vid.isBlank()) {
            finish()
            return
        }
        binding = ActivityVersionDetailBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.tvVersion.text = vid
        binding.pager.adapter = DetailPager(this)
        TabLayoutMediator(binding.tabs, binding.pager) { tab, pos ->
            tab.text = label(kinds[pos])
        }.attach()

        binding.btnRefresh.setOnClickListener { refreshPage() }
        binding.btnDir.setOnClickListener { openDir(Paths.gameDir(vid).absolutePath) }
        binding.btnToggle.setOnClickListener { toggleSelected() }
        binding.btnDelete.setOnClickListener { deleteSelected() }

        updateSummary()
    }

    private fun label(kind: Scan.Kind) = when (kind) {
        Scan.Kind.MOD -> "模组"
        Scan.Kind.RESOURCE_PACK -> "资源包"
        Scan.Kind.SAVE -> "存档"
        Scan.Kind.DATA_PACK -> "数据包"
    }

    fun currentKind(): Scan.Kind = kinds.getOrNull(binding.pager.currentItem) ?: Scan.Kind.MOD

    fun onEntrySelected(pos: Int, entry: Scan.Entry?) {
        if (entry == null) selected.remove(pos) else selected[pos] = entry
    }

    private fun refreshPage() {
        // 通知当前页重新扫描：ViewPager2 的 fragment 通过 tag 找回
        val f = supportFragmentManager.findFragmentByTag("f${binding.pager.currentItem}")
        (f as? ListPageFragment)?.reload()
        toast("已刷新")
    }

    private fun toggleSelected() {
        val e = selected[binding.pager.currentItem]
        if (e == null) {
            toast("先选一个条目")
            return
        }
        if (e.kind != Scan.Kind.MOD) {
            toast("只有模组支持禁用 / 启用")
            return
        }
        if (Scan.toggleMod(e.path)) {
            toast(if (e.enabled) "已禁用 ${e.title}" else "已启用 ${e.title}")
            val f = supportFragmentManager.findFragmentByTag("f${binding.pager.currentItem}")
            (f as? ListPageFragment)?.reload()
        } else {
            toast("操作失败")
        }
    }

    private fun deleteSelected() {
        val e = selected[binding.pager.currentItem]
        if (e == null) {
            toast("先选一个条目")
            return
        }
        if (e.kind == Scan.Kind.SAVE) {
            toast("存档不提供删除入口，避免误删；可到「打开目录」里手动处理")
            return
        }
        android.app.AlertDialog.Builder(this)
            .setTitle("删除？")
            .setMessage(e.title)
            .setNegativeButton("取消", null)
            .setPositiveButton("删除") { _, _ ->
                if (Scan.delete(e.path)) {
                    selected.remove(binding.pager.currentItem)
                    val f = supportFragmentManager.findFragmentByTag("f${binding.pager.currentItem}")
                    (f as? ListPageFragment)?.reload()
                    toast("已删除")
                } else toast("删除失败")
            }
            .show()
    }

    private fun updateSummary() {
        lifecycleScope.launch {
            val info = withContext(Dispatchers.IO) {
                val jar = Paths.clientJar(vid)
                val dir = Paths.versionDir(vid)
                val mods = Scan.mods(vid).size
                val saves = Scan.saves(vid).size
                val rps = Scan.resourcePacks(vid).size
                "本体 ${if (jar.exists()) Scan.humanSize(jar.length()) else "缺失"} · 模组 $mods · 资源包 $rps · 存档 $saves · ${Scan.humanSize(Scan.dirSize(dir))}"
            }
            binding.tvSummary.text = info
        }
    }

    inner class DetailPager(a: FragmentActivity) : FragmentStateAdapter(a) {
        override fun getItemCount(): Int = kinds.size
        override fun createFragment(position: Int): Fragment =
            ListPageFragment.newInstance(vid, kinds[position].ordinal, position)
    }

    // ---------------------------------------------------------------- 子页
    class ListPageFragment : Fragment(R.layout.fragment_page_list) {

        private var _b: FragmentPageListBinding? = null
        private val b get() = _b!!

        private lateinit var adapter: SimpleAdapter
        private var vid: String = ""
        private var kind: Scan.Kind = Scan.Kind.MOD
        private var pageIndex: Int = 0

        override fun onCreate(savedInstanceState: Bundle?) {
            super.onCreate(savedInstanceState)
            vid = arguments?.getString(ARG_VERSION) ?: ""
            kind = Scan.Kind.values()[arguments?.getInt(ARG_KIND) ?: 0]
            pageIndex = arguments?.getInt(ARG_INDEX) ?: 0
        }

        override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
            _b = FragmentPageListBinding.bind(view)
            adapter = SimpleAdapter(onClick = { item ->
                val e = item.payload as? Scan.Entry
                (activity as? VersionDetailActivity)?.onEntrySelected(pageIndex, e)
            })
            b.rv.layoutManager = LinearLayoutManager(requireContext())
            b.rv.adapter = adapter
            reload()
        }

        fun reload() {
            lifecycleScope.launch {
                val entries = withContext(Dispatchers.IO) {
                    when (kind) {
                        Scan.Kind.MOD -> Scan.mods(vid)
                        Scan.Kind.RESOURCE_PACK -> Scan.resourcePacks(vid)
                        Scan.Kind.SAVE -> Scan.saves(vid)
                        Scan.Kind.DATA_PACK -> Scan.dataPacks(vid)
                    }
                }
                val rows = entries.map { e ->
                    RowItem(
                        title = e.title,
                        sub = e.sub,
                        tail = e.tail,
                        iconPath = e.iconPath,
                        payload = e,
                        dim = !e.enabled
                    )
                }
                adapter.submitList(rows)
                b.tvEmpty.visibility = if (rows.isEmpty()) View.VISIBLE else View.GONE
                b.tvEmpty.text = emptyHint()
            }
        }

        private fun emptyHint(): String = when (kind) {
            Scan.Kind.MOD -> "还没有模组：去「下载 → 模组」搜索安装，或把 .jar 放进该版本的 mods 目录"
            Scan.Kind.RESOURCE_PACK -> "还没有资源包：把 .zip 放进 resourcepacks 目录"
            Scan.Kind.SAVE -> "还没有存档：进游戏创建一个世界就会出现在这里"
            Scan.Kind.DATA_PACK -> "还没有数据包：可放进全局 datapacks 或某存档的 datapacks 目录"
        }

        override fun onDestroyView() {
            _b = null
            super.onDestroyView()
        }

        companion object {
            private const val ARG_VERSION = "v"
            private const val ARG_KIND = "k"
            private const val ARG_INDEX = "i"

            fun newInstance(vid: String, kindOrdinal: Int, index: Int) = ListPageFragment().apply {
                arguments = Bundle().apply {
                    putString(ARG_VERSION, vid)
                    putInt(ARG_KIND, kindOrdinal)
                    putInt(ARG_INDEX, index)
                }
            }
        }
    }
}
