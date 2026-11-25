package com.ultron.ultron_app.sms

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * Sends one SMS (with the POD of a courier SMS) to the worker's POST /api/sms, which records the phone and
 * passes the SMS to the SMS sheet with the phone's name. It waits while the phone is offline (a network
 * constraint), survives reboots, and on any network or server trouble tries again with growing pauses
 * (WorkManager caps them at 5 hours) - never giving up, so no SMS is lost to a long outage. It stops only on
 * the worker's own refusal: 403 (this phone is blocked) or 400 (a bad request). ok / duplicate / empty are done.
 *
 * Expedited (25 Nov 2026): an OTP is sent the moment it arrives, also while the phone sleeps (Doze), instead of
 * waiting for Android's next window for background work (minutes to hours: the OTP had expired by then). It costs
 * no more battery: one short network call per SMS, and nothing runs between SMS. Out of expedited quota it runs as
 * ordinary work.
 */
class SmsUpload(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val ctx = applicationContext
        val from = inputData.getString(KEY_FROM) ?: ""
        val body = inputData.getString(KEY_BODY) ?: ""
        val timestamp = inputData.getLong(KEY_TIME, System.currentTimeMillis())
        val sim = inputData.getString(KEY_SIM) ?: ""
        val rework = inputData.getBoolean(KEY_REWORK, false)
        val worker = SmsPrefs.worker(ctx)
        val name = SmsPrefs.name(ctx)

        if (worker.isBlank() || name.isBlank()) {
            SmsPrefs.addLog(ctx, "Not sent $from: SMS only mode is not set up")
            return@withContext Result.failure()
        }

        // a courier SMS's POD, read now: its link expires
        val pod = Pod.fetch(ctx, from, body)
        if (pod != null) SmsPrefs.addLog(ctx, if (pod.error.isEmpty()) "POD read $from" else "POD not read $from: ${pod.error}")
        // the SMS itself is on the sheet already (sent at once): without a POD there is nothing to add
        if (rework && (pod == null || pod.error.isNotEmpty())) return@withContext Result.success()

        val attempt = (if (rework) "POD, try " else "try ") + (runAttemptCount + 1)
        when (send(ctx, from, body, timestamp, sim, pod, attempt, 20_000, 120_000, rework)) {
            Outcome.DONE -> Result.success()
            Outcome.REFUSED -> Result.failure()
            Outcome.AGAIN -> Result.retry()
        }
    }

    /** Android 11 and older run expedited work as a short foreground job, which needs a notification. */
    override suspend fun getForegroundInfo(): ForegroundInfo {
        val ctx = applicationContext
        val manager = ctx.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, "Sending SMS", NotificationManager.IMPORTANCE_MIN).apply { setShowBadge(false) })
        }
        val note = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(com.ultron.ultron_app.R.drawable.ultron_icon)
            .setContentTitle("ULTRON: sending an SMS to the sheet")
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .build()
        return ForegroundInfo(NOTE_ID, note)
    }

    enum class Outcome { DONE, REFUSED, AGAIN }

    companion object {
        const val VERSION = "ultron-app"
        private const val CHANNEL = "sms_send"
        private const val NOTE_ID = 8
        private const val KEY_FROM = "from"
        private const val KEY_BODY = "body"
        private const val KEY_TIME = "time"
        private const val KEY_SIM = "sim"
        private const val KEY_REWORK = "rework"

        /**
         * One SMS to the worker's POST /api/sms. DONE: on the sheet (ok / duplicate / empty); REFUSED: the
         * worker's own no (403 blocked, 400 bad request), never tried again; AGAIN: no internet, a timeout or a
         * server error - queued (enqueue) and tried again until it goes.
         */
        fun send(ctx: Context, from: String, body: String, timestamp: Long, sim: String, pod: Pod.Result?,
                 attempt: String, connectMs: Int, readMs: Int, rework: Boolean = false): Outcome {
            val worker = SmsPrefs.worker(ctx)
            val json = JSONObject()
                .put("phone", SmsPrefs.phoneId(ctx))
                .put("name", SmsPrefs.name(ctx))
                .put("version", VERSION)
                .put("from", from)
                .put("body", body)
                .put("time", SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ENGLISH).format(Date(timestamp)))
                .put("sim", sim)
                .put("pdf", pod?.pdfBase64 ?: "")
                .put("pdftext", pod?.text ?: "")
                .put("pdferror", pod?.error ?: "")
                .put("html", pod?.htmlBase64 ?: "")
                .put("rework", if (rework) "1" else "")    // the same SMS again, now with its POD
            return try {
                val (code, answer) = post("$worker/api/sms", json.toString(), connectMs, readMs)
                val word = answer.trim().substringBefore(' ').trimEnd(':')
                when {
                    code == 200 && word in listOf("ok", "duplicate", "empty") -> {
                        if (word == "ok") SmsPrefs.countSent(ctx)
                        SmsPrefs.addLog(ctx, "${if (word == "ok") "Sent" else word.replaceFirstChar { it.uppercase() }} $from ($attempt)")
                        Outcome.DONE
                    }
                    code == 403 -> {
                        SmsPrefs.addLog(ctx, "Not sent $from: this phone is blocked in the control panel")
                        Outcome.REFUSED
                    }
                    code == 400 -> {
                        SmsPrefs.addLog(ctx, "Not sent $from: ${answer.take(60)}")
                        Outcome.REFUSED
                    }
                    else -> {
                        SmsPrefs.addLog(ctx, "Retry $from ($attempt): HTTP $code ${answer.take(40)}")
                        Outcome.AGAIN
                    }
                }
            } catch (e: IOException) {
                SmsPrefs.addLog(ctx, "Retry $from ($attempt): no internet or worker (${e.javaClass.simpleName})")
                Outcome.AGAIN
            }
        }

        private fun post(endpoint: String, body: String, connectMs: Int, readMs: Int): Pair<Int, String> {
            val conn = (URL(endpoint).openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = connectMs
                readTimeout = readMs            // the sheet also files the OTP (and saves a courier SMS's POD)
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=UTF-8")
            }
            try {
                conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                val code = conn.responseCode
                val stream = if (code >= 400) conn.errorStream else conn.inputStream
                return code to (stream?.bufferedReader()?.use { it.readText() } ?: "")
            } finally {
                conn.disconnect()
            }
        }

        /** Queued: sent as soon as possible and tried until it goes. rework: the SMS is on the sheet already
         *  (sent at once); this reads its POD and sends the SMS again with it (the sheet then files the POD and
         *  names the portals of its OTP). */
        fun enqueue(context: Context, from: String, body: String, timestamp: Long, sim: String, rework: Boolean = false) {
            val request = OneTimeWorkRequestBuilder<SmsUpload>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .setInputData(workDataOf(KEY_FROM to from, KEY_BODY to body, KEY_TIME to timestamp, KEY_SIM to sim,
                    KEY_REWORK to rework))
                .addTag("sms_upload")
                .build()
            WorkManager.getInstance(context).enqueue(request)
        }
    }
}
