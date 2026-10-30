package com.bindal.ultronphone

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {

    private lateinit var workerInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var urlInput: EditText
    private lateinit var secretInput: EditText
    private lateinit var filterInput: EditText
    private lateinit var agentSwitch: Switch
    private lateinit var agentDot: View
    private lateinit var agentText: TextView
    private lateinit var statusText: TextView
    private lateinit var logText: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        workerInput = findViewById(R.id.workerInput)
        tokenInput = findViewById(R.id.tokenInput)
        urlInput = findViewById(R.id.urlInput)
        secretInput = findViewById(R.id.secretInput)
        filterInput = findViewById(R.id.filterInput)
        agentSwitch = findViewById(R.id.agentSwitch)
        agentDot = findViewById(R.id.agentDot)
        agentText = findViewById(R.id.agentText)
        statusText = findViewById(R.id.statusText)
        logText = findViewById(R.id.logText)
        findViewById<TextView>(R.id.versionText).text = "v${BuildConfig.VERSION_NAME}"

        workerInput.setText(Prefs.getWorker(this))
        tokenInput.setText(Prefs.getToken(this))
        urlInput.setText(Prefs.getUrl(this))
        secretInput.setText(Prefs.getSecret(this))
        filterInput.setText(Prefs.getFilter(this))
        agentSwitch.isChecked = Prefs.agentOn(this)

        agentSwitch.setOnCheckedChangeListener { _, on -> setAgent(on) }
        findViewById<Button>(R.id.saveButton).setOnClickListener { save() }
        findViewById<Button>(R.id.permissionButton).setOnClickListener { requestSms() }
        findViewById<Button>(R.id.testButton).setOnClickListener { sendTest() }
        findViewById<Button>(R.id.batteryButton).setOnClickListener { askBattery() }
        findViewById<Button>(R.id.appSettingsButton).setOnClickListener { openAppSettings() }
        findViewById<Button>(R.id.refreshButton).setOnClickListener { refresh() }

        if (Prefs.agentOn(this)) AgentService.start(this)     // in case Android stopped it
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    private fun save() {
        val worker = workerInput.text.toString().trim()
        val url = urlInput.text.toString().trim()
        val secret = secretInput.text.toString().trim()
        if (worker.isNotEmpty() && !worker.startsWith("https://")) return toast("Worker URL should start with https://")
        if (url.isNotEmpty() && (!url.startsWith("https://script.google.com/") || !url.endsWith("/exec"))) {
            return toast("Sheet URL should start with https://script.google.com/ and end with /exec")
        }
        if (url.isNotEmpty() && secret.length < 8) return toast("Secret key should be at least 8 characters")
        Prefs.save(this, url, secret, filterInput.text.toString(), worker, tokenInput.text.toString())
        toast("Saved")
        refresh()
    }

    private fun setAgent(on: Boolean) {
        if (on && (Prefs.getWorker(this).isBlank() || Prefs.getToken(this).isBlank())) {
            agentSwitch.isChecked = false
            return toast("Save the worker URL and token first")
        }
        if (on && Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTE)
        }
        Prefs.setAgentOn(this, on)
        if (on) AgentService.start(this) else AgentService.stop(this)
        refresh()
    }

    private fun sendTest() {
        if (Prefs.getUrl(this).isBlank()) return toast("Save the sheet URL and secret key first")
        UploadWorker.enqueue(this, "TEST", "Test message from Ultron Phone", System.currentTimeMillis(), "SIM ?")
        Prefs.addLog(this, "SMS queued TEST")
        toast("Test queued. Tap Refresh in a few seconds.")
        refresh()
    }

    private fun requestSms() {
        if (hasSms()) return toast("SMS permission already granted")
        requestPermissions(arrayOf(Manifest.permission.RECEIVE_SMS), REQ_SMS)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_SMS && !hasSms()) toast("Not allowed. App settings > Permissions > SMS (Android 13+: first ⋮ > Allow restricted settings).")
        refresh()
    }

    private fun askBattery() {
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        if (pm.isIgnoringBatteryOptimizations(packageName)) return toast("Battery optimisation is already off for this app")
        startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
    }

    private fun openAppSettings() {
        startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).setData(Uri.fromParts("package", packageName, null)))
    }

    private fun hasSms() = checkSelfPermission(Manifest.permission.RECEIVE_SMS) == PackageManager.PERMISSION_GRANTED

    private fun refresh() {
        val on = Prefs.agentOn(this)
        val last = Prefs.lastPoll(this)
        val ago = if (last == 0L) -1 else ((System.currentTimeMillis() - last) / 60000).toInt()
        val alive = on && ago in 0..3
        agentDot.backgroundTintList = ColorStateList.valueOf(
            if (alive) getColor(R.color.accent) else if (on) 0xFFE0A21B.toInt() else 0xFF9AA3B2.toInt())
        agentText.text = when {
            !on -> "Off. Turn on to let the bots use this phone for Myntra lookups when the office PC is off."
            ago < 0 -> "On, has not reached the worker yet."
            alive -> "On. Last check-in ${if (ago == 0) "just now" else "$ago min ago"}."
            else -> "On, but the last check-in was $ago min ago (no internet, or Android stopped the app)."
        } + Prefs.lastJob(this).let { if (it.isBlank()) "" else "\nLast job: $it" }
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        statusText.text = buildString {
            append("SMS permission: ").append(if (hasSms()) "allowed" else "not allowed").append('\n')
            append("Sheet: ").append(if (Prefs.getUrl(this@MainActivity).isNotBlank()) "set" else "not set").append('\n')
            append("Senders: ").append(Prefs.getFilter(this@MainActivity).ifBlank { "all" }).append('\n')
            append("Battery optimisation: ").append(if (pm.isIgnoringBatteryOptimizations(packageName)) "off (good)" else "on")
        }
        logText.text = Prefs.getLog(this).ifBlank { "No activity yet" }
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()

    companion object {
        private const val REQ_SMS = 101
        private const val REQ_NOTE = 102
    }
}
