import dash
import numpy as np
import pandas as pd
from dash import html, dcc, callback, Output, Input, State

import pages.dashboard.absolute_revenues as absolute_revenues
from pages.constants import Constants as CON
from pages.data import get_revenue_parameters, get_plan_df

absolute_revenues.get_callbacks()

import pages.calculations as calc
import pages.scenario_parameters.scenario_parameters as sp
import pages.helpers as helpers
import plotly.graph_objects as go
import dash_bootstrap_components as dbc

import pages.scenario_parameters.tarif_rules as tr
from pages.scenario_parameters.misc import input_states, check_and_prepare_params

GR_DF = None
PARAMS = None
CL_DF = None

dash.register_page(__name__, name="Финансовый план / Отдельные решения", path='/fp', order=1,
                   my_class='my-navbar__icon-1')

CARGOS = CON.CARGOS

HOLDINGS = pd.read_feather('data/fp/holdings.feather')
HOLDINGS = HOLDINGS[(HOLDINGS['Холдинг'] != 'Прочие') & (HOLDINGS['Холдинг'] != 'неопределен')]
HOLDINGS = np.append(HOLDINGS['Холдинг'].unique(), 'Все')

df = []
loss_df = []
ipem_df = []


def layout():
    return html.Div([
        sp.scenario_parameters(),
        sp.toggle_button(),
        dcc.Loading(id="table-div", type="default", fullscreen=False, children=[]),
        html.Div(className='my-separate my-separate_width_600 my-separate_vector_left mt-4'),
        html.H2(className='my-header__nav-title mb-3', children='Оценка мер покрытия дефицита', id='kpis_header'),
        dcc.Loading(id="kpis-div", type="default", fullscreen=False, children=[]),
        html.Section(className='my-section', children=[
            html.Div(className='my-section__header', children=[
                html.H2(className='my-section__title',
                        children='Эффекты от применения индексации и отдельных решений'),
                html.Span(className='my-section__badge', children='млрд руб.')
            ]),
            html.Div(
                className='my-separate my-separate_width_600 my-separate_vector_left'),
            dbc.Row([
                dbc.Col([
                    html.Label('Группировка верхнего уровня'),
                    dcc.Dropdown(
                        id='second_slice',
                        options=[CON.CARGO, 'Холдинг', 'Вид перевозки'],
                        searchable=True,
                        clearable=False,
                        value=CON.CARGO,
                        style={'width': '150px'}
                    ),
                ], width=2),
                dbc.Col([
                    html.Label('Группировка внутри'),
                    dcc.Dropdown(
                        id='second_slice2',
                        options=[CON.CARGO, 'Холдинг', 'Вид перевозки', 'Нет'],
                        searchable=True,
                        clearable=False,
                        value='Нет',
                        style={'width': '150px'}
                    ),
                ], width=2),
                dbc.Col([
                    html.Label('Фильтр по грузу'),
                    dcc.Dropdown(
                        id='cargo_filter',
                        options=CARGOS,
                        searchable=True,
                        multi=True,
                        clearable=False,
                        value=[],
                        style={'width': '250px'}
                    ),
                ], width=3),
                dbc.Col([
                    html.Label('Фильтр по холдингу'),
                    dcc.Dropdown(
                        id='holding_filter',
                        options=HOLDINGS,
                        searchable=True,
                        clearable=False,
                        multi=True,
                        value=[],
                        style={'width': '250px'}
                    ),
                ], width=3),
                dbc.Col([
                    html.Label('Год'),
                    dcc.Dropdown(
                        id='second_year',
                        options=CON.YEARS,
                        searchable=True,
                        clearable=False,
                        value=2025,
                        style={'width': '150px'}
                    ),
                ], width=2),
            ]),
            dbc.Row([
                dbc.Col([
                    dcc.Loading(
                        id="loading",
                        type="default",
                        color="#e21a1a",
                        fullscreen=False,
                        children=[html.Div([], id='second-div', className='mt-4')]
                    ),
                ]),
                dbc.Col([
                    dcc.Loading(
                        id="loading",
                        color="#e21a1a",
                        type="default",
                        fullscreen=False,
                        children=[html.Div([], id='second-div2')]
                    ),
                ]),
            ], className='mt-2', id='second-row', style={'flex-wrap': 'nowrap'}),
        ]),
        dcc.Loading(id='absolute_revenues_loading', type="default", fullscreen=False, children=[
            html.Div(
                children=[absolute_revenues.layout()],
                id='absoulte_revenues_div'
            )
        ]),
    ])


page_inputs = [
    State('second_slice', 'value'),
    State('second_slice2', 'value'),
    State('second_year', 'value'),
    State('cargo_filter', 'value'),
    State('holding_filter', 'value'),
]
inputs = page_inputs + input_states

outputs = [
    Output('table-div', 'children'),
    Output('kpis-div', 'children'),
    Output('kpis_header', 'children'),
    Output('second-div', 'children'),
    Output('second-div2', 'children'),
    Output('absoulte_revenues_div', 'children'),
    # Output('rules_div', 'children'),
    # Output('routes_div', 'children'),
]

args = outputs + inputs


