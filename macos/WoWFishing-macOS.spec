# -*- mode: python ; coding: utf-8 -*-
# 仅用于 macOS，需在 Mac 上执行: pyinstaller WoWFishing-macOS.spec


a = Analysis(
    ["wow_fishing_mac.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=["AppKit", "Quartz", "ApplicationServices", "AVFoundation"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["win32api", "win32con", "win32gui", "pywin32"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WoWFishingMac",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="WoWFishingMac",
)

app = BUNDLE(
    coll,
    name="WoWFishingMac.app",
    icon=None,
    bundle_identifier="com.linkfish.wowfishing.mac",
    info_plist={
        # 发布版本号（对外展示）。
        "CFBundleShortVersionString": "1.0",
        # 构建版本号（可与展示版本保持一致）。
        "CFBundleVersion": "1.0",
        "NSMicrophoneUsageDescription": "用于监听游戏音频并检测上钩声音。",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)
