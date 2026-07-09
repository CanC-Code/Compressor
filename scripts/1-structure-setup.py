import os

def create_structure():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    os.chdir(project_root)

    folders = [
        "app/src/main/cpp",
        "app/src/main/java/com/videocompressor",
        "app/src/main/res/drawable",
        "app/src/main/res/values",
        "app/src/main/res/mipmap-hdpi",
        "gradle/wrapper"
    ]

    for folder in folders:
        os.makedirs(folder, exist_ok=True)
    print("✅ 1-Structure initialized for Video Compressor.")

if __name__ == "__main__":
    create_structure()