@callback(
    *args
    # prevent_initial_call=True
)
def update_dashboard(
        second_slice, second_slice2, second_year, cargo_filter, holding_filter,
        calculate_button,
        epl_change, market_loss,
        cif_fob, index_sell_prices, price_variant, index_sell_coal, index_oper, index_per,
        *revenue_index_values,

):
    global PARAMS
    PARAMS = check_and_prepare_params(
        epl_change, market_loss, cif_fob, index_sell_prices, price_variant, index_sell_coal,
        index_oper, index_per, revenue_index_values
    )

    helpers.save_last_params(PARAMS)

    # Расчет на уровне маршрутов
    global df
    df = calc.calculate_data('small', PARAMS)
    # if 'Yes' in PARAMS['market']['use_market']:
    if PARAMS['market_loss'] == [True]:
        loss_df = calc.market_coef(df)
    else:
        loss_df = df

    # else:
    #    df['market_coefficient'] = 1.0
    #    df['market_coefficient_r'] = 1.0

    if cargo_filter != []:
        df = df[df['Группа груза'].isin(cargo_filter)]

    # группируем данные
    df_gr = calc.group_data(df, second_slice, second_slice2)

    kpis = make_kpis(df_gr)
    kpis_header = "Оценка мер покрытия дефицита (с учетом изменения грузооборота)" if PARAMS['epl_change'] == [
        True] else "Оценка мер покрытия дефицита"

    main_table = make_main_table(df_gr, PARAMS)
    # main_table = []
    cargo = bar_graph(df_gr, second_slice, second_slice2, second_year)
    # cargo = []
    table = make_res_table(df_gr, loss_df, second_slice, second_slice2, second_year)

    return (
        html.Div([main_table]),
        html.Div([kpis]), kpis_header,
        table, cargo,
        absolute_revenues.layout(),
    )


def make_kpis(df):
    rules = tr.load_rules(active_only=True)
    data = {
        'year': [],
        'deficit': [-403.5, -1839.6, -1857.8, -1780.8, -1663.1, -2303.6],
        'invest': [1647.6, 1839.6, 1857.8, 2167.2, 2322.5, 2727.2],
        'base': [],
        'base_percent': [],
        'rules': [],
        'rules_percent': [],
        'revenue': [],
        'total': [],
        'total_percent': [],
    }
    start = helpers.billions(df[CON.PR_P].sum())
    base_indexation = []
    base_indexation_percent = []
    for year in CON.LITTLE_YEARS:
        prev_rev = df[f'Доходы {year - 1}, тыс.руб'].sum()
        base_rev = df[f'Доходы {year}_0, тыс.руб'].sum()
        data['year'].append(year)
        data['base'].append(base_rev)

        rule_index = 0
        rules_sum = 0
        for rule in rules:
            rule_index += 1
            rules_sum += df[f'Доходы {year}_{rule_index}, тыс.руб'].sum()
        data['rules'].append(rules_sum)
        data['total'].append(base_rev + rules_sum)
        if year == 2025:
            data['base_percent'].append(base_rev * 100 / df[CON.PR_P].sum())
            data['rules_percent'].append(rules_sum * 100 / df[CON.PR_P].sum())
            data['total_percent'].append((base_rev + rules_sum) * 100 / df[CON.PR_P].sum())
        else:
            data['base_percent'].append(base_rev * 100 / prev_rev)
            data['rules_percent'].append(rules_sum * 100 / prev_rev)
            data['total_percent'].append((base_rev + rules_sum) * 100 / prev_rev)
        data['revenue'].append(rules_sum * 100 + prev_rev + base_rev)

    df = pd.DataFrame(data)

    cards = [
    ]
    for index, row in df.iterrows():
        cards.append(
            html.Div(className="my-card__item", children=[
                html.Div(className="my-card__caption",
                         children=f"{int(row['year'])} год"),
                html.Div(className="my-card__body", children=[
                    html.Div(className="my-card__info", children=[
                        html.Div(className="my-card__count", children=[
                            html.P(className="my-card__count-title my-title_size_36",
                                   children=f"{round(helpers.billions(row['base'] + row['rules']), 1)}",
                                   style={'display': 'inline-block'}),
                            html.P(className="my-card__count-caption",
                                   children=f"млрд",
                                   style={'display': 'inline-block'}),
                        ]),
                        html.P(className="my-card__text",
                               # children='f'
                               children=[f"Индексация",
                                         f" ({round(row['base_percent'] + row['rules_percent'], 1)}%)"],
                               # children=f"(: {row['deficit']})",
                               ),
                    ]),
                    html.Div(className="my-indicators__description", children=[
                        html.Div(className="my-indicators__description-item", children=[
                            html.Div(className="my-card__count", children=[
                                html.P(className="my-card__count-title",
                                       children=f"{round(helpers.billions(row['base']), 1)}",
                                       style={'display': 'inline-block'}),
                                html.P(className="my-card__count-caption",
                                       children=f"млрд",
                                       style={'display': 'inline-block'}),
                            ]),
                            html.Div(className="my-card__count", children=[
                                html.P(
                                    className="my-card__text",
                                    children='Базовые решения',
                                ),
                                html.P(
                                    className="my-card__text my-card__text_margin_left my-card__text_color_green",
                                    children=f"(+{round(row['base_percent'], 1)}%)",
                                ),
                            ]),
                        ]),
                        html.Div(className="my-indicators__description-item", children=[
                            html.Div(className="my-card__count", children=[
                                html.P(className="my-card__count-title",
                                       children=f"{round(helpers.billions(row['rules']), 1)}",
                                       style={'display': 'inline-block'}),
                                html.P(className="my-card__count-caption",
                                       children=f"млрд",
                                       style={'display': 'inline-block'}),
                            ]),
                            html.Div(className="my-card__count", children=[
                                html.P(
                                    className="my-card__text",
                                    children='Отдельные решения',
                                ),
                                html.P(
                                    className="my-card__text my-card__text_margin_left my-card__text_color_green",
                                    children=f"(+{round(row['rules_percent'], 1)}%)",
                                ),
                            ]),
                        ]),
                    ]),
                ]),
            ]),
        )
    return html.Div(className="my-cards", children=cards)


