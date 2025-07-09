import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from dash import html, dcc, callback, Output, Input, State, clientside_callback

import pages.calculations as calc
import pages.helpers as helpers
import pages.scenario_parameters.scenario_parameters as sp
import pages.scenario_parameters.tarif_rules as tr
from pages.scenario_parameters.misc import input_states, check_and_prepare_params
from pages.constants import Constants as CON
from pages.data import get_revenue_parameters

dash.register_page(__name__, name="Куб эффектов", path='/cube', order=6, my_class='my-navbar__icon-2')


def layout():
    return html.Div([
        sp.scenario_parameters(),
        sp.toggle_button(),
        html.Div(
            results()
        ),
    ])


def results():
    return html.Div([
        html.Div([], id='header_div'),
        html.Section(className='my-section', children=[
            html.Div(className='my-section__header', children=[
                html.H2(className='my-section__title',
                        children='Куб эффектов'),
                html.Button(className='my-section__badge', id='btn-excel-export',
                            style={'margin-left': 'auto', 'margin-right': '10px'}, children='Выгрузить отчет'),
                # html.Span(className='my-section__badge', style={'margin': 0}, children='Выгрузить отчет (полный)'),

            ]),
            html.Div(
                className='my-separate my-separate_width_600 my-separate_vector_left'),
            dbc.Row([
                dbc.Col([
                    html.Label('Группировка верхнего уровня'),
                    dcc.Dropdown(
                        id='group_parameter',
                        options=['Группа груза', 'Код груза', 'Направления', 'Род вагона', 'Вид перевозки', 'Тип парка',
                                 'Холдинг', 'Тарифные решения'],
                        searchable=True,
                        clearable=False,
                        value='Группа груза'
                    ),
                ], width=3),
                dbc.Col([
                    html.Label('Фильтрация для группировки верхнего уровня'),
                    dcc.Dropdown(
                        id='filter',
                        options=['Уголь каменный', 'Кокс каменноугольный', 'Нефть и нефтепродукты',
                                 'Руды металлические',
                                 'Черные металлы', 'Лесные грузы', 'Минерально-строит.', 'Удобрения', 'Хлебные грузы',
                                 'Остальные грузы'],
                        searchable=True,
                        value=None
                    ),
                ], style={'display': 'none'}),
                dbc.Col([
                    html.Label('Группировка внутри'),
                    dcc.Dropdown(
                        id='group_parameter2',
                        options=['Группа груза', 'Код груза', 'Направления',
                                 'Род вагона', 'Вид перевозки',
                                 'Категория отпр.', 'Тип парка', 'Холдинг'],
                        searchable=True,
                        value=None
                    ),
                ], width=3),
                dbc.Col([
                    html.Label('Фильтрация для группировки внутри'),
                    dcc.Dropdown(
                        id='filter2',
                        options=[],
                        searchable=True,
                        value=None
                    ),
                ], width=3, style={'display': 'none'}),

            ], className='mb-3'),
            dcc.Loading(
                id="loading",
                type="default",
                color="#063971",
                fullscreen=False,
                children=[html.Div([], id='table_div')]
            ),
        ]),

    ])


outputs = [
    Output('table_div', 'children'),
]
inputs = [
    State('group_parameter', 'value'),
    State('group_parameter2', 'value'),
    State('filter', 'value'),
    State('filter2', 'value')
] + input_states
args = outputs + inputs


@callback(*args,)
def recount_base(
        group1, group2, filter, filter2,
        calculate_button,
        epl_change, market_loss,
        cif_fob,
        index_sell_prices, price_variant, index_sell_coal, index_oper, index_per,
        *revenue_index_values,
):
    params = check_and_prepare_params(
        epl_change, market_loss, cif_fob, index_sell_prices, price_variant, index_sell_coal,
        index_oper, index_per, revenue_index_values
    )
    helpers.save_last_params(params)

    global df

    # Определяем базу по правилам
    rules = tr.load_rules(active_only=True)
    database_type = 'main' if any(rule['is_special'] == 1 for rule in rules) else 'small'

    df = calc.calculate_data(database_type, params)

    index_df = get_revenue_parameters()
    indexation_variant = 'Индексация по расп.N2991-р'

    global rp
    rp = {}
    for param in index_df['param'].unique():
        rp[param] = index_df[index_df['param'] == param].sort_values('year')['value'].tolist()
    # rp.get('cap_rem').insert(0, 1.05)
    # rp.get('taxes').insert(0, 1.015)
    # rp.get('tb').insert(0, 1)
    # rp.get('invest').insert(0, 1)
    # rp.get('indexation').insert(0, 1.08)

    res_df = group_and_combine(group1, group2, filter, filter2)
    res_df = make_result_table(res_df, group1, group2)

    grid = draw_grid(res_df)
    return grid


