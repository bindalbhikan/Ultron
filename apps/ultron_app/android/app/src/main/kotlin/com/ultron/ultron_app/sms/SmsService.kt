package com.ultron.ultron_app.sms

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.ultron.ultron_app.MainActivity
import com.ultron.ultron_app.R

/**
 * Keeps ULTRON running in the background while "SMS only" mode is on (notification "ULTRON: SMS to sheet
 * on"), so phone makers that kill idle apps (Xiaomi, Oppo, Vivo, Realme) do not stop the SMS. The SMS
 * themselves come through SmsReceiver; this service only holds the process.
 */
class SmsService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!SmsPrefs.isOn(this)) {
            stopSelf()
            return START_NOT_STICKY
        }
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, "SMS to sheet", NotificationManager.IMPORTANCE_LOW)
                    .apply { setShowBadge(false) })
        }
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val note: Notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ultron_icon)
            .setContentTitle("ULTRON: SMS to sheet on")
            .setContentText("${SmsPrefs.name(this)} · ${SmsPrefs.sim(this).ifEmpty { "both SIMs" }}")
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        val type = if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0
        ServiceCompat.startForeground(this, ID, note, type)
        return START_STICKY
    }

    companion object {
        private const val CHANNEL = "sms"
        private const val ID = 7

        fun start(context: Context) = ContextCompat.startForegroundService(context, Intent(context, SmsService::class.java))

        fun stop(context: Context) = context.stopService(Intent(context, SmsService::class.java))
    }
}

/** After a reboot or an app update, SMS only and Agent mode come back on by themselves when they were on. */
class SmsBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action !in listOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED)) return
        if (SmsPrefs.isOn(context)) SmsService.start(context)
        if (com.ultron.ultron_app.agent.AgentPrefs.isOn(context)) com.ultron.ultron_app.agent.AgentService.start(context)
    }
}
