package com.bindal.ultronphone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.BatteryManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Agent mode: a foreground service (its notification keeps Android from stopping it) that asks the
 * Telegram worker for work every minute (POST /api/phone/next) and does it on the phone's own line.
 * Jobs: "myntra_style" - style ids looked up on www.myntra.com (MyntraLookup), answered back a part
 * at a time (POST /api/phone/result). Started from the app, and again after a reboot (BootReceiver).
 */
class AgentService : Service() {

    @Volatile private var running = false
    private var thread: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP || !Prefs.agentOn(this)) {
            stopSelf()
            return START_NOT_STICKY
        }
        startForegroundNow("Waiting for work")
        if (!running) {
            running = true
            thread = Thread({ loop() }, "ultron-agent").apply { start() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        thread?.interrupt()
        super.onDestroy()
    }

    private fun loop() {
        Prefs.addLog(this, "Agent on")
        while (running && Prefs.agentOn(this)) {
            try {
                val job = call("next", null, JSONObject()
                    .put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
                    .put("battery", battery())
                    .put("version", BuildConfig.VERSION_NAME).toString())
                Prefs.markPoll(this)
                if (job.optString("id").isNotEmpty()) work(job)
            } catch (e: Exception) {
                Prefs.addLog(this, "Agent: worker not reached (${e.javaClass.simpleName})")
            }
            try { Thread.sleep(POLL_MS) } catch (_: InterruptedException) { break }
        }
        Prefs.addLog(this, "Agent off")
    }

    private fun work(job: JSONObject) {
        val id = job.getString("id")
        val kind = job.optString("kind")
        val items = job.optJSONArray("items") ?: JSONArray()
        if (kind != "myntra_style") {
            Prefs.addLog(this, "Job $id: kind $kind not known to this app version")
            return
        }
        val wake = (getSystemService(Context.POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ultronphone:job").apply { acquire(2 * 60 * 60 * 1000L) }
        try {
            val ids = (0 until items.length()).map { items.getLong(it) }
            Prefs.addLog(this, "Job $id: ${ids.size} Myntra styles")
            startForegroundNow("Myntra: 0 of ${ids.size} styles")
            val started = System.currentTimeMillis()
            val answers = MyntraLookup(onProgress = { n, total -> startForegroundNow("Myntra: $n of $total styles") }).run(ids)
            val keys = answers.keys.toList()
            val parts = keys.chunked(PART)
            parts.forEachIndexed { i, chunk ->
                val body = JSONObject()
                chunk.forEach { k -> body.put(k, answers[k]) }
                call("result", "job=$id&part=$i" + if (i == parts.size - 1) "&last=1" else "", body.toString())
            }
            val minutes = (System.currentTimeMillis() - started) / 60000.0
            val found = answers.values.count { it is JSONObject }
            val text = "Job $id done: $found of ${ids.size} styles answered, %.1f min".format(minutes)
            Prefs.addLog(this, text)
            Prefs.setLastJob(this, text)
        } catch (e: Exception) {
            Prefs.addLog(this, "Job $id failed: ${e.javaClass.simpleName} ${e.message?.take(80)}")
        } finally {
            if (wake.isHeld) wake.release()
            startForegroundNow("Waiting for work")
        }
    }

    /** POST to the worker's /api/phone/<action> with the token; the answer as JSON. */
    private fun call(action: String, query: String?, body: String): JSONObject {
        val worker = Prefs.getWorker(this)
        val token = Prefs.getToken(this)
        if (worker.isBlank() || token.isBlank()) throw IllegalStateException("worker URL or token not set")
        val url = "$worker/api/phone/$action" + (query?.let { "?$it" } ?: "")
        val c = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 20_000
            readTimeout = 60_000
            doOutput = true
            setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("Content-Type", "application/json")
        }
        try {
            c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val code = c.responseCode
            val text = (if (code >= 400) c.errorStream else c.inputStream)?.bufferedReader()?.use { it.readText() } ?: ""
            if (code == 403) throw IllegalStateException("token refused")
            if (code >= 400) throw IllegalStateException("HTTP $code $text")
            return if (text.isBlank()) JSONObject() else JSONObject(text)
        } finally {
            c.disconnect()
        }
    }

    private fun battery(): Int =
        (getSystemService(Context.BATTERY_SERVICE) as BatteryManager).getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)

    private fun startForegroundNow(text: String) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "Agent mode", NotificationManager.IMPORTANCE_LOW))
        }
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, CHANNEL) else Notification.Builder(this)
        val n = builder.setContentTitle("Ultron Phone: agent on")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_stat_ultron)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTE_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTE_ID, n)
        }
    }

    companion object {
        private const val CHANNEL = "agent"
        private const val NOTE_ID = 7
        private const val POLL_MS = 60_000L
        private const val PART = 300
        const val ACTION_STOP = "stop"

        fun start(context: Context) {
            val i = Intent(context, AgentService::class.java)
            if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(i) else context.startService(i)
        }

        fun stop(context: Context) {
            context.startService(Intent(context, AgentService::class.java).setAction(ACTION_STOP))
        }
    }
}
