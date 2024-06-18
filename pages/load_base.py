import dash
import pandas as pd
import time
import sqlite3
from dash import html, dcc, callback, Output, Input, State, ALL


# dash.register_page(__name__, name="Обработка данных", path='/load_data', order=10, my_class='my-navbar__icon-1')



def layout():

    load_data()

    return html.Div([])


def read_data():
    start_time = time.time()
    df = pd.read_hdf('data/tariff_data.h5', key='tariff_data')
    execution_time = time.time() - start_time

    print(time.time() - start_time)


def load_old_data():
    conn = sqlite3.connect('db_drafts/db9.db')
    query = '''
                    SELECT * 
                    FROM ЦПС_отформат
            '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    columns_to_drop = ['Наим отправителя', 'Наим получателя', 'Класс негабаритности_идентификатор',
                       'Класс негабаритности_наименование','Перевозка СПФ','Опасный груз','Код ЕТСНГ',
                       'Перевозка с отдельным локомотивом',
                       ]
    df.drop(columns=columns_to_drop, inplace=True)
    cargo_names = df['Наименование груза ЦО-12'].unique()
    for name in cargo_names:
        car_df = df[df['Наименование груза ЦО-12']==name]
        car_df.to_excel(f'data/old/{name}.xlsx')


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
    holdings_df.to_feather('data/holdings.feather')



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
    print(column_mapping)
    print(df.columns)
    df.rename(columns=column_mapping, inplace=True)

    df_grouped = df.groupby(group_parameters).agg(agg_params).reset_index()
    df_grouped['Доходы 2023, тыс.руб'] = df_grouped['Доходы 2023, тыс.руб'] / 1000
    print(df_grouped.columns)
    # df_grouped.to_hdf('data/tariff_data_grouped.h5', key='tariff_data')
    df_grouped.to_feather('data/tariff_data_grouped.feather')
    print (len(df_grouped))