package com.ultron.ultron_app

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import kotlin.concurrent.thread

/** Stream an update into private cache, verify it, then let Android confirm installation. */
object AppUpdates {
    private var busy = false

    fun install(activity: MainActivity, call: MethodCall, result: MethodChannel.Result) {
        if (busy) {
            result.error("busy", "An update is already downloading.", null)
            return
        }
        if (Build.VERSION.SDK_INT >= 26 && !activity.packageManager.canRequestPackageInstalls()) {
            activity.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${activity.packageName}")))
            result.success("permission")
            return
        }
        val address = call.argument<String>("url").orEmpty()
        val expected = call.argument<String>("sha256").orEmpty()
        val size = call.argument<Number>("size")?.toLong() ?: 0L
        val build = call.argument<Number>("build")?.toLong() ?: 0L
        val uri = Uri.parse(address)
        if (uri.scheme != "https" || !uri.userInfo.isNullOrEmpty() ||
            !uri.path.orEmpty().startsWith("/api/releases/files/releases/") ||
            !Regex("[a-f0-9]{64}").matches(expected) || size !in 1L..2_000_000_000L) {
            result.error("invalid", "The update details are invalid.", null)
            return
        }
        busy = true
        thread(name = "ultron-update") {
            val folder = File(activity.cacheDir, "updates").apply { mkdirs() }
            val file = File(folder, "ULTRON.apk")
            var connection: HttpURLConnection? = null
            try {
                connection = URL(address).openConnection() as HttpURLConnection
                connection.instanceFollowRedirects = false
                connection.connectTimeout = 30_000
                connection.readTimeout = 60_000
                check(connection.responseCode == 200) { "The update download was refused." }
                val hash = MessageDigest.getInstance("SHA-256")
                var received = 0L
                connection.inputStream.use { input ->
                    file.outputStream().use { output ->
                        val buffer = ByteArray(65536)
                        while (true) {
                            val n = input.read(buffer)
                            if (n == -1) break
                            received += n
                            check(received <= size) { "The update size did not match." }
                            hash.update(buffer, 0, n)
                            output.write(buffer, 0, n)
                        }
                    }
                }
                check(received == size && hash.digest().joinToString("") { "%02x".format(it) } == expected) {
                    "The update verification failed. Please download it again."
                }
                @Suppress("DEPRECATION")
                val archive = activity.packageManager.getPackageArchiveInfo(file.path, 0)
                @Suppress("DEPRECATION")
                val installed = activity.packageManager.getPackageInfo(activity.packageName, 0)
                @Suppress("DEPRECATION")
                val archiveBuild = if (Build.VERSION.SDK_INT >= 28) archive?.longVersionCode else archive?.versionCode?.toLong()
                @Suppress("DEPRECATION")
                val installedBuild = if (Build.VERSION.SDK_INT >= 28) installed.longVersionCode else installed.versionCode.toLong()
                check(archive?.packageName == activity.packageName && archiveBuild == build && build > installedBuild) {
                    "This update does not match the installed app or is not newer."
                }
                activity.runOnUiThread {
                    try {
                        val content = FileProvider.getUriForFile(activity, "${activity.packageName}.updates", file)
                        activity.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(content, "application/vnd.android.package-archive")
                            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                        result.success("installer")
                    } catch (_: Exception) {
                        result.error("install", "Android could not open the update installer.", null)
                    } finally { busy = false }
                }
            } catch (_: Exception) {
                file.delete()
                activity.runOnUiThread {
                    busy = false
                    result.error("download", "The update could not be downloaded or verified. Try again.", null)
                }
            } finally { connection?.disconnect() }
        }
    }
}
