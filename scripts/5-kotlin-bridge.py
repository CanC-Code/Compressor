import os

def generate():
    package_path = "app/src/main/java/com/videocompressor"
    os.makedirs(package_path, exist_ok=True)

    # 1. Native JNI Bridge
    engine_content = """package com.videocompressor

class NativeEngine {
    init {
        System.loadLibrary("videocompressor")
    }

    // Triggers the hardware C++ encode pipeline
    external fun compressVideo(inputPath: String, outputPath: String): Boolean
}
"""
    with open(f"{package_path}/NativeEngine.kt", "w") as f:
        f.write(engine_content)

    # 2. Main Compose Activity with File Handling UI
    main_activity_content = """package com.videocompressor

import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

class MainActivity : ComponentActivity() {
    private val nativeEngine = NativeEngine()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    CompressorScreen(nativeEngine)
                }
            }
        }
    }

    @Composable
    fun CompressorScreen(engine: NativeEngine) {
        var inputUri by remember { mutableStateOf<Uri?>(null) }
        var outputUri by remember { mutableStateOf<Uri?>(null) }
        var isCompressing by remember { mutableStateOf(false) }
        var statusText by remember { mutableStateOf("Ready") }
        val coroutineScope = rememberCoroutineScope()

        val inputLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
            inputUri = uri
        }
        
        val outputLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("video/mp4")) { uri ->
            outputUri = uri
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text("Hardware Video Compressor", style = MaterialTheme.typography.headlineSmall)
            
            Spacer(modifier = Modifier.height(32.dp))

            Button(
                onClick = { inputLauncher.launch(arrayOf("video/*")) },
                modifier = Modifier.fillMaxWidth(),
                enabled = !isCompressing
            ) {
                Text(if (inputUri != null) "Input Selected" else "1. Select Input Video")
            }

            Spacer(modifier = Modifier.height(16.dp))

            Button(
                onClick = { outputLauncher.launch("compressed_output.mp4") },
                modifier = Modifier.fillMaxWidth(),
                enabled = !isCompressing
            ) {
                Text(if (outputUri != null) "Destination Selected" else "2. Choose Output Location")
            }

            Spacer(modifier = Modifier.height(32.dp))

            Button(
                onClick = {
                    if (inputUri != null && outputUri != null) {
                        coroutineScope.launch {
                            isCompressing = true
                            statusText = "Caching input for native processing..."
                            
                            val success = withContext(Dispatchers.IO) {
                                try {
                                    val inFile = File(cacheDir, "temp_input.mp4")
                                    val outFile = File(cacheDir, "temp_output.mp4")
                                    
                                    // 1. Stream URI to internal cache for C++ access
                                    contentResolver.openInputStream(inputUri!!)?.use { input ->
                                        FileOutputStream(inFile).use { output ->
                                            input.copyTo(output)
                                        }
                                    }
                                    
                                    statusText = "Compressing via C++ Hardware NDK..."
                                    
                                    // 2. Execute Native Compression
                                    val result = engine.compressVideo(inFile.absolutePath, outFile.absolutePath)
                                    
                                    if (result || outFile.exists()) {
                                        statusText = "Saving to destination..."
                                        // 3. Stream compressed cache file back to target URI
                                        contentResolver.openOutputStream(outputUri!!)?.use { output ->
                                            outFile.inputStream().use { input ->
                                                input.copyTo(output)
                                            }
                                        }
                                        inFile.delete()
                                        outFile.delete()
                                        true
                                    } else {
                                        false
                                    }
                                } catch (e: Exception) {
                                    e.printStackTrace()
                                    false
                                }
                            }
                            
                            statusText = if (success) "Compression Complete!" else "Compression Failed"
                            isCompressing = false
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = inputUri != null && outputUri != null && !isCompressing,
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
            ) {
                Text("3. Start Compression")
            }

            Spacer(modifier = Modifier.height(24.dp))

            if (isCompressing) {
                CircularProgressIndicator()
                Spacer(modifier = Modifier.height(16.dp))
            }
            
            Text(statusText, style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center)
        }
    }
}
"""
    with open(f"{package_path}/MainActivity.kt", "w") as f:
        f.write(main_activity_content)

    # 3. Application Class
    app_class_content = """package com.videocompressor

import android.app.Application

class CompressorApp : Application()
"""
    with open(f"{package_path}/CompressorApp.kt", "w") as f:
        f.write(app_class_content)

    print("✅ 5 Generated Kotlin Core & Jetpack Compose Bridge (UI Added)")

if __name__ == "__main__":
    generate()
