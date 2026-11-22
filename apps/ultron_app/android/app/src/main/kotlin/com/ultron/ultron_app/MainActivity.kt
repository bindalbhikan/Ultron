package com.ultron.ultron_app

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.core.content.ContextCompat
import com.ultron.ultron_app.agent.AgentPrefs
import com.ultron.ultron_app.agent.AgentService
import com.ultron.ultron_app.sms.SmsImport
import com.ultron.ultron_app.sms.SmsPrefs
import com.ultron.ultron_app.sms.SmsService
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import kotlin.concurrent.thread

/**
 * The Flutter UI plus the "ultron/sms" channel of "SMS only" mode (lib/src/data/sms_bridge.dart):
 * status, start (name, SIM, worker), stop, permissions, battery, sending old SMS.
 */
class MainActivity : FlutterActivity() {
    private var pendingPermissions: MethodChannel.Result? = null

    private val needed: Array<String>
        get() = buildList {
            add(Manifest.permission.RECEIVE_SMS)
            add(Manifest.permission.READ_SMS)
            if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
        }.toTypedArray()

    private fun granted(p: String) = ContextCompat.checkSelfPermission(this, p) == PackageManager.PERMISSION_GRANTED

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "ultron/agent").setMethodCallHandler { call, result ->
            when (call.method) {
                "status" -> result.success(agentStatus())
                "start" -> {
                    val worker = call.argument<String>("worker").orEmpty().trim()
                    val token = call.argument<String>("token").orEmpty().trim()
                    if (!worker.startsWith("https://") || token.length < 40) {
                        result.error("bad", "a worker and this phone's token", null)
                    } else {
                        AgentPrefs.turnOn(this, worker, token)
                        AgentService.start(this)
                        result.success(agentStatus())
                    }
                }
                "stop" -> {
                    AgentPrefs.turnOff(this)
                    AgentService.stop(this)
                    result.success(agentStatus())
                }
                else -> result.notImplemented()
            }
        }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "ultron/sms").setMethodCallHandler { call, result ->
            when (call.method) {
                "status" -> result.success(status())
                "start" -> {
                    val name = call.argument<String>("name").orEmpty().trim()
                    val worker = call.argument<String>("worker").orEmpty().trim()
                    val sim = call.argument<String>("sim").orEmpty()
                    if (name.length !in 2..40 || !worker.startsWith("https://") || sim !in listOf("", "SIM 1", "SIM 2")) {
                        result.error("bad", "a name of 2 to 40 characters, a SIM choice", null)
                    } else if (!granted(Manifest.permission.RECEIVE_SMS)) {
                        result.error("permission", "allow SMS first", null)
                    } else {
                        SmsPrefs.turnOn(this, name, sim, worker)
                        SmsPrefs.addLog(this, "SMS only on: $name, ${sim.ifEmpty { "both SIMs" }}")
                        SmsService.start(this)
                        result.success(status())
                    }
                }
                "stop" -> {
                    SmsPrefs.turnOff(this)
                    SmsService.stop(this)
                    SmsPrefs.addLog(this, "SMS only off")
                    result.success(status())
                }
                "permissions" -> {
                    val missing = needed.filterNot(::granted)
                    if (missing.isEmpty()) result.success(status())
                    else {
                        pendingPermissions?.success(status())
                        pendingPermissions = result
                        requestPermissions(missing.toTypedArray(), REQUEST)
                    }
                }
                "battery" -> {
                    askBattery()
                    result.success(status())
                }
                "sendOld" -> {
                    val days = (call.argument<Int>("days") ?: 60).coerceIn(1, 365)
                    if (!SmsPrefs.isOn(this) || !granted(Manifest.permission.READ_SMS)) {
                        result.error("off", "turn SMS only on and allow SMS first", null)
                    } else thread {
                        val n = SmsImport.run(this, days)
                        runOnUiThread { result.success(n) }
                    }
                }
                else -> result.notImplemented()
            }
        }
    }

    /** Agent mode (lib/src/data/agent_bridge.dart): the token comes from the app API, never typed. */
    private fun agentStatus(): Map<String, Any> = mapOf(
        "on" to AgentPrefs.isOn(this),
        "device" to "${Build.MANUFACTURER} ${Build.MODEL}",
        "lastPoll" to AgentPrefs.lastPoll(this),
        "lastJob" to AgentPrefs.lastJob(this),
        "log" to AgentPrefs.log(this),
    )

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST) {
            pendingPermissions?.success(status())
            pendingPermissions = null
        }
    }

    @SuppressLint("BatteryLife")    // sideloaded business app: the owner chooses to keep it awake
    private fun askBattery() {
        val power = getSystemService(PowerManager::class.java)
        if (power.isIgnoringBatteryOptimizations(packageName)) return
        startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
    }

    private fun status(): Map<String, Any> = mapOf(
        "on" to SmsPrefs.isOn(this),
        "name" to SmsPrefs.name(this),
        "sim" to SmsPrefs.sim(this),
        "phoneId" to SmsPrefs.phoneId(this),
        "sent" to SmsPrefs.sent(this),
        "lastSent" to SmsPrefs.lastSent(this),
        "log" to SmsPrefs.log(this),
        "smsAllowed" to (granted(Manifest.permission.RECEIVE_SMS) && granted(Manifest.permission.READ_SMS)),
        "notificationsAllowed" to (Build.VERSION.SDK_INT < 33 || granted(Manifest.permission.POST_NOTIFICATIONS)),
        "batteryFree" to getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName),
    )

    companion object {
        private const val REQUEST = 41
    }
}
