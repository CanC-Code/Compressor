import os

def generate():
    package_path = "app/src/main/java/com/videocompressor"
    os.makedirs(package_path, exist_ok=True)

    # 1. Native JNI Bridge with Callback Interface
    engine_content = """package com.videocompressor

interface ProgressCallback {
    fun onProgress(percent: Int)
}

class NativeEngine {
    init { System.loadLibrary("videocompressor") }
    external fun compressVideoNative(inputPath: String, outputPath: String, callback: ProgressCallback): Boolean
}
"""
    with open(f"{package_path}/NativeEngine.kt", "w") as f:
        f.write(engine_content)

    # 2. WorkManager Worker for Background Execution
    worker_content = """package com.videocompressor

import android.content.Context
import android.net.Uri
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

class CompressorWorker(appContext: Context, workerParams: WorkerParameters) :
    CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val inputUriStr = inputData.getString("INPUT_URI") ?: return@withContext Result.failure()
        val outputUriStr = inputData.getString("OUTPUT_URI") ?: return@withContext Result.failure()

        val inputUri = Uri.parse(inputUriStr)
        val outputUri = Uri.parse(outputUriStr)

        val engine = NativeEngine()
        val inFile = File(applicationContext.cacheDir, "temp_input.mp4")
        val outFile = File(applicationContext.cacheDir, "temp_output.mp4")

        try {
            setProgress(workDataOf("PROGRESS" to 0))
            
            // 1. Stream to cache
            applicationContext.contentResolver.openInputStream(inputUri)?.use { input ->
                FileOutputStream(inFile).use { output -> input.copyTo(output) }
            }

            // 2. Execute Native Engine with Progress Callback
            val success = engine.compressVideoNative(inFile.absolutePath, outFile.absolutePath, object : ProgressCallback {
                override fun onProgress(percent: Int) {
                    setProgressAsync(workDataOf("PROGRESS" to percent))
                }
            })

            if (success && outFile.exists()) {
                setProgress(workDataOf("PROGRESS" to 99))
                // 3. Stream to user destination
                applicationContext.contentResolver.openOutputStream(outputUri)?.use { output ->
                    outFile.inputStream().use { input -> input.copyTo(output) }
                }
                inFile.delete()
                outFile.delete()
                setProgress(workDataOf("PROGRESS" to 100))
                Result.success()
            } else {
                Result.failure()
            }
        } catch (e: Exception) {
            e.printStackTrace()
            Result.failure()
        }
    }
}
"""
    with open(f"{package_path}/CompressorWorker.kt", "w") as f:
        f.write(worker_content)

    # 3. Main Compose UI with Progress Meter
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
import androidx.compose.runtime.livedata.observeAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.work.*

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    CompressorScreen(WorkManager.getInstance(applicationContext))
                }
            }
        }
    }

    @Composable
    fun CompressorScreen(workManager: WorkManager) {
        var inputUri by remember { mutableStateOf<Uri?>(null) }
        var outputUri by remember { mutableStateOf<Uri?>(null) }

        val inputLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> inputUri = uri }
        val outputLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("video/mp4")) { uri -> outputUri = uri }

        val workInfos by workManager.getWorkInfosByTagLiveData("compress_tag").observeAsState(emptyList())
        val workInfo = workInfos.firstOrNull { it.state == WorkInfo.State.RUNNING || it.state == WorkInfo.State.ENQUEUED }
        
        val isRunning = workInfo != null
        val progress = workInfo?.progress?.getInt("PROGRESS", 0) ?: 0

        Column(
            modifier = Modifier.fillMaxSize().padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text("Hardware Compressor", style = MaterialTheme.typography.headlineSmall)
            Spacer(modifier = Modifier.height(32.dp))

            Button(onClick = { inputLauncher.launch(arrayOf("video/*")) }, enabled = !isRunning) {
                Text(if (inputUri != null) "Input Selected" else "1. Select Input Video")
            }
            Spacer(modifier = Modifier.height(16.dp))

            Button(onClick = { outputLauncher.launch("compressed_output.mp4") }, enabled = !isRunning) {
                Text(if (outputUri != null) "Destination Selected" else "2. Choose Output Location")
            }
            Spacer(modifier = Modifier.height(32.dp))

            Button(
                onClick = {
                    if (inputUri != null && outputUri != null) {
                        val data = Data.Builder()
                            .putString("INPUT_URI", inputUri.toString())
                            .putString("OUTPUT_URI", outputUri.toString())
                            .build()
                        val request = OneTimeWorkRequestBuilder<CompressorWorker>()
                            .setInputData(data)
                            .addTag("compress_tag")
                            .build()
                        workManager.enqueue(request)
                    }
                },
                enabled = inputUri != null && outputUri != null && !isRunning,
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
            ) {
                Text("3. Start Background Compression")
            }

            Spacer(modifier = Modifier.height(32.dp))

            if (isRunning) {
                Text("Processing: $progress%")
                Spacer(modifier = Modifier.height(8.dp))
                LinearProgressIndicator(
                    progress = { progress / 100f },
                    modifier = Modifier.fillMaxWidth().height(8.dp)
                )
            } else if (workInfos.firstOrNull()?.state == WorkInfo.State.SUCCEEDED) {
                Text("✅ Compression Complete!", color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}
"""
    with open(f"{package_path}/MainActivity.kt", "w") as f:
        f.write(main_activity_content)

    # 4. App Class
    with open(f"{package_path}/CompressorApp.kt", "w") as f:
        f.write("package com.videocompressor\nimport android.app.Application\nclass CompressorApp : Application()\n")

    print("✅ 5 Generated Kotlin Core (WorkManager & Progress Meter)")

if __name__ == "__main__":
    generate()
