package com.ncl.launcher.ui

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentActivity
import androidx.viewpager2.adapter.FragmentStateAdapter
import com.google.android.material.tabs.TabLayoutMediator
import com.ncl.launcher.R
import com.ncl.launcher.auth.AccountStore
import com.ncl.launcher.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val titles = listOf("启动", "版本", "下载", "服务器", "穿透", "设置")
        binding.pager.adapter = PagerAdapter(this)
        TabLayoutMediator(binding.tabs, binding.pager) { tab, pos ->
            tab.text = titles[pos]
        }.attach()
    }

    override fun onResume() {
        super.onResume()
        val acc = AccountStore.active()
        binding.tvAccount.text = "${acc.name} · ${acc.displayType}"
    }

    class PagerAdapter(a: FragmentActivity) : FragmentStateAdapter(a) {
        override fun getItemCount(): Int = 6
        override fun createFragment(position: Int): Fragment = when (position) {
            0 -> HomeFragment()
            1 -> VersionsFragment()
            2 -> DownloadFragment()
            3 -> ServersFragment()
            4 -> TunnelFragment()
            else -> SettingsFragment()
        }
    }
}
