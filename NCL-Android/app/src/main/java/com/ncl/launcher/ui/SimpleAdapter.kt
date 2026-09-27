package com.ncl.launcher.ui

import android.graphics.Bitmap
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.ncl.launcher.R

/** 通用列表项：图标 + 标题 + 副标题 + 尾注 */
data class RowItem(
    val title: String,
    val sub: String = "",
    val tail: String = "",
    val iconPath: String = "",
    val iconBitmap: Bitmap? = null,
    val payload: Any? = null,
    val dim: Boolean = false
)

class SimpleAdapter(
    private val onClick: (RowItem) -> Unit = {},
    private val onLongClick: (RowItem) -> Boolean = { false }
) : ListAdapter<RowItem, SimpleAdapter.Holder>(Diff) {

    var selected: RowItem? = null
        private set

    fun select(item: RowItem?) {
        selected = item
        notifyDataSetChanged()
    }

    object Diff : DiffUtil.ItemCallback<RowItem>() {
        override fun areItemsTheSame(a: RowItem, b: RowItem) =
            a.title == b.title && a.payload == b.payload

        override fun areContentsTheSame(a: RowItem, b: RowItem) = a == b
    }

    inner class Holder(v: View) : RecyclerView.ViewHolder(v) {
        val icon: ImageView = v.findViewById(R.id.ivIcon)
        val title: TextView = v.findViewById(R.id.tvTitle)
        val sub: TextView = v.findViewById(R.id.tvSub)
        val tail: TextView = v.findViewById(R.id.tvTail)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Holder =
        Holder(LayoutInflater.from(parent.context).inflate(R.layout.item_simple, parent, false))

    override fun onBindViewHolder(h: Holder, pos: Int) {
        val item = getItem(pos)
        h.title.text = item.title
        h.sub.text = item.sub
        h.tail.text = item.tail
        h.itemView.alpha = if (item.dim) 0.45f else 1f

        when {
            item.iconBitmap != null -> h.icon.setImageBitmap(item.iconBitmap)
            item.iconPath.isNotBlank() -> {
                val bmp = com.ncl.launcher.mc.Scan.loadIcon(item.iconPath)
                if (bmp != null) h.icon.setImageBitmap(bmp)
                else h.icon.setImageResource(R.drawable.bg_card)
            }
            else -> h.icon.setImageResource(R.drawable.bg_card)
        }

        h.itemView.isSelected = selected?.payload == item.payload && selected?.title == item.title
        h.itemView.setOnClickListener { select(item); onClick(item) }
        h.itemView.setOnLongClickListener { onLongClick(item) }
    }
}
