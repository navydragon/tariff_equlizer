import dash
import dash_pivottable
from dash import html, dcc, callback, Output, Input, State

import pages.calculations as calc
import pages.scenario_parameters.scenario_parameters as sp
import pages.scenario_parameters.tarif_rules as tr
from pages.scenario_parameters.misc import input_states, check_and_prepare_params
from pages.constants import Constants as CON

dash.register_page(__name__, name="Сводные", path='/pivot', order=7, my_class='my-navbar__icon-2')


def layout():
    global df

    res = html.Div([
        sp.scenario_parameters(),
        sp.toggle_button(),
        dcc.Loading(id="pivot-div", type="default", fullscreen=False, children=[
            html.Div([], id='pivot_output')
        ]),
    ])
    return res


outputs = [
    Output('pivot_output', 'children'),
]

args = outputs + input_states


@callback(
    *args
    # prevent_initial_call=True
)
def update_dashboard(
        calculate_button,
        epl_change, market_loss,
        cif_fob,
        index_sell_prices, price_variant, index_sell_coal, index_oper, index_per,
        *revenue_index_values
):
    params = check_and_prepare_params(
        epl_change, market_loss, cif_fob,index_sell_prices, price_variant, index_sell_coal,
        index_oper, index_per, revenue_index_values
    )

    df = calc.calculate_data('small', params)
    select_columns = ["Группа груза", "Направления", "Дор отпр", "Дор наз", "Вид перевозки", "Холдинг", 'Род вагона',
                      'Категория отпр.', 'Тип парка', 'Вид спец. контейнера']
    columns_for_del = list(set(list(df.select_dtypes(exclude=['floating']))) - set(select_columns))
    df = df.drop(columns=columns_for_del)

    df = df.groupby(list(df.select_dtypes(exclude=['floating']))).sum()
    df = df.reset_index()

    df = melt_pivot_df(df, select_columns)
    head_data_values = list(df.select_dtypes(include=['floating']))
    head_data_filters = list(df.select_dtypes(exclude=['floating']))
    data_data = [df.columns.values.tolist()] + df.values.tolist()
    res = html.Div([
        dash_pivottable.PivotTable(
            id='table',
            data=data_data,
            rows=['Группа груза'],
            cols=['Направления'],
            colOrder="key_a_to_z",
            rowOrder="key_a_to_z",
            rendererName="Table",
            aggregatorName="Count",
        ),
        html.Div(
            id='output'
        )
    ])
    return res


@callback(
    Output('output', 'children'),
    [Input('table', 'cols'),
     Input('table', 'rows'),
     Input('table', 'rowOrder'),
     Input('table', 'colOrder'),
     Input('table', 'aggregatorName'),
     Input('table', 'rendererName')],
    prevent_initial_call=True
)
def display_props(cols, rows, row_order, col_order, aggregator, renderer):
    return [
        html.P(str(cols), id='columns'),
        html.P(str(rows), id='rows'),
        html.P(str(row_order), id='row_order'),
        html.P(str(col_order), id='col_order'),
        html.P(str(aggregator), id='aggregator'),
        html.P(str(renderer), id='renderer'),
    ]


def melt_pivot_df(df, index_columns):
    df = df.loc[:, ~df.columns.str.contains('rules')]
    df = df.loc[:, ~df.columns.str.contains('_без')]
    cols_to_change = {}
    # cols_to_change[f'Доходы 2023, тыс.руб'] = f'Доходы 2023, тыс.руб'
    cols_to_change[f'Доходы 2024, тыс.руб'] = f'Доходы 2024, тыс.руб'
    rules = tr.load_rules(active_only=True)

    for year in CON.YEARS:
        if len(rules) > 0:
            columns_to_sum = [f'Доходы {year}_{i}, тыс.руб' for i in range(1, len(rules) + 1)]
            df[f'{year} Отдельные решения, тыс.руб'] = df[columns_to_sum].sum(axis=1)
        cols_to_change[f'Доходы {year}, тыс.руб'] = f'{year} Доходы, тыс.руб'
        cols_to_change[f'Доходы {year}_0, тыс.руб'] = f'{year} Базовая индексация, тыс.руб'

    df = df.rename(columns=cols_to_change)

    # Преобразование DataFrame
    df_melt = df.melt(
        id_vars=index_columns,
        var_name='Year_Metric', value_name='Value'
    )

    # Извлечение года и метрики из объединённой колонки
    df_melt[['Год', 'Metric']] = df_melt['Year_Metric'].str.extract(r'(\d{4}) (.+)')
    # print(df_melt['Year_Metric'].unique())
    # print(df_melt['Metric'].unique())
    # Заполнение пропущенных значений в столбце 'Metric'
    # df_melt['Metric'] = df_melt['Metric'].fillna(0)
    # print(df_melt[df_melt['Year_Metric']=='2029 Доходы, тыс.руб'].tail())
    # print(df_melt.info())
    # income_mask = df_melt['Metric'].str.contains('Доходы')
    # print(df_melt.loc[income_mask, 'Metric']).info()
    # df_melt.loc[income_mask, 'Metric'] = 'Доходы, тыс.руб'
    # print(df_melt.columns)
    # print(df_melt['Metric'].unique())
    # Поворот таблицы для получения нужного формата
    df_pivot = df_melt.pivot_table(index=index_columns + ['Год'], columns='Metric',
                                   values='Value', aggfunc='sum').reset_index()

    # Переименование колонок
    df_pivot.rename(columns={'Грузооборот, т_км': 'Грузоб,тыс.ткм',
                             'Доходы,тыс.руб': 'Доходы,тыс.руб', 'Объем перевозок, т.': 'Объем перевозок, т.'},
                    inplace=True)
    return df_pivot