@callback(
    Output('table_div', 'children', allow_duplicate=True),
    Input('group_parameter', 'value'),
    Input('group_parameter2', 'value'),
    Input('filter', 'value'),
    Input('filter2', 'value'),
    prevent_initial_call=True,
)
def regroup(group1, group2, filter, filter2):
    res_df = group_and_combine(group1, group2, filter, filter2)
    res_df = make_result_table(res_df, group1, group2)
    grid = draw_grid(res_df)
    return grid


def group_and_combine(group1, group2, filter, filter2):

    if group1 == 'Тарифные решения':
        if group2 is not None:
            df_gr = calc.group_data(df, group2, 'Нет')
        else:
            df_gr = df.sum(numeric_only=True).to_frame().T
    else:
        df_gr = calc.group_data(df, group1, group2 if group2 is not None else 'Нет')
        if filter is not None: df_gr = df_gr[df_gr[group1] == filter]

    if filter2 is not None and group2 is not None: df_gr = df_gr[df_gr[group2] == filter2]
    if group2 is not None and group1 != 'Тарифные решения': df_gr = df_gr[df_gr[group2] != 'ИТОГО']

    res = []
    indexation = rp.get('indexation')
    cap_rem = rp.get('cap_rem')
    taxes = rp.get('taxes')
    tb = rp.get('tb')
    rules = tr.load_rules(active_only=True)

    cap_rem_2024_total = 142348877.406051
    taxes_2024_total = 32553370.5964365
    tb_2024_total = 22091640.3407531


    cap_rem_totals = [142348877.406051]
    taxes_totals = [32553370.5964365]
    tb_totals = [22091640.3407531]
    base_totals = [0]

    for year_index, year in enumerate(CON.YEARS, start=1):
        epl_change_total = df_gr[f'{year} ЦЭКР груззоборот, тыс ткм'].sum() / df_gr[f'{year-1} ЦЭКР груззоборот, тыс ткм'].sum()
        cap_rem_totals.append(cap_rem_totals[-1] * indexation[year_index] * epl_change_total)
        taxes_totals.append(taxes_totals[-1] * indexation[year_index] * epl_change_total)
        tb_totals.append(tb_totals[-1] * indexation[year_index] * epl_change_total)
        base_totals.append(df_gr[f'Доходы {year}_0, тыс.руб'].sum())

    for index, row in df_gr.iterrows():
        res_row = {}

        rev_year_base = row[f'Доходы 2024, тыс.руб']
        epl_year_base = row[f'2024 ЦЭКР груззоборот, тыс ткм']
        epl_part = row[f'2024 ЦЭКР груззоборот, тыс ткм'] / df_gr[f'2024 ЦЭКР груззоборот, тыс ткм'].sum()
        cap_rem_values = {
            2024 : cap_rem_2024_total * epl_part,
        }
        taxes_values = {
            2024: taxes_2024_total * epl_part,
        }
        tb_values = {
            2024: tb_2024_total * epl_part,
        }

        for year_index, year in enumerate(CON.YEARS, start=1):

            rev_year = row[f'Доходы {year}, тыс.руб']
            rev_year_prev = row[f'Доходы {year - 1}, тыс.руб']
            epl_year = row[f'{year} ЦЭКР груззоборот, тыс ткм']
            epl_year_prev = row[f'{year - 1} ЦЭКР груззоборот, тыс ткм']


            cap_rem_values[year] = cap_rem_totals[1] / base_totals[1] * row[f'Доходы {year}_0, тыс.руб']
            taxes_values[year] = taxes_totals[1] / base_totals[1] * row[f'Доходы {year}_0, тыс.руб']
            tb_values[year] = tb_totals[1] / base_totals[1] * row[f'Доходы {year}_0, тыс.руб']



            res_row[f'base_{year}'] = row[f'Доходы {year}_0, тыс.руб']
            res_row[f'cap_rem_{year}'] = cap_rem_values[year]
            res_row[f'taxes_{year}'] = taxes_values[year]
            res_row[f'tb_{year}'] = tb_values[year]


            if group1 != 'Тарифные решения':
                res_row['parameter'] = row[group1]

            if group2 is not None: res_row['parameter2'] = row[group2]

            rules_sum = 0
            if year != 2024:
                for rule_index, rule_obj in enumerate(rules, start=1):
                    row[f'Доходы 2024_{rule_index}, тыс.руб'] = 0

                    res_row[f'rules_{rule_index}_2024'] = 0
                    res_row[f'rules_{rule_index}_{year}'] = row[f'Доходы {year}_{rule_index}, тыс.руб']
                    # res_row[f'rules_{rule_index}_{year}'] = (res_row[f'rules_{rule_index}_{year - 1}'] + row[
                    #     f'Доходы {year}_{rule_index}, тыс.руб']) * indexation[year_index]
                    rules_sum += res_row[f'rules_{rule_index}_{year}']
            res_row[f'rules_{year}'] = rules_sum
            if year != 2024:
                res_row[f'prev_rules_{year}'] = 0
            else:
                res_row[f'prev_rules_{year}'] = row['2024_lost']
            res.append(res_row)

    res_df = pd.DataFrame(res)
    res_df = res_df.drop_duplicates()

    return res_df


