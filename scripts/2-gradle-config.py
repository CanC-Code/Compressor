import os

def generate():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    os.chdir(project_root)

    settings_content = """pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "VideoCompressor"
include ':app'
"""
    with open("settings.gradle", "w") as f:
        f.write(settings_content)

    gradle_properties_content = """android.useAndroidX=true
android.enableJetifier=true
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
"""
    with open("gradle.properties", "w") as f:
        f.write(gradle_properties_content)

    project_build_content = """plugins {
    id 'com.android.application' version '8.2.1' apply false
    id 'org.jetbrains.kotlin.android' version '2.0.0' apply false
    id 'org.jetbrains.kotlin.plugin.compose' version '2.0.0' apply false
}
"""
    with open("build.gradle", "w") as f:
        f.write(project_build_content)

    app_dir = "app"
    os.makedirs(app_dir, exist_ok=True)

    app_build_content = """plugins {
    id 'com.android.application'
    id 'org.jetbrains.kotlin.android'
    id 'org.jetbrains.kotlin.plugin.compose'
}

android {
    namespace 'com.videocompressor'
    compileSdk 34

    defaultConfig {
        applicationId "com.videocompressor"
        minSdk 24
        targetSdk 34
        versionCode 1
        versionName "1.0"
        externalNativeBuild {
            cmake {
                cppFlags "-std=c++17"
            }
        }
    }

    buildTypes {
        release {
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
    
    buildFeatures {
        compose true
    }

    externalNativeBuild {
        cmake {
            path "src/main/cpp/CMakeLists.txt"
            version "3.22.1+"
        }
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_1_8
        targetCompatibility JavaVersion.VERSION_1_8
    }
    kotlinOptions {
        jvmTarget = '1.8'
    }
}

dependencies {
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation 'androidx.lifecycle:lifecycle-runtime-ktx:2.7.0'
    implementation 'androidx.activity:activity-compose:1.8.2'
    
    implementation platform('androidx.compose:compose-bom:2024.02.00')
    implementation 'androidx.compose.ui:ui'
    implementation 'androidx.compose.ui:ui-graphics'
    implementation 'androidx.compose.ui:ui-tooling-preview'
    implementation 'androidx.compose.material3:material3'
}
"""
    with open(f"{app_dir}/build.gradle", "w") as f:
        f.write(app_build_content)
    print("✅ 2-Gradle Configuration Generated")

if __name__ == "__main__":
    generate()