def make_res_table(df, loss_df, parameter, parameter2, year):
    head = html.Div(className="my-table__header my-table__header_type_scroll",
                    children=[
                        html.Ul(className="my-table__row ", children=[
                            html.Li(className="my-table__column", children=[
                                html.P(
                                    className="my-table__text my-table__text_color_grey",
                                    children=parameter)
                            ]),
                            html.Li(
                                className="my-table__column my-table__column_align_center my-table__column_width_120 text-center",
                                children=[
                                    html.P(className="my-table__text my-table__badge", children='Базовые решения',
                                           style={'min-height': '44px', 'display': 'flex', 'align-items': 'center',
                                                  'justify-content': 'center'}
                                           ),
                                ]),
                            html.Li(
                                className="my-table__column my-table__column_align_center my-table__column_width_120 text-center",
                                children=[
                                    html.P(className="my-table__text my-table__badge", children='Отдельные решения'),
                                ]),
                            html.Li(
                                className="my-table__column my-table__column_align_center my-table__column_width_120 text-center",
                                children=[
                                    html.P(className="my-table__text my-table__badge", children='Увеличение нагрузки'),
                                ]),
                            html.Li(
                                className="my-table__column my-table__column_align_center my-table__column_width_120 text-center",
                                children=[
                                    html.P(className="my-table__text my-table__badge",
                                           children='Выпадающие объемы'),
                                ]) if PARAMS['market_loss'] == [True] else '',
                        ])
                    ])
    table_rows = []
    rules = tr.load_rules(active_only=True)
    totals = [0, 0, 0]

    prev_sum = df[f'Доходы {year - 1}, тыс.руб'].sum()
    if parameter2 == 'Нет':
        for index, row in df.iterrows():
            if parameter2 == 'Нет' or row[parameter2] == 'ИТОГО':
                label = row[parameter]
                if PARAMS['market_loss'] == [True]:
                    loss_df_row = loss_df[loss_df[parameter] == row[parameter]]
                add_class = 'my-table__text_weight_bold'
                row_class = 'background-gray' if parameter2 != 'Нет' and row[parameter2] == 'ИТОГО' else ''
            else:
                label = row[parameter2]
                if PARAMS['market_loss'] == [True]:
                    loss_df_row = loss_df[loss_df[parameter2] == row[parameter2]]
                add_class = ''
                row_class = ''

            indexation_sum = row[f'Доходы {year}_0, тыс.руб']
            prev = row[f'Доходы {year - 1}, тыс.руб'] if row[f'Доходы {year - 1}, тыс.руб'] != 0 else 0.0000000001
            rules_sum = sum(row[f'Доходы {year}_{i}, тыс.руб'] for i in range(1, len(rules) + 1))
            row_sum = round(indexation_sum + rules_sum, 2)
            if parameter2 == 'Нет' or row[parameter2] == 'ИТОГО':
                totals[0] += indexation_sum
                totals[1] += rules_sum
                totals[2] += row_sum

            table_rows.append(
                html.Ul(className=f"my-table__row {row_class}", children=[
                    html.Li(className="my-table__column", children=[
                        html.P(
                            className=f"my-table__text {add_class}",
                            children=label)
                    ]),
                    html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                        html.P(
                            className=f"my-table__text my-table__text_weight_bold",
                            children=[helpers.billions(indexation_sum),
                                      html.Br(), "(",
                                      round(indexation_sum * 100 / prev, 1),
                                      "%)"])
                    ]),
                    html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                        html.P(
                            className=f"my-table__text my-table__text_weight_bold",
                            children=[helpers.billions(rules_sum), html.Br(), "(",
                                      round(rules_sum * 100 / prev, 1),
                                      "%)"])
                    ]),
                    html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                        html.P(
                            className=f"my-table__text my-table__text_weight_bold ",
                            children=[helpers.billions(row_sum), html.Br(), "(",
                                      round(round(rules_sum * 100 / prev, 1) + round(indexation_sum * 100 / prev, 1),
                                            1),
                                      "%)"])
                    ]),
                    html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                        html.P(
                            className=f"my-table__text my-table__text_weight_bold ",
                            children=[helpers.billions(loss_df_row[f'money_loss_{year}'].sum()), html.Br(), "(",
                                      helpers.billions(loss_df_row[f'cargo_loss_{year}'].sum()), " млн т)"]
                        )
                    ]) if PARAMS['market_loss'] == [True] else '',
                ])
            )

    if parameter2 != 'Нет':
        total_rows = df[df[parameter2] == 'ИТОГО']
        for main_index, main_row in total_rows.iterrows():
            loss_df_row = loss_df[loss_df[parameter] == main_row[parameter]] if PARAMS['market_loss'] == [True] else []
            label = main_row[parameter]
            add_class = 'my-table__text_weight_bold'
            row_class = 'background-gray'
            indexation_sum = main_row[f'Доходы {year}_0, тыс.руб']
            prev = main_row[f'Доходы {year - 1}, тыс.руб'] if main_row[
                                                                  f'Доходы {year - 1}, тыс.руб'] != 0 else 0.0000000001
            rules_sum = sum(main_row[f'Доходы {year}_{i}, тыс.руб'] for i in range(1, len(rules) + 1))
            row_sum = round(indexation_sum + rules_sum, 2)
            totals[0] += indexation_sum
            totals[1] += rules_sum
            totals[2] += row_sum
            table_rows.append(
                html.Ul(className=f"my-table__row {row_class}", children=[
                    html.Li(className="my-table__column", children=[
                        html.P(
                            className=f"my-table__text {add_class}",
                            children=label)
                    ]),
                    html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                        html.P(
                            className=f"my-table__text my-table__text_weight_bold",
                            children=[helpers.billions(indexation_sum),
                                      html.Br(), "(",
                                      round(indexation_sum * 100 / prev, 1),
                                      "%)"])
                    ]),
                    html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                        html.P(
                            className=f"my-table__text my-table__text_weight_bold",
                            children=[helpers.billions(rules_sum), html.Br(), "(",
                                      round(rules_sum * 100 / prev, 1),
                                      "%)"])
                    ]),
                    html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                        html.P(
                            className=f"my-table__text my-table__text_weight_bold ",
                            children=[helpers.billions(row_sum), html.Br(), "(",
                                      round(round(rules_sum * 100 / prev, 1) + round(indexation_sum * 100 / prev, 1),
                                            1),
                                      "%)"])
                    ]),
                    html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                        html.P(
                            className=f"my-table__text my-table__text_weight_bold ",
                            children=[helpers.billions(loss_df_row[f'money_loss_{year}'].sum()), html.Br(), "(",
                                      helpers.billions(loss_df_row[f'cargo_loss_{year}'].sum()), " млн т)"]
                        )
                    ]) if PARAMS['market_loss'] == [True] else '',
                ])
            )
            current_rows = df[(df[parameter2] != 'ИТОГО') & (df[parameter] == main_row[parameter])]
            for index, row in current_rows.iterrows():
                label = row[parameter2]
                if PARAMS['market_loss'] == [True]:
                    loss_df_row = loss_df[(loss_df[parameter2] == row[parameter2]) & (loss_df[parameter] == row[parameter])]
                add_class = ''
                row_class = ''
                indexation_sum = row[f'Доходы {year}_0, тыс.руб']
                prev = row[f'Доходы {year - 1}, тыс.руб'] if row[f'Доходы {year - 1}, тыс.руб'] != 0 else 0.0000000001
                rules_sum = sum(row[f'Доходы {year}_{i}, тыс.руб'] for i in range(1, len(rules) + 1))
                row_sum = round(indexation_sum + rules_sum, 2)
                table_rows.append(
                    html.Ul(className=f"my-table__row {row_class}", children=[
                        html.Li(className="my-table__column", children=[
                            html.P(
                                className=f"my-table__text {add_class}",
                                children=label)
                        ]),
                        html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                            html.P(
                                className=f"my-table__text my-table__text_weight_bold",
                                children=[helpers.billions(indexation_sum),
                                          html.Br(), "(",
                                          round(indexation_sum * 100 / prev, 1),
                                          "%)"])
                        ]),
                        html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                            html.P(
                                className=f"my-table__text my-table__text_weight_bold",
                                children=[helpers.billions(rules_sum), html.Br(), "(",
                                          round(rules_sum * 100 / prev, 1),
                                          "%)"])
                        ]),
                        html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                            html.P(
                                className=f"my-table__text my-table__text_weight_bold ",
                                children=[helpers.billions(row_sum), html.Br(), "(",
                                          round(
                                              round(rules_sum * 100 / prev, 1) + round(indexation_sum * 100 / prev, 1),
                                              1),
                                          "%)"])
                        ]),
                        html.Li(className="my-table__column my-table__column_width_120 text-center", children=[
                            html.P(
                                className=f"my-table__text my-table__text_weight_bold ",
                                children=[helpers.billions(loss_df_row[f'money_loss_{year}'].sum()), html.Br(), "(",
                                          helpers.billions(loss_df_row[f'cargo_loss_{year}'].sum()), " млн т)"]
                            )
                        ]) if PARAMS['market_loss'] == [True] else '',
                    ])
                )
    table_rows.insert(0,
                      html.Ul(className=f"my-table__row", children=[
                          html.Li(className="my-table__column", children=[
                              html.P(
                                  className=f"my-table__text my-table__text_weight_bold",
                                  children='ИТОГО')
                          ]),
                          html.Li(
                              className="my-table__column my-table__column_width_120 text-center",
                              children=[
                                  html.P(
                                      className=f"my-table__text my-table__text_weight_bold",
                                      children=[helpers.billions(totals[0]), html.Br(), "(",
                                                round(totals[0] * 100 / prev_sum, 1),
                                                "%)"])
                              ]),
                          html.Li(
                              className="my-table__column my-table__column_width_120 text-center",
                              children=[
                                  html.P(
                                      className=f"my-table__text my-table__text_weight_bold",
                                      children=[helpers.billions(totals[1]), html.Br(), "(",
                                                round(totals[1] * 100 / prev_sum, 1),
                                                "%)"])
                              ]),
                          html.Li(
                              className="my-table__column my-table__column_width_120 text-center",
                              children=[
                                  html.P(
                                      className=f"my-table__text my-table__text_weight_bold",
                                      children=[helpers.billions(totals[2]), html.Br(), "(",
                                                round(round(totals[0] * 100 / prev_sum, 1) + round(
                                                    totals[1] * 100 / prev_sum, 1), 1),
                                                "%)"])
                              ]),
                          html.Li(
                              className="my-table__column my-table__column_width_120 text-center",
                              children=[
                                  html.P(
                                      className=f"my-table__text my-table__text_weight_bold",
                                      children=[helpers.billions(loss_df[f'money_loss_{year}'].sum()), html.Br(), "(",
                                                helpers.billions(loss_df[f'cargo_loss_{year}'].sum()), " млн т)"])
                              ]) if PARAMS['market_loss'] == [True] else '',
                      ])
                      )

    table = html.Div(className="my-table my-table_margin_top", children=[
        head,
        html.Div(
            className="my-table__main my-table__main_type_scroll scroll my-table__main_height_450",
            children=table_rows),
    ])
    return table


