plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.ultron.ultron_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // The old Ultron Phone app's id (and its signing key, below): ULTRON installs over it as an update, so a
        // phone that trusted that app takes this one as its new version, and the old one never needs removing.
        applicationId = "com.bindal.ultronphone"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // GitHub builds (.github/workflows/flutter-app.yml) sign with the one fixed key kept in the owner's Drive
    // (scripts/github/android_app.py keystore, the key of the old Ultron Phone app), so a new APK installs over the
    // app already on the phone. A local build without ANDROID_KEYSTORE_FILE is signed with the debug key.
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
            signingConfig = if (keystore != null) signingConfigs.getByName("release") else signingConfigs.getByName("debug")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
}

dependencies {
    // "SMS only" mode (kotlin/.../sms): uploads that survive restarts and retry, the notification, POD text
    implementation("androidx.work:work-runtime-ktx:2.10.1")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("com.tom-roush:pdfbox-android:2.0.27.0")
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
