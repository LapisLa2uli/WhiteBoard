from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files(
    "playwright",
    excludes=["**/.local-browsers", "**/.local-browsers/**"],
)
binaries = [
    item
    for item in collect_dynamic_libs("playwright")
    if ".local-browsers" not in str(item[0]).replace("\\", "/")
    and ".app/" not in str(item[0]).replace("\\", "/")
    and not str(item[0]).replace("\\", "/").endswith(".app")
]
hiddenimports = ["playwright.async_api"]