def bar_graph(df, parameter, parameter2, year):
    if parameter2 != 'Нет':
        df = df[df[parameter2] == 'ИТОГО'].head(10).copy()
    else:
        df = df.sort_values(by=CON.PR_P, ascending=False).head(10).copy()
    df['indexation'] = df[f'Доходы {year}_0, тыс.руб']
    rules = tr.load_rules(active_only=True)

    rule_index = 0
    df['rules'] = 0
    for rule in rules:
        rule_index += 1
        df['rules'] += df[f'Доходы {year}_{rule_index}, тыс.руб']

    df['sum'] = df['indexation'] + df['rules']

    df = df.sort_values(by='sum', ascending=True)
    fig = go.Figure(layout=dict(height=500))
    fig.add_trace(go.Bar(
        y=df[parameter], x=df['indexation'] / 1000000,
        text=round(df['indexation'] / 1000000, 1),
        textposition='auto',
        textfont=dict(size=14),
        outsidetextfont=dict(size=14),
        orientation='h',
        name='Базовые решения'
    ))
    fig.add_trace(go.Bar(
        y=df[parameter], x=df['rules'] / 1000000,
        textposition='auto',
        text=round(df['rules'] / 1000000, 1),
        textfont=dict(size=14),
        outsidetextfont=dict(size=14),
        orientation='h',
        name='Отдельные решения',
    ))

    fig.update_layout(
        barmode='stack',
        legend=dict(y=5, orientation='h'),
        margin=dict(t=20, l=0, r=0),
        margin_pad=30,
        plot_bgcolor='white',
        font=dict(family='Arial'),
    )
    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(tickfont=dict(family='Arial', size=14))
    graph = html.Div([dcc.Graph(figure=fig)], id='cargo-graph1')

    return graph


