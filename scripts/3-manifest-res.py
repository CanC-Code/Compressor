import os

def generate():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    os.chdir(project_root)

    manifest_dir = "app/src/main"
    res_values_dir = "app/src/main/res/values"
    os.makedirs(manifest_dir, exist_ok=True)
    os.makedirs(res_values_dir, exist_ok=True)

    colors_content = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="primary">#000000</color>
    <color name="primary_variant">#121212</color>
    <color name="white">#FFFFFF</color>
</resources>
"""
    with open(f"{res_values_dir}/colors.xml", "w") as f:
        f.write(colors_content)

    themes_content = """<?xml version="1.0" encoding="utf-8"?>
<resources xmlns:tools="http://schemas.android.com/tools">
    <style name="Theme.VideoCompressor" parent="Theme.Material3.DayNight.NoActionBar">
        <item name="colorPrimary">@color/primary</item>
        <item name="android:statusBarColor">@color/primary_variant</item>
    </style>
</resources>
"""
    with open(f"{res_values_dir}/themes.xml", "w") as f:
        f.write(themes_content)

    manifest_content = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" android:maxSdkVersion="32" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" android:maxSdkVersion="29" />
    <uses-permission android:name="android.permission.READ_MEDIA_VIDEO" />

    <application
        android:name=".CompressorApp"
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="Fast Compressor"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:supportsRtl="true"
        android:theme="@style/Theme.VideoCompressor"
        android:requestLegacyExternalStorage="true">

        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
"""
    with open(f"{manifest_dir}/AndroidManifest.xml", "w") as f:
        f.write(manifest_content)
    
    print("✅ 3-Manifest & Resources Generated")

if __name__ == "__main__":
    generate()
