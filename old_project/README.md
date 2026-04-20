pyinstaller --onefile --add-binary "venv/Lib/site-packages/tables/libblosc2.dll;." --add-data "pages;pages" --add-data "assets;assets" --hidden-import dash_bootstrap_components --hidden-import pyarrow.vendored.version  app.py
# rule_conditions

# фильтр в уровень с шапкой