import os

def generate():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    os.chdir(project_root)

    cmake_dir = "app/src/main/cpp"
    os.makedirs(cmake_dir, exist_ok=True)

    cmake_content = """cmake_minimum_required(VERSION 3.22.1)

project("videocompressor")

add_library(
        videocompressor
        SHARED
        native-codec.cpp)

find_library(
        log-lib
        log)

# Linking mediandk gives us access to NdkMediaCodec, NdkMediaExtractor,
# NdkMediaMuxer and NdkMediaFormat for real hardware-accelerated H.264
# decode/encode transcoding (not a same-format passthrough remux).
find_library(
        mediandk-lib
        mediandk)

# REQUIRED FIX: ANativeWindow_acquire/_release (used for the encoder's Surface
# input in native-codec.cpp) live in libandroid.so, NOT libmediandk.so.
# Without this the linker fails with "undefined reference to
# ANativeWindow_release" as soon as the real Surface-to-Surface decode/encode
# pipeline is compiled in, which previously produced a build that either
# failed to link or silently fell back to the old broken passthrough path.
find_library(
        android-lib
        android)

target_link_libraries(
        videocompressor
        ${log-lib}
        ${mediandk-lib}
        ${android-lib})
"""
    with open(f"{cmake_dir}/CMakeLists.txt", "w") as f:
        f.write(cmake_content)
    print("✅ 4-1-CMakeLists.txt Generated (Linked mediandk + android for hardware transcode)")

if __name__ == "__main__":
    generate()
