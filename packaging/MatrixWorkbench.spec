# Build on the target OS. Windows artifacts are produced by windows-desktop.yml.
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
datas = [(str(root / "THIRD_PARTY_NOTICES.md"), ".")]
datas += [(str(path), "licenses") for path in (root / "packaging" / "licenses").glob("*.txt")]
datas += collect_data_files("pyqtgraph", includes=["colors/maps/*"])
if sys.platform.startswith("linux"):
    datas += collect_data_files("jevdb", includes=["*.duckdb_extension"])

analysis = Analysis(
    [str(root / "packaging" / "desktop_entry.py")],
    pathex=[str(root)],
    binaries=[], datas=datas, hiddenimports=[],
    excludes=["streamlit", "plotly", "playwright", "pytest", "IPython", "matplotlib",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="MatrixWorkbench", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
bundle = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="MatrixWorkbench")
