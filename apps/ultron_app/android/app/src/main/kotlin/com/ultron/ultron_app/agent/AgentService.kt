package com.ultron.ultron_app.agent

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.ServiceInfo
import android.os.BatteryManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.ultron.ultron_app.MainActivity
import com.ultron.ultron_app.R
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Agent mode settings: the worker, this phone's own token (from the app API), the last check-in and job, a log. */
object AgentPrefs {
    private fun sp(c: Context): SharedPreferences = c.applicationContext.getSharedPreferences("ultron_agent", Context.MODE_PRIVATE)
    fun isOn(c: Context) = sp(c).getBoolean("on", false)
    fun worker(c: Context) = (sp(c).getString("worker", "") ?: "").trimEnd('/')
    fun token(c: Context) = sp(c).getString("token", "") ?: ""
    fun turnOn(c: Context, worker: String, token: String) =
        sp(c).edit().putBoolean("on", true).putString("worker", worker).putString("token", token).apply()
    /** Off, and the token forgotten: turning on again asks the app API for a new one. */
    fun turnOff(c: Context) = sp(c).edit().putBoolean("on", false).remove("token").apply()
    fun markPoll(c: Context) = sp(c).edit().putLong("last_poll", System.currentTimeMillis()).apply()
    fun lastPoll(c: Context) = sp(c).getLong("last_poll", 0)
    fun setLastJob(c: Context, t: String) = sp(c).edit().putString("last_job", t).apply()
    fun lastJob(c: Context) = sp(c).getString("last_job", "") ?: ""

    @Synchronized
    fun addLog(c: Context, line: String) {
        val time = SimpleDateFormat("dd-MMM HH:mm:ss", Locale.ENGLISH).format(Date())
        val lines = (listOf("$time  $line") + (sp(c).getString("log", "") ?: "").lines().filter { it.isNotBlank() }).take(60)
        sp(c).edit().putString("log", lines.joinToString("\n")).apply()
    }
    fun log(c: Context) = sp(c).getString("log", "") ?: ""
}

/**
 * Agent mode (ported from Ultron Phone): a foreground service that asks the Telegram worker for work every
 * minute (POST /api/phone/next with this phone's own token) and does it on the phone's own line. Jobs:
 * "myntra_style" - style ids looked up on www.myntra.com (MyntraLookup), answered a part at a time
 * (POST /api/phone/result). The worker refuses the token once an administrator revokes it.
 */
class AgentService : Service() {

    @Volatile private var running = false
    private var thread: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP || !AgentPrefs.isOn(this)) {
            running = false
            stopSelf()
            return START_NOT_STICKY
        }
        foreground("Waiting for work")
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
        AgentPrefs.addLog(this, "Agent on")
        while (running && AgentPrefs.isOn(this)) {
            try {
                val job = call("next", null, JSONObject()
                    .put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
                    .put("battery", battery())
                    .put("version", "ultron-app").toString())
                AgentPrefs.markPoll(this)
                if (job.optString("id").isNotEmpty()) work(job)
            } catch (e: Refused) {
                AgentPrefs.addLog(this, "Agent: this phone's token was revoked; turn Agent mode on again in the app")
                AgentPrefs.turnOff(this)
                break
            } catch (e: Exception) {
                AgentPrefs.addLog(this, "Agent: worker not reached (${e.javaClass.simpleName})")
            }
            try { Thread.sleep(POLL_MS) } catch (_: InterruptedException) { break }
        }
        AgentPrefs.addLog(this, "Agent off")
        stopSelf()
    }

    private fun work(job: JSONObject) {
        val id = job.getString("id")
        val kind = job.optString("kind")
        val items = job.optJSONArray("items") ?: JSONArray()
        if (kind != "myntra_style") {
            AgentPrefs.addLog(this, "Job $id: kind $kind not known to this app version")
            return
        }
        val wake = (getSystemService(Context.POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ultron:agentjob").apply { acquire(2 * 60 * 60 * 1000L) }
        try {
            val ids = (0 until items.length()).map { items.getLong(it) }
            AgentPrefs.addLog(this, "Job $id: ${ids.size} Myntra styles")
            foreground("Myntra: 0 of ${ids.size} styles")
            val started = System.currentTimeMillis()
            val answers = MyntraLookup(onProgress = { n, total -> foreground("Myntra: $n of $total styles") }).run(ids)
            val parts = answers.keys.toList().chunked(PART)
            parts.forEachIndexed { i, chunk ->
                val body = JSONObject()
                chunk.forEach { k -> body.put(k, answers[k]) }
                send("result", "job=$id&part=$i" + if (i == parts.size - 1) "&last=1" else "", body.toString())
            }
            val minutes = (System.currentTimeMillis() - started) / 60000.0
            val found = answers.values.count { it is JSONObject }
            val text = "Job $id done: $found of ${ids.size} styles answered, %.1f min".format(minutes)
            AgentPrefs.addLog(this, text)
            AgentPrefs.setLastJob(this, text)
        } catch (e: Exception) {
            AgentPrefs.addLog(this, "Job $id failed: ${e.javaClass.simpleName} ${e.message?.take(80)}")
        } finally {
            if (wake.isHeld) wake.release()
            foreground("Waiting for work")
        }
    }

    /** call() until it goes through: the internet can be off for a while, and the answers of a job that took
     *  hours must not be lost. Pauses grow to 10 minutes; after 6 hours the job is given up (the worker keeps
     *  results a day and hands an unanswered job to a phone again). A revoked token stops at once. */
    private fun send(action: String, query: String, body: String) {
        val started = System.currentTimeMillis()
        var attempt = 0
        while (true) {
            try {
                call(action, query, body)
                return
            } catch (e: Exception) {
                attempt++
                if (e is Refused || System.currentTimeMillis() - started > SEND_FOR_MS) throw e
                AgentPrefs.addLog(this, "Agent: sending answers failed (${e.javaClass.simpleName}), try $attempt")
                Thread.sleep(minOf(30_000L * attempt, 600_000L))
            }
        }
    }

    private class Refused : Exception("token refused")

    /** POST to the worker's /api/phone/<action> with this phone's token; the answer as JSON. */
    private fun call(action: String, query: String?, body: String): JSONObject {
        val worker = AgentPrefs.worker(this)
        val token = AgentPrefs.token(this)
        if (worker.isBlank() || token.isBlank()) throw Refused()
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
            if (code == 403) throw Refused()
            if (code >= 400) throw IllegalStateException("HTTP $code $text")
            return if (text.isBlank()) JSONObject() else JSONObject(text)
        } finally {
            c.disconnect()
        }
    }

    private fun battery(): Int =
        (getSystemService(Context.BATTERY_SERVICE) as BatteryManager).getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)

    private fun foreground(text: String) {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL, "Agent mode", NotificationManager.IMPORTANCE_LOW))
        }
        val open = PendingIntent.getActivity(this, 1, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val note = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ultron_icon)
            .setContentTitle("ULTRON: agent on")
            .setContentText(text)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        val type = if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0
        ServiceCompat.startForeground(this, NOTE_ID, note, type)
    }

    companion object {
        private const val CHANNEL = "agent"
        private const val NOTE_ID = 8
        private const val POLL_MS = 60_000L
        private const val PART = 300
        private const val SEND_FOR_MS = 6 * 60 * 60 * 1000L
        const val ACTION_STOP = "stop"

        fun start(context: Context) = ContextCompat.startForegroundService(context, Intent(context, AgentService::class.java))

        fun stop(context: Context) {
            context.startService(Intent(context, AgentService::class.java).setAction(ACTION_STOP))
        }
    }
}
