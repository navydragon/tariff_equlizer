import dash
import pandas as pd
import time
import sqlite3
from dash import html, dcc, callback, Output, Input, State, ALL


# dash.register_page(__name__, name="Обработка данных", path='/load_data', order=10, my_class='my-navbar__icon-1')



def layout():

    load_data()

    return html.Div([])

def load_data():
    conn = sqlite3.connect('db_7.db')

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
                        #'Станц отпр РФ','Станц назн РФ',
                        'Код станц отпр РФ', 'Код станц назн РФ',
                        'Ключ ИПЕМ',
                        # 'Маршрут',
                        'Род вагона',
                        'Вид перевозки','Категория отпр.','Тип парка','Вид спец. контейнера',
                        'Холдинг','Направления',

                        ]
    agg_params = {
        '2023 Грузооборот, т_км': 'sum',
        '2023 Объем перевозок, т.': 'sum',
        'Доходы 2023, тыс.руб': 'sum',
        'Доходы 2024, тыс.руб': 'sum',
    }

    column_mapping = {
        '2024 Доходы,тыс.руб': 'Доходы 2024, тыс.руб',
        '2023 Доходы,тыс.руб': 'Доходы 2023, тыс.руб'
    }

    for year in [2024,2025,2026,2027,2028,2029,2030,2031,2032,2033,2034,2035]:
        old_epl = f'{year} Грузоб,тыс.ткм'
        epl = f'{year} ЦЭКР груззоборот, тыс ткм'
        agg_params[epl] = 'sum'
        column_mapping[old_epl] = epl
    # Переименование колонок

    df.rename(columns=column_mapping, inplace=True)

    df_grouped = df.groupby(group_parameters).agg(agg_params).reset_index()
    df_grouped['Доходы 2023, тыс.руб'] = df_grouped['Доходы 2023, тыс.руб'] / 1000
    print(df_grouped.columns)

    df_grouped.to_feather('data/fp/tariff_data_grouped.feather')
    print (len(df_grouped))