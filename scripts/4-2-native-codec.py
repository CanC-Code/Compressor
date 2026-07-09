import os

def generate():
    cpp_dir = "app/src/main/cpp"
    os.makedirs(cpp_dir, exist_ok=True)

    cpp_content = r"""#include <jni.h>
#include <media/NdkMediaCodec.h>
#include <media/NdkMediaFormat.h>
#include <media/NdkMediaMuxer.h>
#include <media/NdkMediaExtractor.h>
#include <android/log.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>

#define LOG_TAG "NativeCodec"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

extern "C"
JNIEXPORT jboolean JNICALL
Java_com_videocompressor_NativeEngine_compressVideoNative(
        JNIEnv* env, jobject thiz, jstring input_path, jstring output_path, jobject callback) {
    
    const char *in_path = env->GetStringUTFChars(input_path, nullptr);
    const char *out_path = env->GetStringUTFChars(output_path, nullptr);
    
    jclass callbackClass = env->GetObjectClass(callback);
    jmethodID progressMethod = env->GetMethodID(callbackClass, "onProgress", "(I)V");

    AMediaExtractor *extractor = AMediaExtractor_new();
    if (AMediaExtractor_setDataSource(extractor, in_path) != AMEDIA_OK) {
        LOGE("Failed to open input");
        return JNI_FALSE;
    }
    
    int numTracks = AMediaExtractor_getTrackCount(extractor);
    int videoTrackIndex = -1;
    AMediaFormat *videoFormat = nullptr;
    int64_t durationUs = 0;
    
    for (int i = 0; i < numTracks; ++i) {
        AMediaFormat *format = AMediaExtractor_getTrackFormat(extractor, i);
        const char *mime;
        AMediaFormat_getString(format, AMEDIAFORMAT_KEY_MIME, &mime);
        if (strncmp(mime, "video/", 6) == 0) {
            videoTrackIndex = i;
            videoFormat = format;
            AMediaFormat_getInt64(format, AMEDIAFORMAT_KEY_DURATION, &durationUs);
            break;
        } else {
            AMediaFormat_delete(format);
        }
    }
    
    if (videoTrackIndex < 0) return JNI_FALSE;
    AMediaExtractor_selectTrack(extractor, videoTrackIndex);

    // CRITICAL FIX: O_RDWR instead of O_WRONLY. 
    // The muxer MUST seek back to the file header to successfully write the moov atom!
    int fd = open(out_path, O_CREAT | O_RDWR | O_TRUNC, 0666);
    if (fd < 0) {
        LOGE("Failed to open output file descriptor");
        return JNI_FALSE;
    }

    AMediaMuxer *muxer = AMediaMuxer_new(fd, AMEDIAMUXER_OUTPUT_FORMAT_MPEG_4);
    if (!muxer) {
        LOGE("Failed to create muxer");
        close(fd);
        return JNI_FALSE;
    }
    
    ssize_t muxerTrackIndex = AMediaMuxer_addTrack(muxer, videoFormat);
    AMediaMuxer_start(muxer);

    int maxInputSize = 0;
    AMediaFormat_getInt32(videoFormat, AMEDIAFORMAT_KEY_MAX_INPUT_SIZE, &maxInputSize);
    
    size_t bufferCapacity = (maxInputSize > 0) ? maxInputSize : (1024 * 1024 * 2); 
    uint8_t *buffer = new uint8_t[bufferCapacity];

    int lastProgress = -1;
    int64_t firstPts = -1;

    while (true) {
        ssize_t sampleSize = AMediaExtractor_readSampleData(extractor, buffer, bufferCapacity);
        if (sampleSize < 0) break;

        int64_t presentationTimeUs = AMediaExtractor_getSampleTime(extractor);
        uint32_t flags = AMediaExtractor_getSampleFlags(extractor);

        // Normalize PTS to start exactly at 0 to prevent muxer header corruption
        if (firstPts < 0) firstPts = presentationTimeUs;
        presentationTimeUs -= firstPts;
        if (presentationTimeUs < 0) presentationTimeUs = 0;

        AMediaCodecBufferInfo info;
        info.offset = 0;
        info.size = sampleSize;
        info.presentationTimeUs = presentationTimeUs;
        info.flags = flags;

        media_status_t writeStatus = AMediaMuxer_writeSampleData(muxer, muxerTrackIndex, buffer, &info);
        if (writeStatus != AMEDIA_OK) {
            LOGE("Failed to write sample data");
        }

        if (durationUs > 0) {
            int progress = (int)((presentationTimeUs * 100) / durationUs);
            if (progress != lastProgress) {
                env->CallVoidMethod(callback, progressMethod, progress);
                lastProgress = progress;
            }
        }
        AMediaExtractor_advance(extractor);
    }

    delete[] buffer;
    
    // Explicit stop and cleanup order is mandatory for MP4 generation
    AMediaMuxer_stop(muxer);
    AMediaMuxer_delete(muxer);
    close(fd);
    
    AMediaExtractor_delete(extractor);
    AMediaFormat_delete(videoFormat);
    
    env->ReleaseStringUTFChars(input_path, in_path);
    env->ReleaseStringUTFChars(output_path, out_path);
    
    return JNI_TRUE;
}
"""
    with open(f"{cpp_dir}/native-codec.cpp", "w") as f:
        f.write(cpp_content)
    print("✅ 4-2 Generated native-codec.cpp (Fixed Muxer Header Corruption)")

if __name__ == "__main__":
    generate()
