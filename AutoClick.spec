# PyInstaller spec for AutoClick.app. Build with `make build`.
#
# The bundle id must stay fixed: macOS keys the Accessibility and Input
# Monitoring permissions on it.

import tomllib

with open("pyproject.toml", "rb") as f:
    VERSION = tomllib.load(f)["project"]["version"]

BUNDLE_ID = "io.github.ramadhan-zain.autoclick"

a = Analysis(["src/autoclick/__main__.py"], pathex=["src"])
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoClick",
    console=False,
    target_arch="arm64",
    codesign_identity=None,
)

coll = COLLECT(exe, a.binaries, a.datas, name="AutoClick")

app = BUNDLE(
    coll,
    name="AutoClick.app",
    bundle_identifier=BUNDLE_ID,
    version=VERSION,
    info_plist={
        "CFBundleName": "AutoClick",
        "CFBundleDisplayName": "Auto Click",
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
    },
)
