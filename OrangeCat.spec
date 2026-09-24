# -*- mode: python ; coding: utf-8 -*-
# Orange Cat Desktop Pet spec
# onefile打包：用户双击直接运行，无需安装

a = Analysis(
    ['pet_engine.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        # sounds: only WAV files + config JSON; exclude source/ and processed/ intermediates
        ('sounds/*.wav', 'sounds'),
        ('sounds/config', 'sounds/config'),
        ('icon.png', '.'),
        # Qt5 platform plugin — required for PyQt5 on Windows
        ('C:/Users/humac/anaconda3/Library/plugins/platforms', 'PyQt5/Qt5/plugins/platforms'),
    ],
    hiddenimports=['PyQt5.sip', 'PyQt5.QtMultimedia'],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy third-party libs (safe to exclude)
        'numpy', 'scipy', 'matplotlib', 'pandas',
        'PIL', 'pillow',
        'cryptography', 'pytest', 'setuptools', 'pip', 'wheel',
        'tkinter',
        'transformers', 'torch', 'torchvision',
        'huggingface_hub', 'tokenizers', 'safetensors',
        'sam2', 'rembg', 'onnxruntime',
        'IPython', 'jupyter', 'notebook',
        'sympy', 'networkx',
        # Qt modules not used by pet (only Core+Gui+Widgets+Multimedia needed)
        'PyQt5.QtPdf', 'PyQt5.QtQuick', 'PyQt5.QtQml',
        # QtNetwork kept — QtMultimedia depends on it
        'PyQt5.QtVirtualKeyboard',
        'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineCore',
        'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebKit',
        'PyQt5.QtXml', 'PyQt5.QtSvg', 'PyQt5.QtSql',
        'PyQt5.QtBluetooth', 'PyQt5.QtDBus',
        'PyQt5.QtDesigner', 'PyQt5.QtHelp',
        'PyQt5.QtMultimediaWidgets',
        'PyQt5.QtNfc', 'PyQt5.QtOpenGL',
        'PyQt5.QtPositioning', 'PyQt5.QtLocation',
        'PyQt5.QtPrintSupport', 'PyQt5.QtSensors',
        'PyQt5.QtSerialPort', 'PyQt5.QtTest',
        'PyQt5.QtTextToSpeech', 'PyQt5.QtXmlPatterns',
    ],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OrangeCat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,           # UPX must be OFF — Qt5 DLLs fail with UPX
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
