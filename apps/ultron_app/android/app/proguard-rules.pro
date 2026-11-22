# PDFBox (reads the courier POD text, sms/Pod.kt): its JPEG 2000 decoder is an optional extra library the
# app does not ship; POD PDFs are text. Its classes and resource lookups are kept as they are.
-dontwarn com.gemalto.jp2.JP2Decoder
-keep class com.tom_roush.pdfbox.** { *; }
-keep class com.tom_roush.fontbox.** { *; }