@callback(
    Output('second-div', 'children', allow_duplicate=True),
    Output('second-div2', 'children', allow_duplicate=True),
    Input('second_slice', 'value'),
    Input('second_slice2', 'value'),
    Input('second_year', 'value'),
    Input('cargo_filter', 'value'),
    Input('holding_filter', 'value'),
    prevent_initial_call=True,
)
def cargo_graph1_callback(slice, slice2, year, cargo_filter, holding_filter):
    df2 = df
    loss_df2 = loss_df
    if cargo_filter != []:
        df2 = df2[df2['Группа груза'].isin(cargo_filter)]
        if PARAMS['market_loss'] == [True]:
            loss_df2 = loss_df2[loss_df2['Группа груза'].isin(cargo_filter)]
    if holding_filter != []:
        df2 = df2[df2['Холдинг'].isin(holding_filter)]
        if PARAMS['market_loss'] == [True]:
            loss_df2 = loss_df2[loss_df2['Холдинг'].isin(holding_filter)]

    df_gr = calc.group_data(df2, slice, slice2)
    # df_gr.sort_values(by=CON.PR_P, inplace=True, ascending=False)
    if slice == 'Холдинг':
        df_gr = df_gr[df_gr['Холдинг'] != 'Прочие']
        df_gr = df_gr[df_gr['Холдинг'] != 'неопределен']

    res_table = make_res_table(df_gr, loss_df2, slice, slice2, year)
    res_graph = bar_graph(df_gr, slice, slice2, year)
    return [res_table, res_graph]


