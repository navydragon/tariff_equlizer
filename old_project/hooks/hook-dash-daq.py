from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('dash_daq', include_datas=['.json', '.css', '*.js'])