from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("flet_desktop")
# Keep the package on disk so the bundled Flet archive next to it can be found.
module_collection_mode = "py"
