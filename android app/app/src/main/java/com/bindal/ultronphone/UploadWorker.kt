package com.bindal.ultronphone

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
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * Posts one SMS to the Apps Script web app.
 * Runs only when the network is available; WorkManager retries with backoff on failure.
 */
class UploadWorker(context: Context, params: WorkerParameters) :
    CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val ctx = applicationContext
        val url = Prefs.getUrl(ctx)
        val secret = Prefs.getSecret(ctx)
        val from = inputData.getString(KEY_FROM) ?: ""
        val body = inputData.getString(KEY_BODY) ?: ""
        val timestamp = inputData.getLong(KEY_TIME, System.currentTimeMillis())
        val sim = inputData.getString(KEY_SIM) ?: ""

        if (url.isBlank() || secret.isBlank()) {
            Prefs.addLog(ctx, "SMS not sent $from: sheet URL or secret key not set")
            return@withContext Result.failure()
        }

        if (runAttemptCount >= MAX_ATTEMPTS) {
            Prefs.addLog(ctx, "GAVE UP $from after $runAttemptCount attempts")
            return@withContext Result.failure()
        }

        val deviceTime = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ENGLISH)
            .format(Date(timestamp))

        val form = mapOf(
            "key" to secret,
            "from" to from,
            "body" to body,
            "time" to deviceTime,
            "sim" to sim
        ).entries.joinToString("&") { (k, v) ->
            "${enc(k)}=${enc(v)}"
        }

        try {
            val (code, response) = post(url, form)
            val text = response.trim()
            when {
                text.startsWith("unauthorized") -> {
                    Prefs.addLog(ctx, "FAILED $from: wrong secret key")
                    Result.failure()
                }
                text.startsWith("error") -> {
                    Prefs.addLog(ctx, "RETRY $from: script $text")
                    Result.retry()
                }
                code in 200..399 -> {
                    val label = if (text.startsWith("duplicate")) "DUPLICATE" else "SENT"
                    Prefs.addLog(ctx, "SMS $label $from")
                    Result.success()
                }
                else -> {
                    Prefs.addLog(ctx, "RETRY $from: HTTP $code")
                    Result.retry()
                }
            }
        } catch (e: IOException) {
            Prefs.addLog(ctx, "RETRY $from: ${e.javaClass.simpleName}")
            Result.retry()
        }
    }

    private fun post(endpoint: String, form: String): Pair<Int, String> {
        val conn = (URL(endpoint).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            instanceFollowRedirects = true
            connectTimeout = 20_000
            readTimeout = 30_000
            doOutput = true
            setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
        }
        try {
            conn.outputStream.use { it.write(form.toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val stream = if (code >= 400) conn.errorStream else conn.inputStream
            val response = stream?.bufferedReader()?.use { it.readText() } ?: ""
            return code to response
        } finally {
            conn.disconnect()
        }
    }

    private fun enc(value: String): String = URLEncoder.encode(value, "UTF-8")

    companion object {
        private const val KEY_FROM = "from"
        private const val KEY_BODY = "body"
        private const val KEY_TIME = "time"
        private const val KEY_SIM = "sim"
        private const val MAX_ATTEMPTS = 25

        fun enqueue(context: Context, from: String, body: String, timestamp: Long, sim: String = "") {
            val request = OneTimeWorkRequestBuilder<UploadWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .setInputData(
                    workDataOf(
                        KEY_FROM to from,
                        KEY_BODY to body,
                        KEY_TIME to timestamp,
                        KEY_SIM to sim
                    )
                )
                .addTag("sms_upload")
                .build()

            WorkManager.getInstance(context).enqueue(request)
        }
    }
}