@callback(
    Output('filter', 'options'),
    Output('filter', 'value'),
    Input('group_parameter', 'value'),
    prevent_initial_call=True
)
def update_filter(param):
    if param != 'Тарифные решения':
        options = df[param].unique()
        return (options, None)
    return ([], None)


@callback(
    Output('filter2', 'options'),
    Output('filter2', 'value'),
    Input('group_parameter2', 'value'),
    prevent_initial_call=True
)
def update_filter2(param):
    if param is None: return ([], None)
    options = df[param].unique()
    return (options, None)


def draw_grid(res_df):
    # Создаем mapping для колонок с проблемными символами
    column_mapping = {}
    clean_columns = []

    for col in res_df.columns:
        clean_col = col.replace('.', '_').replace(' ', '_').replace(',', '_')
        column_mapping[col] = clean_col
        clean_columns.append(clean_col)

    # Переименовываем колонки для AgGrid
    clean_df = res_df.copy()
    clean_df.columns = clean_columns
    sum_row = {
        clean_col: round(res_df[orig_col].sum(), 2) if pd.api.types.is_numeric_dtype(res_df[orig_col]) else 'ИТОГО'
        for orig_col, clean_col in column_mapping.items()}

    columnDefs = [
        {
            "headerName": orig_col,  # Отображаемое название
            "field": clean_col  # Поле для данных
        }
        for orig_col, clean_col in column_mapping.items()
    ]
    grid = dag.AgGrid(
        id="main_grid",
        rowData=clean_df.to_dict("records"),
        columnDefs=columnDefs,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        enableEnterpriseModules=True,
        dashGridOptions={
            'groupIncludeFooter': True,
           # 'groupIncludeTotalFooter': True,
            'statusBar': {
                'statusPanels': [
                    {'statusPanel': 'agAggregationComponent', 'statusPanelParams': {'aggFuncs': ['sum']}}
                ]
            }
        },
        # dashGridOptions={
        #     'pinnedTopRowData': [sum_row],
        #     'groupIncludeFooter': True,
        #     'groupIncludeTotalFooter': True,
        # },
    )
    return grid


def make_result_table(df, group1, group2):
    my_dict = {
        # 'Эффект от индексации': 'base_plus',
        'Базовая индексация': 'base',
        'Капитальный ремонт': 'cap_rem',
        'Налоговая надбавка': 'taxes',
        'Транспортная безопасность': 'tb',
        'Отдельные тарифные решения': 'rules',
    }
    rules = tr.load_rules(active_only=True)
    for rule_index, rule_obj in enumerate(rules, start=1):
        my_dict[rule_obj['name']] = f'rules_{rule_index}'

    my_dict['Принятые ранее тарифные решения'] = 'prev_rules'
    res = []

    for index, row in df.iterrows():
        for key, value in my_dict.items():
            res_row = {}
            if group1 != 'Тарифные решения':
                res_row[group1] = row['parameter']
            if group2 is not None: res_row[group2] = row['parameter2']

            res_row['Тарифное решение'] = key
            for year_index, year in enumerate(CON.YEARS):
                res_row[str(year)] = round(row[f'{value}_{year}'] / 1000000, 3)
            res.append(res_row)

    res_df = pd.DataFrame(res)
    res_df = res_df.drop_duplicates()

    years = CON.YEARS
    res_df[str(years[0]) + '-' + str(years[-1])] = round(res_df[[str(year) for year in years]].sum(axis=1), 2)

    return res_df


clientside_callback(
    """function (n) {
        if (n) {
            dash_ag_grid.getApi("main_grid").exportDataAsExcel();
        }
        return dash_clientside.no_update
    }""",
    Output("btn-excel-export", "n_clicks"),
    Input("btn-excel-export", "n_clicks"),
    prevent_initial_call=True
)