def make_rules(df, cargo, holding, rules_type, route):
    if cargo and cargo != 'Все': df = df[df['Группа груза'] == cargo]

    if holding and holding != 'Все': df = df[df['Холдинг'] == holding]

    if route and route != '': df = df[df['Маршрут'] == route]

    head = html.Div(className="my-table__header my-table__header_type_scroll", children=[
        html.Ul(className="my-table__row ", children=[
            html.Li(className="my-table__column", children=[
                html.P(className="my-table__text my-table__text_color_grey", children='Правило')
            ]),
            *[html.Li(className="my-table__column my-table__column_align_center my-table__column_width_120", children=[
                html.P(className="my-table__text my-table__badge", children=f"{year} г.")
            ]) for year in CON.YEARS]
        ])
    ])

    res = calc.group_data(df, 'Группа груза', 'Нет')
    # base_indexation
    start = res[CON.PR_P].sum()
    base_indexation = []
    base_indexation_percent = []
    total_sum = []
    if rules_type == 'Нарастающим итогом':
        summ = 0
        for year in CON.YEARS:
            summ += res[f'Доходы {year}_0, тыс.руб'].sum()
            base_indexation.append(summ)
            total_sum.append(summ)
            base_indexation_percent.append(summ / start * 100)
    else:
        for index, year in enumerate(CON.YEARS):
            base_indexation.append(res[f'Доходы {year}_0, тыс.руб'].sum())
            total_sum.append(res[f'Доходы {year}_0, тыс.руб'].sum())
            if index == 0:
                base_indexation_percent.append(res[f'Доходы {year}_0, тыс.руб'].sum() * 100 / start)
            else:
                base_indexation_percent.append(
                    res[f'Доходы {year}_0, тыс.руб'].sum() * 100 / res[f'Доходы {year - 1}, тыс.руб'].sum())
    table_rows = [
        html.Ul(className="my-table__row", children=[
            html.Li(className="my-table__column", children=[
                html.P(children='Базовая индексация', className=f"my-table__text my-table__text_weight_bold", )
            ]),
            *[html.Li(
                className="my-table__column my-table__column_align_center my-table__column_width_120",
                children=[
                    html.P(
                        className="my-table__text my-table__text_weight_bold",
                        children=[
                            helpers.billions(base_indexation[index]),
                            html.Br(),
                            '(', '+', round(base_indexation_percent[index], 2), '%)'
                        ]
                    )
                ]) for index, year in enumerate(CON.YEARS)],

        ]),
    ]
    rules = tr.load_rules(active_only=True)
    rule_index = 0
    for rule in rules:
        rule_index += 1
        rule_indexation = []
        rule_indexation_percent = []
        if rules_type == 'Нарастающим итогом':
            summ = 0
            for index, year in enumerate(CON.YEARS):
                summ += res[f'Доходы {year}_{rule_index}, тыс.руб'].sum()
                rule_indexation.append(summ)
                total_sum[index] += summ
                rule_indexation_percent.append(summ / start * 100)
        else:
            for index, year in enumerate(CON.YEARS):
                rule_indexation.append(res[f'Доходы {year}_{rule_index}, тыс.руб'].sum())
                total_sum[index] += res[f'Доходы {year}_{rule_index}, тыс.руб'].sum()
                if index == 0:
                    rule_indexation_percent.append(res[f'Доходы {year}_{rule_index}, тыс.руб'].sum() * 100 / start)
                else:
                    rule_indexation_percent.append(res[f'Доходы {year}_{rule_index}, тыс.руб'].sum() * 100 / res[
                        f'Доходы {year - 1}, тыс.руб'].sum())
        table_rows.append(
            html.Ul(className=f"my-table__row", children=[
                html.Li(className="my-table__column", children=[
                    html.P(
                        className=f"my-table__text my-table__text_weight_bold",
                        children=rule['name'])
                ]),
                *[html.Li(
                    className="my-table__column my-table__column_align_center my-table__column_width_120",
                    children=[
                        html.P(
                            className=f"my-table__text my-table__text_weight_bold",
                            children=[
                                helpers.billions(rule_indexation[index]),
                                html.Br(),
                                '(', '+', round(rule_indexation_percent[index], 2), '%)'
                            ]
                        )
                    ]) for index, year in enumerate(CON.YEARS)],
            ])
        )

    total_percent = []
    for index, year in enumerate(CON.YEARS):
        if rules_type == 'Нарастающим итогом':
            total_percent.append(total_sum[index] * 100 / res[CON.PR_P].sum())
        else:
            total_percent.append(total_sum[index] * 100 / res[f'Доходы {year - 1}, тыс.руб'].sum())
    table_rows.append(
        html.Ul(className=f"my-table__row", children=[
            html.Li(className="my-table__column", children=[
                html.P(
                    className=f"my-table__text my-table__text_weight_bold",
                    children='ИТОГО'
                )
            ]),
            *[html.Li(
                className="my-table__column my-table__column_align_center my-table__column_width_120",
                children=[
                    html.P(
                        className=f"my-table__text my-table__text_weight_bold",
                        children=[
                            helpers.billions(total_sum[index]),
                            html.Br(),
                            '(', '+', round(total_percent[index], 2), '%)'
                        ]
                    )
                ]) for index, year in enumerate(CON.YEARS)],
        ])
    )

    table = html.Div(className="my-table my-table_margin_top", children=[
        head,
        html.Div(className="my-table__main my-table__main_type_scroll scroll my-table__main_height_450",
                 children=table_rows),
    ])
    return table


@callback(
    Output('rules_div', 'children', allow_duplicate=True),
    Input('rules_cargo', 'value'),
    Input('rules_holding', 'value'),
    Input('rules_type', 'value'),
    Input('rules_routes', 'value'),
    prevent_initial_call=True,
)
def make_rules_callback(cargo, holding, rules_type, rules_routes):
    res = make_rules(df, cargo, holding, rules_type, rules_routes)
    return res


@callback(
    Output('rules_holding', 'options'),
    Output('rules_holding', 'value'),
    Input('rules_cargo', 'value'),
    State('rules_holding', 'value'),
    prevent_initial_call=True,
)
def update_holding_options(cargo, holding):
    holdings = df.loc[df[CON.CARGO] == cargo, CON.HOLDING].unique() if cargo != None else HOLDINGS
    selected = holding if holding in holdings else None

    return (holdings, selected)


@callback(
    Output('rules_routes', 'options'),
    Output('rules_routes', 'value'),
    Input('rules_holding', 'value'),
    State('rules_cargo', 'value'),
    prevent_initial_call=True,
)
def update_routes_options(holding, cargo):
    routes = df.loc[(df[CON.CARGO] == cargo) & (df[CON.HOLDING] == holding)]
    routes = routes['Маршрут'].unique()
    if len(routes) == 0:
        routes = [{'label': 'Выберите груз и холдинг', 'value': ''}]
    # selected = holding if holding in holdings else None

    return (routes, None)


