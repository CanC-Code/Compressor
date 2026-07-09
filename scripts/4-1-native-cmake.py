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

# CRITICAL: Linking mediandk gives us access to NdkMediaCodec for hardware HEVC encoding
find_library(
        mediandk-lib
        mediandk)

target_link_libraries(
        videocompressor
        ${log-lib}
        ${mediandk-lib})
"""
    with open(f"{cmake_dir}/CMakeLists.txt", "w") as f:
        f.write(cmake_content)
    print("✅ 4-1-CMakeLists.txt Generated (Linked mediandk)")

if __name__ == "__main__":
    generate()
