import os

def generate():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    os.chdir(project_root)

    # Define directories for modern adaptive icons (API 26+) and legacy vector fallbacks
    mipmap_anydpi_v26 = "app/src/main/res/mipmap-anydpi-v26"
    mipmap_anydpi = "app/src/main/res/mipmap-anydpi"
    drawable_dir = "app/src/main/res/drawable"
    
    os.makedirs(mipmap_anydpi_v26, exist_ok=True)
    os.makedirs(mipmap_anydpi, exist_ok=True)
    os.makedirs(drawable_dir, exist_ok=True)

    # 1. Background Vector (Solid dark color)
    with open(f"{drawable_dir}/ic_launcher_background.xml", "w") as f:
        f.write("""<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp" 
    android:viewportWidth="108" android:viewportHeight="108">
    <path android:fillColor="#121212" android:pathData="M0,0h108v108h-108z"/>
</vector>""")

    # 2. Foreground Vector (A simple play/compress icon symbol)
    with open(f"{drawable_dir}/ic_launcher_foreground.xml", "w") as f:
        f.write("""<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp" 
    android:viewportWidth="108" android:viewportHeight="108">
    <path android:fillColor="#FFFFFF" android:pathData="M34,34 v40 l30,-20 z"/>
</vector>""")

    # 3. Adaptive Icon XML for API 26+ (combines foreground and background)
    adaptive_icon_xml = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>"""
    
    with open(f"{mipmap_anydpi_v26}/ic_launcher.xml", "w") as f:
        f.write(adaptive_icon_xml)
        
    with open(f"{mipmap_anydpi_v26}/ic_launcher_round.xml", "w") as f:
        f.write(adaptive_icon_xml)

    # 4. Fallback Vector Icon for older devices (minSdk 24 supports raw vectors natively)
    legacy_icon_xml = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="48dp" android:height="48dp" 
    android:viewportWidth="108" android:viewportHeight="108">
    <path android:fillColor="#121212" android:pathData="M0,0h108v108h-108z"/>
    <path android:fillColor="#FFFFFF" android:pathData="M34,34 v40 l30,-20 z"/>
</vector>"""
    
    with open(f"{mipmap_anydpi}/ic_launcher.xml", "w") as f:
        f.write(legacy_icon_xml)
        
    with open(f"{mipmap_anydpi}/ic_launcher_round.xml", "w") as f:
        f.write(legacy_icon_xml)

    print("✅ 3-5-Icons Generated (Fixed Missing Mipmap AAPT Error)")

if __name__ == "__main__":
    generate()