def make_routes(df, cargo, holding, type):
    if cargo and cargo != 'Все':
        df = df[df['Группа груза'] == cargo]
    if holding and holding != 'Все':
        df = df[df['Холдинг'] == holding]

    grouped = calc.group_data(df, 'Маршрут', 'Нет')
    df.loc[:, 'rules_total'] = 0
    rules = tr.load_rules(active_only=True)
    for year in CON.YEARS:
        # Формируем список столбцов с доходами за текущий год для всех правил
        year_columns = [f'Доходы {year}_{rule_index}, тыс.руб' for rule_index, _ in enumerate(rules, start=1)]
        # Суммируем значения по всем столбцам за текущий год и сохраняем результат в отдельном столбце
        grouped[f'Доходы_{year}_total'] = grouped[year_columns].sum(axis=1)
    # Вычисляем общую сумму доходов для всех лет
    grouped['rules_total'] = grouped[[f'Доходы_{year}_total' for year in CON.YEARS]].sum(axis=1)
    # Сортируем данные по общей сумме доходов
    grouped = grouped[grouped['rules_total'] != 0]
    grouped = grouped.sort_values(by='rules_total', ascending=False)
    grouped = grouped.head(10)

    head = html.Div(className="my-table__header my-table__header_type_scroll", children=[
        html.Ul(className="my-table__row ", children=[
            html.Li(className="my-table__column", children=[
                html.P(className="my-table__text my-table__text_color_grey", children='Маршрут')
            ]),
            *[html.Li(className="my-table__column my-table__column_align_center my-table__column_width_120", children=[
                html.P(className="my-table__text my-table__badge", children=f"{year} г.")
            ]) for year in CON.YEARS]
        ])
    ])

    table_rows = []
    rule_index = 0
    if len(grouped) == 0:
        table_rows.append(
            html.Ul(className=f"my-table__row", children=[
                html.Li(className="my-table__column", children=[
                    html.P(
                        className=f"my-table__text my-table__text_weight_bold",
                        children=html.Em('Отдельные решения не окажут влияние на маршруты по укзанным фильтрам'))
                ]),
            ])
        )

    for index, row in grouped.iterrows():
        totals = {}
        totals_percent = {}
        total_sum = 0
        for year in CON.YEARS:
            total_sum = 0
            if type == 'Нарастающим итогом':
                prev = 0 if year == 2025 else totals[year - 1]
                total_sum += prev
                for rule_index, rule in enumerate(rules, start=1):
                    total_sum += row[f'Доходы {year}_{rule_index}, тыс.руб']
                start = row[CON.PR_P]
            else:
                for rule_index, rule in enumerate(rules, start=1):
                    total_sum += row[f'Доходы {year}_{rule_index}, тыс.руб']
                start = row[f'Доходы {year - 1}, тыс.руб']

            totals[year] = total_sum
            totals_percent[year] = total_sum * 100 / (start + 1)

        table_rows.append(
            html.Ul(className=f"my-table__row", children=[
                html.Li(className="my-table__column", children=[
                    html.P(
                        className=f"my-table__text my-table__text_weight_bold",
                        children=row['Маршрут'])
                ]),
                *[html.Li(
                    className="my-table__column my-table__column_align_center my-table__column_width_120",
                    children=[
                        html.P(
                            className=f"my-table__text my-table__text_weight_bold",
                            children=[
                                helpers.thousands(totals[year]),
                                html.Br(),
                                '(', '+', round(totals_percent[year], 1), '%)'
                            ]
                        )
                    ]) for year in CON.YEARS],
            ])
        )

    table = html.Div(className="my-table my-table_margin_top", children=[
        head,
        html.Div(className="my-table__main my-table__main_type_scroll scroll my-table__main_height_450",
                 children=table_rows),
    ])
    return table


@callback(
    Output('routes_div', 'children', allow_duplicate=True),
    Input('routes_cargo', 'value'),
    Input('routes_holding', 'value'),
    Input('routes_type', 'value'),
    prevent_initial_call=True,
)
def make_routes_callback(cargo, holding, type):
    return make_routes(df, cargo, holding, type)


@callback(
    Output('routes_holding', 'options'),
    Output('routes_holding', 'value'),
    Input('routes_cargo', 'value'),
    State('routes_holding', 'value'),
    prevent_initial_call=True,
)
def update_holding_options_routes(cargo, holding):
    holdings = df.loc[df[CON.CARGO] == cargo, CON.HOLDING].unique() if cargo != None else HOLDINGS
    selected = holding if holding in holdings else None

    return (holdings, selected)


