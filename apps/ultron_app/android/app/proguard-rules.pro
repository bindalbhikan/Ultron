# PDFBox (reads the courier POD text, sms/Pod.kt): its JPEG 2000 codec (decoder and encoder) is an optional extra library the
# app does not ship; POD PDFs are text. Its classes and resource lookups are kept as they are.
-dontwarn com.gemalto.jp2.**
-keep class com.tom_roush.pdfbox.** { *; }
-keep class com.tom_roush.fontbox.** { *; }

# WorkManager (sms/SmsUpload.kt) opens its Room database by reflection on the generated class's no-argument
# constructor; R8 removed it and the app closed at start ("NoSuchMethodException: WorkDatabase_Impl.<init>").
-keep class * extends androidx.room.RoomDatabase { <init>(); }
-keep class androidx.work.impl.WorkDatabase_Impl { *; }
