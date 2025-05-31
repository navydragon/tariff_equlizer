import dash
import pandas as pd
import time
import sqlite3
from dash import html, dcc, callback, Output, Input, State, ALL
from pages.constants import Constants as CON
import numpy as np

dash.register_page(__name__, name="Обработка данных", path='/load_data', order=10, my_class='my-navbar__icon-1')


def layout():

    # load_data()
    load_key_routes()

    return html.Div([])


def load_key_routes():
    # 1. Подключение к SQLite и загрузка данных
    sqlite_file = 'db9.db'
    table_name = 'ИХ_ГП'

    conn = sqlite3.connect(sqlite_file)
    query = f"SELECT * FROM {table_name}"
    df_sqlite = pd.read_sql_query(query, conn)
    conn.close()

    # 2. Загрузка данных из Excel
    excel_file = 'data/fp/key_routes.xlsx'  #
    df_excel = pd.read_excel(excel_file)

    # 3. Объединение по столбцу 'index'
    keys = ['Код станц отпр РФ', 'Код станц назн РФ', 'Код груза','Категория отпр.']

    # Приводим типы в df_sqlite и df_excel к одному типу, например — строке
    for col in keys:
        df_sqlite[col] = df_sqlite[col].astype(str)
        df_excel[col] = df_excel[col].astype(str)


    df_merged = pd.merge(
        df_sqlite,
        df_excel,
        on=keys,
        how='inner',
        suffixes=('_x', '_y')
    )
    # 4. Удаление дублирующихся столбцов (если появились одинаковые названия после merge)е
    # Теперь удалим все столбцы с суффиксом '_y'
    columns_to_drop = [col for col in df_merged.columns if col.endswith('_y')]
    df_merged.drop(columns=columns_to_drop, inplace=True)
    # Переименуем оставшиеся '_x' обратно в исходные имена
    df_merged.rename(columns=lambda c: c.split('_')[0] if '_' in c else c, inplace=True)
    df_merged.fillna(0, inplace=True)

    column_mapping = {
        '2024 Доходы,тыс.руб': 'Доходы 2024, тыс.руб',
    }

    for year in [2024] + CON.YEARS:
        old_epl = f'{year} Грузоб,тыс.ткм'
        epl = f'{year} ЦЭКР груззоборот, тыс ткм'
        column_mapping[old_epl] = epl
    # Переименование колонок
    df_merged.rename(columns=column_mapping, inplace=True)
    df_merged = df_merged.rename(columns={'2024 Грузооборот, т': '2024 Грузооборот, т_км'})
    df_merged = mean_distance(df_merged)
    print(df_merged.columns)
    # 5. Сохранение результата
    output_file = 'data/fp/key_routes_db.xlsx'  # можно использовать .csv для сохранения в CSV
    df_merged.to_excel(output_file, index=False)
    return True



def load_data():
    conn = sqlite3.connect('db9.db')

    query = '''
                SELECT * 
                FROM ИХ_ГП
            '''
    print('Начинаем обрабатывать db...')

    df = pd.read_sql_query(query, conn)
    conn.close()


    df.drop([
             'Субъект федерации отп',
             'Субъект федерации наз'
             ], axis=1, inplace=True)

    holdings_df = pd.DataFrame({'Холдинг': df['Холдинг'].unique()})
    holdings_df.to_feather('data/fp/holdings.feather')




    group_parameters = ['Группа груза',
                        'Код груза', 'Код груза(изпод)',
                        'Дор отпр', 'Дор наз',
                        'Код станц отпр РФ', 'Код станц назн РФ',
                        'Ключ ИПЕМ',
                        # 'Маршрут',
                        'Род вагона',
                        'Вид перевозки','Категория отпр.','Тип парка','Вид спец. контейнера',
                        'Холдинг','Направления',
                        ]

    agg_params = {
        '2024 Грузооборот, т_км': 'sum',
        '2024 Объем перевозок, т.': 'sum',
    #   'Доходы 2023, тыс.руб': 'sum',
        'Доходы 2024, тыс.руб': 'sum',
    }

    column_mapping = {
        '2024 Доходы,тыс.руб': 'Доходы 2024, тыс.руб',
       # '2023 Доходы,тыс.руб': 'Доходы 2023, тыс.руб'
    }

    for year in [2024,2025,2026,2027,2028,2029,2030,2031,2032,2033,2034,2035]:
        old_epl = f'{year} Грузоб,тыс.ткм'
        epl = f'{year} ЦЭКР груззоборот, тыс ткм'
        agg_params[epl] = 'sum'
        column_mapping[old_epl] = epl
    # Переименование колонок

    df.rename(columns=column_mapping, inplace=True)

    df_grouped = df.groupby(group_parameters).agg(agg_params).reset_index()

    print(df_grouped.columns)
    df_grouped = mean_distance(df_grouped)
    df_grouped.to_feather('data/fp/tariff_data_grouped.feather')
    print (len(df_grouped))


    # делаем small
    print("Small:")
    # elements_to_remove = {'Станц отпр РФ', 'Станц назн РФ'}
    # group_parameters = [param for param in group_parameters if param not in elements_to_remove]
    group_parameters = ['Группа груза', 'Код груза', 'Код груза(изпод)', 'Дор отпр', 'Дор наз',
       'Род вагона', 'Вид перевозки', 'Категория отпр.', 'Тип парка',
       'Вид спец. контейнера', 'Холдинг', 'Направления']
    print(group_parameters)

    df_grouped_small = df.groupby(group_parameters).agg(agg_params).reset_index()
    print(df_grouped_small.columns)

    df_grouped_small = mean_distance(df_grouped_small)

    df_grouped_small.to_feather('data/fp/tariff_data_grouped_small.feather')
    print(len(df_grouped_small))


def mean_distance(df):
    df['Средняя дальность, км'] = df['2024 Грузооборот, т_км'] / df[
        '2024 Объем перевозок, т.']
    # Замена бесконечных значений на NaN
    df['Средняя дальность, км'] = df['Средняя дальность, км'].replace([np.inf, -np.inf],np.nan)

    # Определяем максимальное значение для создания интервалов
    max_distance = df['Средняя дальность, км'].max()

    # Создаем интервалы с шагом 500 км
    bins = list(range(0, int(max_distance) + 1000, 500))

    # Создаем метки для интервалов, включая 'Неактуально'
    labels = [f'{bins[i]}-{bins[i + 1]}' for i in range(len(bins) - 1)] + ['Неактуально']

    # Применяем категоризацию с расширенным списком категорий
    df['Категория дальности'] = pd.cut(df['Средняя дальность, км'], bins=bins, labels=labels[:-1], right=False)
    df['Категория дальности'] = df['Категория дальности'].cat.add_categories(['Неактуально'])

    # Присваиваем категорию 'Неактуально'
    df.loc[df['Средняя дальность, км'] > 15000, 'Категория дальности'] = 'Неактуально'
    return df