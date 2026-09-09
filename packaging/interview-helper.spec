from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("faster_whisper") + [
    ("../skills", "skills"),
    ("../templates", "templates"),
    ("../LICENSE", "."),
]

a = Analysis(
    ["../src/app.py"],
    pathex=[".."],
    binaries=[],
    datas=datas,
    hiddenimports=["AppKit", "objc"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Interview Helper", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Interview Helper")
app = BUNDLE(
    coll,
    name="Interview Helper.app",
    bundle_identifier="local.interviewhelper.app",
    info_plist={"NSMicrophoneUsageDescription": "Captures mock interview audio locally for transcription and coaching."},
)
