package com.ultron.ultron_app.sms

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
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
 * passes the SMS to the SMS sheet with the phone's name. Runs only online; WorkManager retries with backoff.
 * The worker answers the sheet's own word: ok / duplicate / empty are done; 403 = this phone is blocked.
 */
class SmsUpload(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val ctx = applicationContext
        val from = inputData.getString(KEY_FROM) ?: ""
        val body = inputData.getString(KEY_BODY) ?: ""
        val timestamp = inputData.getLong(KEY_TIME, System.currentTimeMillis())
        val sim = inputData.getString(KEY_SIM) ?: ""
        val worker = SmsPrefs.worker(ctx)
        val name = SmsPrefs.name(ctx)

        if (worker.isBlank() || name.isBlank()) {
            SmsPrefs.addLog(ctx, "Not sent $from: SMS only mode is not set up")
            return@withContext Result.failure()
        }
        if (runAttemptCount >= MAX_ATTEMPTS) {
            SmsPrefs.addLog(ctx, "Gave up $from after $runAttemptCount tries")
            return@withContext Result.failure()
        }

        // a courier SMS's POD, read now: its link expires
        val pod = Pod.fetch(ctx, from, body)
        if (pod != null) SmsPrefs.addLog(ctx, if (pod.error.isEmpty()) "POD read $from" else "POD not read $from: ${pod.error}")

        val json = JSONObject()
            .put("phone", SmsPrefs.phoneId(ctx))
            .put("name", name)
            .put("version", VERSION)
            .put("from", from)
            .put("body", body)
            .put("time", SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ENGLISH).format(Date(timestamp)))
            .put("sim", sim)
            .put("pdf", pod?.pdfBase64 ?: "")
            .put("pdftext", pod?.text ?: "")
            .put("pdferror", pod?.error ?: "")
            .put("html", pod?.htmlBase64 ?: "")

        try {
            val (code, answer) = post("$worker/api/sms", json.toString())
            val word = answer.trim().substringBefore(' ').trimEnd(':')
            when {
                code == 200 && word in listOf("ok", "duplicate", "empty") -> {
                    if (word == "ok") SmsPrefs.countSent(ctx)
                    SmsPrefs.addLog(ctx, "${if (word == "ok") "Sent" else word.replaceFirstChar { it.uppercase() }} $from")
                    Result.success()
                }
                code == 403 -> {
                    SmsPrefs.addLog(ctx, "Not sent $from: this phone is blocked in the control panel")
                    Result.failure()
                }
                code == 400 -> {
                    SmsPrefs.addLog(ctx, "Not sent $from: ${answer.take(60)}")
                    Result.failure()
                }
                else -> {
                    SmsPrefs.addLog(ctx, "Retry $from: HTTP $code ${answer.take(40)}")
                    Result.retry()
                }
            }
        } catch (e: IOException) {
            SmsPrefs.addLog(ctx, "Retry $from: ${e.javaClass.simpleName}")
            Result.retry()
        }
    }

    private fun post(endpoint: String, body: String): Pair<Int, String> {
        val conn = (URL(endpoint).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 20_000
            readTimeout = 120_000          // the sheet also files the OTP and saves the POD
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

    companion object {
        const val VERSION = "ultron-app"
        private const val KEY_FROM = "from"
        private const val KEY_BODY = "body"
        private const val KEY_TIME = "time"
        private const val KEY_SIM = "sim"
        private const val MAX_ATTEMPTS = 25

        fun enqueue(context: Context, from: String, body: String, timestamp: Long, sim: String) {
            val request = OneTimeWorkRequestBuilder<SmsUpload>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .setInputData(workDataOf(KEY_FROM to from, KEY_BODY to body, KEY_TIME to timestamp, KEY_SIM to sim))
                .addTag("sms_upload")
                .build()
            WorkManager.getInstance(context).enqueue(request)
        }
    }
}
