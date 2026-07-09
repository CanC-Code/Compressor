import os
import subprocess
import sys

def run_build():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    os.chdir(project_root)

    try:
        # Validate Gradle wrapper exists, if not construct it
        if not os.path.exists("gradlew"):
            subprocess.run(["gradle", "wrapper", "--gradle-version", "8.10.2"], check=True)

        # Dynamic mapping for OS compatibility
        gradle_cmd = "gradlew.bat" if sys.platform == "win32" else "./gradlew"
        
        if sys.platform != "win32":
            subprocess.run(["chmod", "+x", "gradlew"], check=True)

        subprocess.run([gradle_cmd, "clean", "assembleDebug", "--no-daemon"], check=True)
        print("✅ APK Compression Engine Build Successful!")

    except subprocess.CalledProcessError:
        print("❌ APK Build Failed. Verify environmental SDKs and CMake.")

if __name__ == "__main__":
    run_build()
