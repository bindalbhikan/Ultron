plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.bindal.ultronphone"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.bindal.ultronphone"
        minSdk = 26
        targetSdk = 35
        // CI sets the build number (GitHub run number), so every APK installs over the last one
        versionCode = (System.getenv("APP_VERSION_CODE") ?: "1").toInt()
        versionName = "2.0." + (System.getenv("APP_VERSION_CODE") ?: "0")
    }

    // One fixed key (GitHub secret ANDROID_KEYSTORE_B64 + ANDROID_KEYSTORE_PASSWORD), so an update
    // installs over the app already on the phone. Without it the build is signed with a debug key.
    val keystore = System.getenv("ANDROID_KEYSTORE_FILE")
    signingConfigs {
        if (keystore != null) {
            create("release") {
                storeFile = file(keystore)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = "ultronphone"
                keyPassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = if (keystore != null) signingConfigs.getByName("release") else signingConfigs.getByName("debug")
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.work:work-runtime-ktx:2.9.1")
}