def make_main_table(df, params):
    plan_df = get_plan_df()
    df_part1 = plan_df.loc[:23].copy()
    df_part2 = plan_df.loc[24:].copy()
    # индексы
    revenue_parameters = get_revenue_parameters()
    indexation_variant = revenue_parameters[revenue_parameters['year'] == 0]['param'].values[0]

    # индексация % с учетом мер
    rules = tr.load_rules(active_only=True)
    df_part2.loc[24, "2025-2030"] = 1
    for year in CON.LITTLE_YEARS:
        indexation_sum = df[f'Доходы {year}_0, тыс.руб'].sum()
        prev = df[f'Доходы {year - 1}, тыс.руб'].sum()
        rules_sum = sum(df[f'Доходы {year}_{i}, тыс.руб'].sum() for i in range(1, len(rules) + 1))
        df_part2.loc[24, f"{year} прогноз"] = round(indexation_sum * 100 / prev, 1) + round(rules_sum * 100 / prev, 1)
        df_part2.loc[24, "2025-2030"] *= (1 + df_part2.loc[24, f"{year} прогноз"] / 100)
    df_part2.loc[24, "2025-2030"] = (df_part2.loc[24, "2025-2030"] - 1) * 100
    for index, year in enumerate(CON.LITTLE_YEARS):
        df_part1.loc[1, f"{year} прогноз"] = params["revenue_index_values"][index]
        df_part1.loc[2, f"{year} прогноз"] = \
            revenue_parameters[(revenue_parameters['year'] == year) & (revenue_parameters['param'] == 'indexation')][
                'value'].values[0]
        df_part1.loc[3, f"{year} прогноз"] = \
            revenue_parameters[(revenue_parameters['year'] == year) & (revenue_parameters['param'] == 'cap_rem')][
                'value'].values[0]
        df_part1.loc[4, f"{year} прогноз"] = \
            revenue_parameters[(revenue_parameters['year'] == year) & (revenue_parameters['param'] == 'tb')][
                'value'].values[0]

    df_part1.loc[1, "2025-2030"] = np.prod(params["revenue_index_values"])

    rules = tr.load_rules(active_only=True)
    new_data = {
        '№': [], 'Наименование бюджетного показателя': [], 'Ед.изм.': [],
        '2024 прогноз': [], '2025 прогноз': [], '2026 прогноз': [], '2027 прогноз': [],
        '2028 прогноз': [], '2029 прогноз': [], '2030 прогноз': [], '2025-2030': [],
        'bold': [], 'percentage': [], 'indexes': [], 'is_blue': [], 'round_digits': []
    }
    indexes = []

    for index, rule in enumerate(rules, start=1):
        total_rule = 0
        new_data['indexes'].append(f'46.{index}')
        new_data['№'].append(f'46.{index}')
        new_data['Наименование бюджетного показателя'].append(rule["name"])
        new_data['Ед.изм.'].append('млрд руб')
        new_data['2024 прогноз'].append(0)
        new_data['is_blue'].append(1)

        for year in CON.LITTLE_YEARS:
            rule_year_value = round(helpers.billions(df[f'Доходы {year}_{index}, тыс.руб'].sum()), 1)
            new_data[f'{year} прогноз'].append(rule_year_value)
            total_rule += rule_year_value
            df_part1.loc[23, f'{year} прогноз'] += rule_year_value
            df_part1.loc[22, f'{year} прогноз'] += rule_year_value
            df_part1.loc[23, '2025-2030'] += rule_year_value
            df_part1.loc[22, '2025-2030'] += rule_year_value
        new_data['2025-2030'].append(total_rule)
        new_data['bold'].append(0)
        new_data['percentage'].append(0)
        new_data['round_digits'].append(1.0)

    new_rows_df = pd.DataFrame(new_data, index=new_data['indexes'])
    result_df = pd.concat([df_part1, new_rows_df, df_part2])
    #    taxes
    #    tb
    #    invest

    rows = []
    for index, row in result_df.iterrows():
        R = int(row['round_digits'])
        color_class = "my-table__row_color_blue" if row["is_blue"] == 1 else ""
        p_class = 'my-table__text my-table__text_weight_bold' if row['bold'] == 1 else 'my-table__text'
        rows.append(
            html.Ul(className=f"my-table__row {color_class}", children=[
                html.Li(className="my-table__column my-table__column_align_center my-table__column_width_40", children=[
                    html.P(className=p_class, children=row['№'])
                ]),
                html.Li(className="my-table__column", children=[
                    html.P(className=p_class, children=row['Наименование бюджетного показателя'])
                ]),
                html.Li(className="my-table__column my-table__column_align_center my-table__column_width_120",
                        children=[
                            html.P(className=p_class, children=row['Ед.изм.'])
                        ]),
                html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60", children=[
                    html.P(className=p_class,
                           children=round(row['2024 прогноз'], R) if row['2024 прогноз'] != 0 else '')
                ]),
                html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60", children=[
                    html.P(className=p_class,
                           children=round(row['2025 прогноз'], R) if row['2025 прогноз'] != 0 else '')
                ]),
                html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60", children=[
                    html.P(className=p_class,
                           children=round(row['2026 прогноз'], R) if row['2026 прогноз'] != 0 else '')
                ]),
                html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60", children=[
                    html.P(className=p_class,
                           children=round(row['2027 прогноз'], R) if row['2027 прогноз'] != 0 else '')
                ]),
                html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60", children=[
                    html.P(className=p_class,
                           children=round(row['2028 прогноз'], R) if row['2028 прогноз'] != 0 else '')
                ]),
                html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60", children=[
                    html.P(className=p_class,
                           children=round(row['2029 прогноз'], R) if row['2029 прогноз'] != 0 else '')
                ]),
                html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60", children=[
                    html.P(className=p_class,
                           children=round(row['2030 прогноз'], R) if row['2030 прогноз'] != 0 else '')
                ]),
                html.Li(className="my-table__column my-table__column_align_center my-table__column_width_80", children=[
                    html.P(className=p_class,
                           children=round(row['2025-2030'], R) if isinstance(row['2025-2030'], (int, float)) else row[
                               '2025-2030'])
                ]),

            ])
        )
    return html.Div([
        html.Section(className='my-section mt-2', children=[
            html.Div(className='my-section__header', children=[
                html.H2(className='my-section__title',
                        children='Основные параметры финансового плана ОАО "РЖД" на 2025-2030 годы'),
            ]),
            html.Div(className='my-separate my-separate_width_600 my-separate_vector_left'),
            html.Div([
                html.Ul([
                    html.Li([
                        html.P(children='№', className='my-table__text my-table__text_color_grey')
                    ], className='my-table__column my-table__column_align_center my-table__column_width_40'),
                    html.Li([
                        html.P(children='Бюджетный показатель', className='my-table__text my-table__text_color_grey')
                    ], className='my-table__column'),
                    html.Li(className="my-table__column my-table__column_align_center my-table__column_width_120",
                            children=[
                                html.P(className="my-table__text my-table__text_color_grey", children="Ед. измерения")
                            ]),
                    html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60",
                            children=[
                                html.P(className="my-table__text my-table__text_color_grey", children="2024")
                            ]),
                    html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60",
                            children=[
                                html.P(className="my-table__text my-table__text_color_grey", children="2025")
                            ]),
                    html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60",
                            children=[
                                html.P(className="my-table__text my-table__text_color_grey", children="2026")
                            ]),
                    html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60",
                            children=[
                                html.P(className="my-table__text my-table__text_color_grey", children="2027")
                            ]),
                    html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60",
                            children=[
                                html.P(className="my-table__text my-table__text_color_grey", children="2028")
                            ]),
                    html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60",
                            children=[
                                html.P(className="my-table__text my-table__text_color_grey", children="2029")
                            ]),
                    html.Li(className="my-table__column my-table__column_align_center my-table__column_width_60",
                            children=[
                                html.P(className="my-table__text my-table__text_color_grey", children="2030")
                            ]),
                    html.Li(className="my-table__column my-table__column_align_center my-table__column_width_80",
                            children=[
                                html.P(className="my-table__text my-table__text_color_grey", children="2025-2030")
                            ]),
                ], className='my-table__row')
            ], className='my-table__header my-table__header_type_scroll'),
            html.Div(rows, className='my-table__main my-table__main_type_scroll scroll my-table__main_height_450')
        ]),
    ])
