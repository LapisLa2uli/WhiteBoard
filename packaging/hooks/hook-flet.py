"""Override flet-cli's PyInstaller hook.

The upstream hook copies the unpacked client from ~/.flet/client, which makes
the installer huge and still leaves first launch downloading if the archive is
missing. WhiteBoard ships flet-windows.zip / flet-macos.tar.gz instead.
"""

from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files("flet.controls.material", includes=["icons.json"])
datas += collect_data_files(
    "flet.controls.cupertino", includes=["cupertino_icons.json"]
)
