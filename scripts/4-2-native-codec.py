import os

def generate():
    cpp_dir = "app/src/main/cpp"
    os.makedirs(cpp_dir, exist_ok=True)

    cpp_content = r"""#include <jni.h>
#include <media/NdkMediaCodec.h>
#include <media/NdkMediaFormat.h>
#include <media/NdkMediaMuxer.h>
#include <media/NdkMediaExtractor.h>
#include <android/native_window.h>
#include <android/log.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <cerrno>

#define LOG_TAG "NativeCodec"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

// MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface. Not exposed as a
// named constant by the NDK media headers, so it is defined explicitly.
#define COLOR_FormatSurface 0x7F000789

static const int64_t kDequeueTimeoutUs = 10000;   // 10ms
static const int kMaxStalledIterations = 2000;    // ~20s of zero progress before we bail

namespace {

// RAII cleanup for every native handle used during a transcode. The
// original code had several early "return JNI_FALSE" paths that skipped
// fd/extractor/codec cleanup entirely, and - more importantly - never
// checked whether AMediaMuxer_addTrack/_start/_writeSampleData actually
// succeeded before calling AMediaMuxer_stop() on an invalid muxer. That
// combination is what produced a 0-byte (header-less) output file: the
// destination Uri is created empty by Android's document picker up front,
// and if the muxer never truly started, nothing ever gets written into it.
struct TranscodeContext {
    AMediaExtractor *videoExtractor = nullptr;
    AMediaExtractor *audioExtractor = nullptr;
    AMediaCodec *decoder = nullptr;
    AMediaCodec *encoder = nullptr;
    AMediaMuxer *muxer = nullptr;
    AMediaFormat *videoFormat = nullptr;
    AMediaFormat *audioFormat = nullptr;
    ANativeWindow *encoderSurface = nullptr;
    int fd = -1;
    bool muxerStarted = false;

    ~TranscodeContext() {
        if (decoder) { AMediaCodec_stop(decoder); AMediaCodec_delete(decoder); }
        if (encoder) { AMediaCodec_stop(encoder); AMediaCodec_delete(encoder); }
        if (encoderSurface) { ANativeWindow_release(encoderSurface); }
        if (muxer) {
            if (muxerStarted) AMediaMuxer_stop(muxer);
            AMediaMuxer_delete(muxer);
        }
        if (fd >= 0) close(fd);
        if (videoFormat) AMediaFormat_delete(videoFormat);
        if (audioFormat) AMediaFormat_delete(audioFormat);
        if (videoExtractor) AMediaExtractor_delete(videoExtractor);
        if (audioExtractor) AMediaExtractor_delete(audioExtractor);
    }
};

// Picks a target video bitrate that is always meaningfully lower than the
// source, so this is an actual compression pass rather than a same-size
// passthrough (which is what the previous implementation really did,
// regardless of what it was labeled).
int32_t computeTargetBitrate(int32_t width, int32_t height, int32_t frameRate,
                              int64_t sourceBitrate) {
    if (frameRate <= 0) frameRate = 30;

    // ~0.08 bits-per-pixel is a widely used "visually near-lossless" H.264
    // target for typical camera/screen footage. True mathematically
    // lossless video compression is not attempted here - it does not
    // meaningfully shrink real-world footage, which would defeat the
    // purpose of a "compressor" app.
    const double bpp = 0.08;
    int64_t computed = (int64_t) (width * height * frameRate * bpp);

    int64_t target = computed;
    if (sourceBitrate > 0) {
        int64_t cappedToSource = (int64_t) (sourceBitrate * 0.75);
        target = (computed < cappedToSource) ? computed : cappedToSource;
    }

    if (target < 800000) target = 800000;     // floor: keep it watchable
    if (target > 8000000) target = 8000000;    // ceiling: keep files small
    return (int32_t) target;
}

} // namespace

extern "C"
JNIEXPORT jboolean JNICALL
Java_com_videocompressor_NativeEngine_compressVideoNative(
        JNIEnv* env, jobject thiz, jstring input_path, jstring output_path, jobject callback) {

    const char *in_path = env->GetStringUTFChars(input_path, nullptr);
    const char *out_path = env->GetStringUTFChars(output_path, nullptr);

    jclass callbackClass = env->GetObjectClass(callback);
    jmethodID progressMethod = env->GetMethodID(callbackClass, "onProgress", "(I)V");

    TranscodeContext ctx;

    // ---- 1. Extractor #1: drives the video decode/encode pipeline ----
    ctx.videoExtractor = AMediaExtractor_new();
    if (AMediaExtractor_setDataSource(ctx.videoExtractor, in_path) != AMEDIA_OK) {
        LOGE("Failed to open input: %s", in_path);
        env->ReleaseStringUTFChars(input_path, in_path);
        env->ReleaseStringUTFChars(output_path, out_path);
        return JNI_FALSE;
    }

    int numTracks = AMediaExtractor_getTrackCount(ctx.videoExtractor);
    int videoTrackIndex = -1;
    int audioTrackIndex = -1;
    int64_t durationUs = 0;

    for (int i = 0; i < numTracks; ++i) {
        AMediaFormat *format = AMediaExtractor_getTrackFormat(ctx.videoExtractor, i);
        const char *mime = nullptr;
        AMediaFormat_getString(format, AMEDIAFORMAT_KEY_MIME, &mime);
        if (mime != nullptr && videoTrackIndex < 0 && strncmp(mime, "video/", 6) == 0) {
            videoTrackIndex = i;
            ctx.videoFormat = format;
            AMediaFormat_getInt64(format, AMEDIAFORMAT_KEY_DURATION, &durationUs);
        } else if (mime != nullptr && audioTrackIndex < 0 && strncmp(mime, "audio/", 6) == 0) {
            audioTrackIndex = i;
            AMediaFormat_delete(format); // re-fetched via extractor #2 below
        } else {
            AMediaFormat_delete(format);
        }
    }

    if (videoTrackIndex < 0 && audioTrackIndex < 0) {
        LOGE("No video or audio track found in input");
        env->ReleaseStringUTFChars(input_path, in_path);
        env->ReleaseStringUTFChars(output_path, out_path);
        return JNI_FALSE;
    }

    // ---- 2. Extractor #2: independent, drives the audio remux pass ----
    // A second extractor instance on the same file avoids having to
    // interleave sample-by-sample reads across two very different pacing
    // models (asynchronous codec draining vs. a straight sample copy).
    if (audioTrackIndex >= 0) {
        ctx.audioExtractor = AMediaExtractor_new();
        if (AMediaExtractor_setDataSource(ctx.audioExtractor, in_path) == AMEDIA_OK) {
            AMediaExtractor_selectTrack(ctx.audioExtractor, audioTrackIndex);
            ctx.audioFormat = AMediaExtractor_getTrackFormat(ctx.audioExtractor, audioTrackIndex);
        } else {
            LOGE("Failed to open secondary extractor for audio, dropping audio track");
            AMediaExtractor_delete(ctx.audioExtractor);
            ctx.audioExtractor = nullptr;
            audioTrackIndex = -1;
        }
    }

    // ---- 3. Output file + muxer ----
    ctx.fd = open(out_path, O_CREAT | O_RDWR | O_TRUNC, 0666);
    if (ctx.fd < 0) {
        LOGE("Failed to open output file descriptor: %s", strerror(errno));
        env->ReleaseStringUTFChars(input_path, in_path);
        env->ReleaseStringUTFChars(output_path, out_path);
        return JNI_FALSE;
    }

    ctx.muxer = AMediaMuxer_new(ctx.fd, AMEDIAMUXER_OUTPUT_FORMAT_MPEG_4);
    if (!ctx.muxer) {
        LOGE("Failed to create muxer");
        unlink(out_path);
        env->ReleaseStringUTFChars(input_path, in_path);
        env->ReleaseStringUTFChars(output_path, out_path);
        return JNI_FALSE;
    }

    // Audio's format is known up front, so its track can be added right
    // away. Video's track can only be added once the encoder reports its
    // real output format below - a freshly created H.264 encoder cannot
    // describe its own csd-0/csd-1 SPS/PPS before it has produced a frame.
    ssize_t muxerAudioTrack = -1;
    if (ctx.audioFormat) {
        muxerAudioTrack = AMediaMuxer_addTrack(ctx.muxer, ctx.audioFormat);
        if (muxerAudioTrack < 0) {
            LOGE("Failed to add audio track to muxer, continuing video-only");
            muxerAudioTrack = -1;
            audioTrackIndex = -1;
        }
    }

    ssize_t muxerVideoTrack = -1;

    // ---- 4. Video: real hardware decode -> encode, not a passthrough copy ----
    if (videoTrackIndex >= 0) {
        AMediaExtractor_selectTrack(ctx.videoExtractor, videoTrackIndex);

        int32_t width = 0, height = 0, frameRate = 0;
        int64_t sourceBitrate = 0;
        AMediaFormat_getInt32(ctx.videoFormat, AMEDIAFORMAT_KEY_WIDTH, &width);
        AMediaFormat_getInt32(ctx.videoFormat, AMEDIAFORMAT_KEY_HEIGHT, &height);
        AMediaFormat_getInt32(ctx.videoFormat, AMEDIAFORMAT_KEY_FRAME_RATE, &frameRate);
        AMediaFormat_getInt64(ctx.videoFormat, AMEDIAFORMAT_KEY_BIT_RATE, &sourceBitrate);

        // NOTE: deliberately using the raw key string "rotation-degrees" here
        // instead of the AMEDIAFORMAT_KEY_ROTATION symbol. That symbol is
        // annotated __INTRODUCED_IN(28) in the NDK headers, and this project's
        // minSdk is 26 - Clang's -Wunguarded-availability rejects the mere
        // *reference* to it at compile time (not just at link time), even
        // though the key itself works fine as a plain string on API 26+.
        int32_t rotation = 0;
        bool hasRotation = AMediaFormat_getInt32(ctx.videoFormat, "rotation-degrees", &rotation);

        const char *srcMime = nullptr;
        AMediaFormat_getString(ctx.videoFormat, AMEDIAFORMAT_KEY_MIME, &srcMime);

        if (width <= 0 || height <= 0) {
            LOGE("Invalid source video dimensions (%dx%d)", width, height);
        } else {
            int32_t targetBitrate = computeTargetBitrate(width, height, frameRate, sourceBitrate);

            AMediaFormat *encFormat = AMediaFormat_new();
            AMediaFormat_setString(encFormat, AMEDIAFORMAT_KEY_MIME, "video/avc");
            AMediaFormat_setInt32(encFormat, AMEDIAFORMAT_KEY_WIDTH, width);
            AMediaFormat_setInt32(encFormat, AMEDIAFORMAT_KEY_HEIGHT, height);
            AMediaFormat_setInt32(encFormat, AMEDIAFORMAT_KEY_BIT_RATE, targetBitrate);
            AMediaFormat_setInt32(encFormat, AMEDIAFORMAT_KEY_FRAME_RATE, frameRate > 0 ? frameRate : 30);
            AMediaFormat_setInt32(encFormat, AMEDIAFORMAT_KEY_I_FRAME_INTERVAL, 2);
            AMediaFormat_setInt32(encFormat, AMEDIAFORMAT_KEY_COLOR_FORMAT, COLOR_FormatSurface);
            if (hasRotation) {
                AMediaFormat_setInt32(encFormat, "rotation-degrees", rotation);
            }

            ctx.encoder = AMediaCodec_createEncoderByType("video/avc");
            media_status_t status = ctx.encoder
                ? AMediaCodec_configure(ctx.encoder, encFormat, nullptr, nullptr,
                                         AMEDIACODEC_CONFIGURE_FLAG_ENCODE)
                : AMEDIA_ERROR_UNSUPPORTED;
            AMediaFormat_delete(encFormat);

            if (!ctx.encoder || status != AMEDIA_OK) {
                LOGE("Failed to create/configure H.264 encoder");
            } else if (AMediaCodec_createInputSurface(ctx.encoder, &ctx.encoderSurface) != AMEDIA_OK) {
                LOGE("Failed to create encoder input surface");
            } else if (AMediaCodec_start(ctx.encoder) != AMEDIA_OK) {
                LOGE("Failed to start encoder");
            } else {
                ctx.decoder = AMediaCodec_createDecoderByType(srcMime);
                if (!ctx.decoder ||
                    AMediaCodec_configure(ctx.decoder, ctx.videoFormat, ctx.encoderSurface, nullptr, 0) != AMEDIA_OK ||
                    AMediaCodec_start(ctx.decoder) != AMEDIA_OK) {
                    LOGE("Failed to create/configure/start decoder for mime %s", srcMime ? srcMime : "(null)");
                } else {
                    // ---- Decode -> encode pump loop (Surface-to-Surface) ----
                    bool sawInputEOS = false, sawDecoderEOS = false, sawEncoderEOS = false;
                    int stalledIterations = 0;

                    while (!sawEncoderEOS && stalledIterations < kMaxStalledIterations) {
                        bool progressed = false;

                        // Feed the decoder from the extractor.
                        if (!sawInputEOS) {
                            ssize_t inIdx = AMediaCodec_dequeueInputBuffer(ctx.decoder, kDequeueTimeoutUs);
                            if (inIdx >= 0) {
                                size_t bufSize = 0;
                                uint8_t *buf = AMediaCodec_getInputBuffer(ctx.decoder, inIdx, &bufSize);
                                ssize_t sampleSize = AMediaExtractor_readSampleData(ctx.videoExtractor, buf, bufSize);
                                if (sampleSize < 0) {
                                    AMediaCodec_queueInputBuffer(ctx.decoder, inIdx, 0, 0, 0,
                                                                  AMEDIACODEC_BUFFER_FLAG_END_OF_STREAM);
                                    sawInputEOS = true;
                                } else {
                                    int64_t pts = AMediaExtractor_getSampleTime(ctx.videoExtractor);
                                    AMediaCodec_queueInputBuffer(ctx.decoder, inIdx, 0, sampleSize, pts, 0);
                                    AMediaExtractor_advance(ctx.videoExtractor);
                                }
                                progressed = true;
                            }
                        }

                        // Drain the decoder straight onto the encoder's input Surface.
                        if (!sawDecoderEOS) {
                            AMediaCodecBufferInfo info;
                            ssize_t outIdx = AMediaCodec_dequeueOutputBuffer(ctx.decoder, &info, kDequeueTimeoutUs);
                            if (outIdx >= 0) {
                                bool eos = (info.flags & AMEDIACODEC_BUFFER_FLAG_END_OF_STREAM) != 0;
                                AMediaCodec_releaseOutputBuffer(ctx.decoder, outIdx, info.size > 0);
                                if (eos) {
                                    sawDecoderEOS = true;
                                    AMediaCodec_signalEndOfInputStream(ctx.encoder);
                                }
                                progressed = true;
                            } else if (outIdx == AMEDIACODEC_INFO_OUTPUT_FORMAT_CHANGED ||
                                       outIdx == AMEDIACODEC_INFO_OUTPUT_BUFFERS_CHANGED) {
                                progressed = true;
                            }
                        }

                        // Drain the encoder into the muxer.
                        AMediaCodecBufferInfo encInfo;
                        ssize_t encIdx = AMediaCodec_dequeueOutputBuffer(ctx.encoder, &encInfo, kDequeueTimeoutUs);
                        if (encIdx == AMEDIACODEC_INFO_OUTPUT_FORMAT_CHANGED) {
                            AMediaFormat *realFormat = AMediaCodec_getOutputFormat(ctx.encoder);
                            muxerVideoTrack = AMediaMuxer_addTrack(ctx.muxer, realFormat);
                            AMediaFormat_delete(realFormat);
                            if (muxerVideoTrack >= 0 && AMediaMuxer_start(ctx.muxer) == AMEDIA_OK) {
                                ctx.muxerStarted = true;
                            } else {
                                LOGE("Failed to add video track / start muxer");
                            }
                            progressed = true;
                        } else if (encIdx >= 0) {
                            if ((encInfo.flags & AMEDIACODEC_BUFFER_FLAG_CODEC_CONFIG) == 0 &&
                                encInfo.size > 0 && ctx.muxerStarted && muxerVideoTrack >= 0) {
                                size_t encBufSize = 0;
                                uint8_t *encBuf = AMediaCodec_getOutputBuffer(ctx.encoder, encIdx, &encBufSize);
                                media_status_t writeStatus = AMediaMuxer_writeSampleData(
                                        ctx.muxer, muxerVideoTrack, encBuf, &encInfo);
                                if (writeStatus != AMEDIA_OK) {
                                    LOGE("Failed to write encoded video sample");
                                }
                                if (durationUs > 0 && progressMethod) {
                                    int percent = (int) ((encInfo.presentationTimeUs * 90) / durationUs);
                                    if (percent > 90) percent = 90;
                                    if (percent < 0) percent = 0;
                                    env->CallVoidMethod(callback, progressMethod, percent);
                                }
                            }
                            if (encInfo.flags & AMEDIACODEC_BUFFER_FLAG_END_OF_STREAM) {
                                sawEncoderEOS = true;
                            }
                            AMediaCodec_releaseOutputBuffer(ctx.encoder, encIdx, false);
                            progressed = true;
                        }

                        stalledIterations = progressed ? 0 : (stalledIterations + 1);
                    }

                    if (!sawEncoderEOS) {
                        LOGE("Transcode loop stalled without reaching end of stream");
                    }
                }
            }
        }
    }

    // ---- 5. Audio: bit-exact passthrough remux, no quality loss ----
    if (audioTrackIndex >= 0 && muxerAudioTrack >= 0) {
        if (!ctx.muxerStarted) {
            // No video track made it through (e.g. video-only input, or an
            // audio-only source file) - audio alone still needs the muxer started.
            if (videoTrackIndex < 0 && AMediaMuxer_start(ctx.muxer) == AMEDIA_OK) {
                ctx.muxerStarted = true;
            }
        }

        if (ctx.muxerStarted) {
            int32_t maxInputSize = 0;
            AMediaFormat_getInt32(ctx.audioFormat, AMEDIAFORMAT_KEY_MAX_INPUT_SIZE, &maxInputSize);
            size_t audioBufCap = maxInputSize > 0 ? (size_t) maxInputSize : (size_t) (256 * 1024);
            uint8_t *audioBuf = new uint8_t[audioBufCap];

            while (true) {
                ssize_t sampleSize = AMediaExtractor_readSampleData(ctx.audioExtractor, audioBuf, audioBufCap);
                if (sampleSize < 0) break;

                AMediaCodecBufferInfo info;
                info.offset = 0;
                info.size = sampleSize;
                info.presentationTimeUs = AMediaExtractor_getSampleTime(ctx.audioExtractor);
                info.flags = AMediaExtractor_getSampleFlags(ctx.audioExtractor);

                if (AMediaMuxer_writeSampleData(ctx.muxer, muxerAudioTrack, audioBuf, &info) != AMEDIA_OK) {
                    LOGE("Failed to write audio sample");
                }
                AMediaExtractor_advance(ctx.audioExtractor);
            }
            delete[] audioBuf;
        }
    }

    if (progressMethod) {
        env->CallVoidMethod(callback, progressMethod, 100);
    }

    // Success requires the muxer to have genuinely started AND, if a video
    // track existed on input, that it was actually transcoded - we never
    // silently degrade a video+audio file into an audio-only "success".
    bool videoOk = (videoTrackIndex < 0) || (ctx.muxerStarted && muxerVideoTrack >= 0);
    bool ok = ctx.muxerStarted && videoOk;

    if (!ok) {
        // ~TranscodeContext still closes the fd/muxer; remove the resulting
        // empty/partial file so the caller never treats a bogus 0-byte or
        // truncated file as a real result.
        unlink(out_path);
    }

    env->ReleaseStringUTFChars(input_path, in_path);
    env->ReleaseStringUTFChars(output_path, out_path);

    return ok ? JNI_TRUE : JNI_FALSE;
}
"""
    with open(f"{cpp_dir}/native-codec.cpp", "w") as f:
        f.write(cpp_content)
    print("✅ 4-2 Generated native-codec.cpp (Real hardware transcode, audio track, fixed 0-byte output)")

if __name__ == "__main__":
    generate()
