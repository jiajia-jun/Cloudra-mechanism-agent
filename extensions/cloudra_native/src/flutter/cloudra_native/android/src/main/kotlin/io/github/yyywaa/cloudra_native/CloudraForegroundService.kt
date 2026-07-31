package io.github.yyywaa.cloudra_native

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.IBinder

class CloudraForegroundService : Service() {
    companion object {
        const val CHANNEL_ID = "cloudra_device_runtime"
        const val APPROVAL_CHANNEL_ID = "cloudra_device_approvals"
        const val NOTIFICATION_ID = 71231
        const val ACTION_START = "io.github.yyywaa.cloudra_native.START"
        const val ACTION_STOP = "io.github.yyywaa.cloudra_native.STOP"
        const val EXTRA_TITLE = "title"
        const val EXTRA_TEXT = "text"
        const val EXTRA_ROUTE = "route"

        fun ensureChannels(context: Context) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
            val manager =
                context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val runtime = NotificationChannel(
                CHANNEL_ID,
                "Cloudra 设备 Runtime",
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = "显示 Android 设备工具节点的后台在线状态"
                setShowBadge(false)
                enableLights(false)
                enableVibration(false)
            }
            val approvals = NotificationChannel(
                APPROVAL_CHANNEL_ID,
                "Cloudra 本地审批",
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = "提醒用户处理 Android 本地审批"
                enableLights(true)
                lightColor = Color.YELLOW
            }
            manager.createNotificationChannels(listOf(runtime, approvals))
        }

        fun contentIntent(context: Context, route: String?): PendingIntent {
            val launch = context.packageManager
                .getLaunchIntentForPackage(context.packageName)
                ?: Intent()
            launch.action = Intent.ACTION_VIEW
            launch.data = Uri.parse(
                route?.takeIf { it.startsWith("cloudra://") }
                    ?: "cloudra://runtime/status"
            )
            launch.addFlags(
                Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            )
            return PendingIntent.getActivity(
                context,
                (route?.hashCode() ?: NOTIFICATION_ID) and Int.MAX_VALUE,
                launch,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        }

        fun buildNotification(
            context: Context,
            channelId: String,
            title: String,
            text: String,
            route: String?,
            ongoing: Boolean,
        ): Notification {
            ensureChannels(context)
            val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                Notification.Builder(context, channelId)
            } else {
                @Suppress("DEPRECATION")
                Notification.Builder(context)
            }
            val icon = context.applicationInfo.icon.takeIf { it != 0 }
                ?: android.R.drawable.stat_notify_sync
            return builder
                .setSmallIcon(icon)
                .setContentTitle(title.take(120))
                .setContentText(text.take(240))
                .setContentIntent(contentIntent(context, route))
                .setOngoing(ongoing)
                .setOnlyAlertOnce(ongoing)
                .setCategory(
                    if (ongoing) Notification.CATEGORY_SERVICE
                    else Notification.CATEGORY_REMINDER
                )
                .setVisibility(Notification.VISIBILITY_PRIVATE)
                .build()
        }
    }

    override fun onCreate() {
        super.onCreate()
        ensureChannels(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                stopForeground(STOP_FOREGROUND_REMOVE)
            } else {
                @Suppress("DEPRECATION")
                stopForeground(true)
            }
            stopSelf()
            return START_NOT_STICKY
        }
        val preferences = getSharedPreferences("cloudra_native_state", MODE_PRIVATE)
        val title = intent?.getStringExtra(EXTRA_TITLE)
            ?: preferences.getString(EXTRA_TITLE, null)
            ?: "Cloudra 设备 Runtime"
        val text = intent?.getStringExtra(EXTRA_TEXT)
            ?: preferences.getString(EXTRA_TEXT, null)
            ?: "正在连接 Cloudra Server"
        val route = intent?.getStringExtra(EXTRA_ROUTE)
            ?: preferences.getString(EXTRA_ROUTE, "cloudra://runtime/status")
        preferences.edit()
            .putString(EXTRA_TITLE, title)
            .putString(EXTRA_TEXT, text)
            .putString(EXTRA_ROUTE, route)
            .apply()
        startForeground(
            NOTIFICATION_ID,
            buildNotification(
                this,
                CHANNEL_ID,
                title,
                text,
                route,
                ongoing = true,
            ),
        )
        // The Python executor lives in this application process. The foreground
        // service raises its process priority but does not pretend it can
        // recreate the Python event loop after the OS has killed the process.
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        getSharedPreferences("cloudra_native_state", MODE_PRIVATE)
            .edit().putBoolean("runtime_enabled", false).apply()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
