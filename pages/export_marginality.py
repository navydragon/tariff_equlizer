import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import html, dcc, callback, ALL
from dash.dependencies import Input, Output, State

import pages.analytics.equlizer as eq
import pages.analytics.parts as parts
import pages.calculations as calc
import pages.helpers as helpers
import pages.scenario_parameters.scenario_parameters as sp
import pages.scenario_parameters.tarif_rules as tr
from pages.constants import Constants as CON
from pages.data import get_ipem_data
from pages.scenario_parameters.misc import input_states, check_and_prepare_params

dash.register_page(__name__, name="Экономика экспортных грузов", path='/export_marginality', order=6,
                   my_class='my-navbar__icon-2')

df = []

df = get_ipem_data()

ipem_calculated = []
FULL_YEARS = [2024] + CON.YEARS
tables = {}


def layout():
    return html.Div([
        sp.scenario_parameters(),
        sp.toggle_button(),

        html.Div(
            equlizer()
        ),
    ])


def equlizer():
    PRICES_DOLLAR = pd.read_excel('data/prices$.xlsx')

    export_directions = df.loc[(df['vid']=='Экспорт') & (df['typical_index'] != 0), 'Вид сообщения'].unique()


    return html.Div([
        html.Section(className='my-section', style={'margin-top': '0px'}, children=[
            dbc.Row([
                dbc.Col(html.Div(className='my-section__header', children=[
                    html.H2(className='my-section__title',
                            children='Экономика экспортных грузов', ),
                    # html.Span(className='my-section__badge', children='руб./т')
                ]), width=3),
                dbc.Col([
                    html.Ul([
                        # html.Li(html.A('Структура (табл.)', href='#pill-tab-structure-table', id='pill-structure-tab',role="tab", className='nav-link nav-pills-link active', **{'data-bs-toggle': 'tab'}), style={'margin-right':'12px'}),
                    ], className='nav nav-pills', id='pill-myTab', role='tablist')
                ], width=9)
            ]),

            html.Div(
                className='my-separate my-separate_width_600 my-separate_vector_left'),
            html.Div([

            ]),

            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Label('Направление'),
                        dcc.Dropdown(
                            id='direction_select_mgn',
                            options=export_directions,
                            searchable=True,
                            value=None,
                            placeholder=''
                        ),
                        html.Label('Вид перевозки'),
                        dcc.Dropdown(
                            id='trip_select',
                            options=['Кругорейс', 'Груженый рейс'],
                            searchable=True,
                            value='Кругорейс',
                            clearable=False
                        ),
                        dbc.Accordion(
                            [
                                dbc.AccordionItem([
                                    html.Div(
                                        [
                                            dbc.Row([
                                                dbc.Col(year, className='my-slider__text'),
                                                dbc.Col(
                                                    eq.draw_input(
                                                        type='dollar_price',
                                                        year=year,
                                                        value=PRICES_DOLLAR.loc[index, 'prices'])
                                                )
                                            ], className='my-row_type_full'),
                                            dbc.Row([
                                                dbc.Col([
                                                    eq.draw_slider(
                                                        type='dollar_price',
                                                        year=year,
                                                        value=PRICES_DOLLAR.loc[index, 'prices'],
                                                        is_vertical=False,
                                                        max=200, step=0.1,
                                                        placement="bottom",
                                                        classname="my-slider-horizontal"
                                                    )
                                                ], id={
                                                    'type': 'dollar_price_container',
                                                    'index': year},
                                                    className='text-center', style={'display': 'block'})
                                            ])
                                        ]
                                    ) for index, year in enumerate(FULL_YEARS)
                                ],
                                    title="Курс $")
                            ],
                            start_collapsed=True,
                            className='mt-3'
                        ),

                    ], id='particular_route_mgn'),

                ], width=3),
                dbc.Col([
                    html.Div([
                        html.Div([
                            dbc.Switch(id='currency_dollar_mgn', value=False,
                                       label='Цены в ₽'),
                        ], className='w-25'),
                        html.Ul([
                            html.Li(html.A('Таблицы', href='#pill-tab-structure-table',
                                           id='pill-tab-structure', role="tab",
                                           className='nav-link nav-pills-link active',
                                           **{'data-bs-toggle': 'tab'}),
                                    style={'margin-right': '12px'}),
                            #html.Li(html.A('Таблица+карта',
                            #               href='#pill-tab-structure-map',
                            #               id='pill-structure-tab2', role="tab",
                            #               className='nav-link nav-pills-link',
                            #               **{'data-bs-toggle': 'tab'}),
                            #        style={'margin-right': '12px'}),
                        ], className='nav nav-pills ml-2', id='pill-myTab',
                            role='tablist'),
                        html.Hr(),
                    ], className='d-flex flex-row mt-2 mb-2 ml-2'),
                    html.Div([
                        html.Div([
                            dcc.Loading(
                                id="loading",
                                type="default",
                                color="#e21a1a",
                                fullscreen=False,
                                children=[
                                    html.Div([html.Div(html.Em('Выберите направление'))], id='eqilizer_table_mgn')],
                            ),
                        ], id='pill-tab-structure-table', className='tab-pane fade show active', role='tabpanel'),
                        html.Div([
                            dcc.Loading(
                                id="loading",
                                type="default",
                                color="#e21a1a",
                                fullscreen=False,
                                children=[html.Div([html.Div(html.Em('Выберите направление'))], id='eqilizer_map_mgn')],
                            ),
                        ], id='pill-tab-structure-map', className='tab-pane fade show', role='tabpanel'),
                    ], className="tab-content", id="pill-myTabContent"),

                ], width=9),
            ]),

            html.Div(
                children=[html.Div([], id='eqilizer_tabs_mgn')]
            ),
        ]),

    ])


def fake_gdf(df):
    fake_df = df.copy()
    # назначение части данных себестоимости, которые можно менять
    part_ch = 0.4

    for year in fake_df["years"].to_list():
        df_w = fake_df[fake_df["years"] == year]
        df_w = df_w.to_dict('records')
        dict_df_w = df_w[0]

        hvost = (dict_df_w['costs'] * (part_ch))
        list_to_sum = [
            'marginality',
            'rzd',
            'oper',
            'per',
            'fraht'
        ]
        count_n = 0
        for i in list_to_sum:
            if dict_df_w[i] != 0:
                count_n = count_n + 1
            else:
                pass
        for i in list_to_sum:
            if dict_df_w[i] != 0:
                dict_df_w[i] = dict_df_w[i] + round((hvost / count_n), 2)
            else:
                pass

        dict_df_w['costs'] = dict_df_w['costs'] * (1 - part_ch)
        for key, value in dict_df_w.items():
            fake_df.loc[fake_df["years"] == year, key] = value

    return fake_df


@callback(
    Output('eqilizer_table_mgn', 'children', allow_duplicate=True),
    Output('eqilizer_map_mgn', 'children', allow_duplicate=True),
    Input('direction_select_mgn', 'value'),
    Input({'type': 'dollar_price_input', 'index': ALL}, 'value'),
    Input('currency_dollar_mgn', 'value'),
    Input('trip_select', 'value'),
    prevent_initial_call=True
)
def recount_graph(direction, dollar_prices,
                  currency_dollar_mgn,
                  trip):
    period = FULL_YEARS
    global tables
    tables = {}
    no = html.Div(html.Em('Выберите направление'))

    if direction is None or dollar_prices == []: return (no, no)

    condition = ipem_calculated['Вид сообщения'] == direction
    typical_indexes = ipem_calculated[condition]['typical_index'].unique()

    condition = ipem_calculated['index'].isin(typical_indexes)
    routes = ipem_calculated[condition]
    routes = routes.sort_values(by='Код группы', ascending=True)
    routes = routes.drop_duplicates()
    rules_suffix = '_gr' if trip == 'Груженый рейс' else ''

    result = []

    for index, current_route in routes.iterrows():
        structure_table = count_mgn_table(current_route, rules_suffix, direction, dollar_prices, trip,
                                          currency_dollar_mgn)
        result.append(html.H3(current_route['Группа груза']))
        result.append(structure_table)
        tables[current_route['Группа груза']] = count_mgn_table(current_route, rules_suffix, direction, dollar_prices,
                                                                trip, currency_dollar_mgn, 'map')

    result_map = html.Div([
        html.Label('Группа груза'),
        dcc.Dropdown(
            id='cargo_select_mgn',
            options=[value for value in routes['Группа груза'].unique()],
            searchable=True,
            value=None,
            placeholder=''
        ),
        html.Div([], id='map_div'),
        html.Div([], id='single_table_div'),
    ])

    return (
        html.Div(result, style={'max-height': '65vh', 'overflow-y': 'scroll'}),
        html.Div(result_map, style={'max-height': '65vh', 'min-height': '65vh', 'overflow-y': 'scroll'})
    )


def make_tabs(route, trip, message, price_message, period, cif_fob):
    PRICES_DOLLAR = pd.read_excel('data/prices$.xlsx')
    is_export = 'block' if message != 'внутренние' else 'none'
    is_fraht = 'block' if (cif_fob == 'CIF') and (message != 'внутренние') else 'none'
    is_internal = 'block' if message == 'внутренние' else 'none'

    rules_suffix = '_gr' if trip == 'Груженый рейс' else ''

    res = dcc.Tabs(
        id="tabs-with-classes",
        value='tab-2',
        parent_className='custom-tabs',
        className='custom-tabs-container',
        vertical=True,
        children=[
            dcc.Tab(
                label='Курс_$',
                value='tab-7',
                className='custom-tab',
                selected_className='custom-tab--selected',
                style={'display': is_export},
                children=[html.Div([
                    html.Div(
                        className='my-section__header',
                        children=[
                            html.H2(className='my-section__title',
                                    children='Курс доллара к рублю'),
                            html.Span(className='my-section__badge',
                                      children='руб. за 1 $')
                        ]
                    ),
                    dbc.Row([*[dbc.Col(
                        year, className='my-slider__text',
                        style={'display': 'block'} if year in period else {'display': 'none'}
                    ) for year in FULL_YEARS]],
                            className='my-row_type_full'),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_input(type='dollar_price', year=year, value=PRICES_DOLLAR.loc[index, 'prices'])
                        ], className='text-center',
                            style={'display': 'block'} if year in period else {'display': 'none'}
                        ) for index, year in enumerate(FULL_YEARS)]
                    ], className='my-row_type_full'),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_slider(type='dollar_price', year=year, value=PRICES_DOLLAR.loc[index, 'prices'],
                                           max=200, step=0.1)
                        ], id={'type': 'dollar_price_container', 'index': year},
                            className='text-center',
                            style={'display': 'block'} if year in period else {'display': 'none'}
                        ) for index, year in enumerate(FULL_YEARS)]
                    ]),
                ])]
            ),
        ])

    return res


def effects_table(route, rzd, bases, rules, trip_type):
    # bases = bases[1:]
    # rules = rules[1:]
    suffix = '_gr' if trip_type == 'Груженый рейс' else ''
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
    table_rows = [
        html.Ul(className="my-table__row", children=[
            html.Li(className="my-table__column", children=[
                html.P(children='Совокупная тарифная нагрузка',
                       className=f"my-table__text my-table__text_weight_bold", )
            ]),
            *[html.Li(
                className="my-table__column my-table__column_align_center my-table__column_width_120",
                children=[
                    html.P(
                        className="my-table__text my-table__text_weight_bold",
                        children=[
                            round(
                                rzd[index - 1] * (route[f'rules%_{year}{suffix}'].values[0] - 1) + rzd[index - 1] * (
                                            bases[index] - 1)
                                , 2),
                            html.Br(),
                            '(', '+', round(
                                (rzd[index - 1] * (route[f'rules%_{year}{suffix}'].values[0] - 1) + rzd[index - 1] * (
                                            bases[index] - 1))
                                * 100 / rzd[index - 1], 2),
                            '%)'
                        ]
                    )
                ]) for index, year in enumerate(CON.YEARS, start=1)],

        ]),
        html.Ul(className="my-table__row", children=[
            html.Li(className="my-table__column", children=[
                html.P(children='Базовая индексация с надбавками',
                       className=f"my-table__text my-table__text_weight_bold", )
            ]),
            *[html.Li(
                className="my-table__column my-table__column_align_center my-table__column_width_120",
                children=[
                    html.P(
                        className="my-table__text my-table__text_weight_bold",
                        children=[
                            round(rzd[index - 1] * (bases[index] - 1), 2),
                            html.Br(),
                            '(', '+', round(rzd[index - 1] * (bases[index] - 1) * 100 / rzd[index - 1], 2),
                            '%)'
                        ]
                    )
                ]) for index, year in enumerate(CON.YEARS, start=1)],

        ]),
        html.Ul(className="my-table__row", children=[
            html.Li(className="my-table__column", children=[
                html.P(children='Тарифные решения, в т.ч.', className=f"my-table__text my-table__text_weight_bold", )
            ]),
            *[html.Li(
                className="my-table__column my-table__column_align_center my-table__column_width_120",
                children=[
                    html.P(
                        className="my-table__text my-table__text_weight_bold",
                        children=[
                            round(rzd[index - 1] * (route[f'rules%_{year}{suffix}'].values[0] - 1), 2),
                            html.Br(),
                            '(', '+', round(
                                rzd[index - 1] * (route[f'rules%_{year}{suffix}'].values[0] - 1) * 100 / rzd[index - 1],
                                2),
                            '%)'
                        ]
                    )
                ]) for index, year in enumerate(CON.YEARS, start=1)],
        ]),
    ]
    rules = tr.load_rules(active_only=True)
    for rule_index, rule in enumerate(rules, start=1):
        rule_sum = 0
        for index, year in enumerate(CON.YEARS, start=1):
            rule_sum += route[f'rules%_{year}_{rule_index}{suffix}'].values[0]
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
                                round(rzd[index - 1] * route[f'rules%_{year}_{rule_index}{suffix}'].values[0], 2),
                                html.Br(),
                                '(', round(route[f'rules%_{year}_{rule_index}{suffix}'].values[0] * 100, 2), '%)'
                            ]
                        )
                    ]) for index, year in enumerate(CON.YEARS, start=1)],
            ])
        ) if rule_sum > 0 else None
    table = html.Div(className="my-table my-table_margin_top", children=[
        head,
        html.Div(
            className="my-table__main my-table__main_type_scroll scroll my-table__main_height_450",
            children=table_rows),
    ])
    return table


outputs = [
    Output('direction_select_mgn', 'value')
]
inputs = [] + input_states
args = outputs + inputs


@callback(*args,)
def update_transport(
        calculate_button,
        epl_change, market_loss,
        cif_fob,
        index_sell_prices, price_variant, index_sell_coal, index_oper, index_per,
        *revenue_index_values
):
    params = check_and_prepare_params(
        epl_change, market_loss, cif_fob, index_sell_prices, price_variant, index_sell_coal,
        index_oper, index_per, revenue_index_values
    )

    helpers.save_last_params(params)
    global ipem_calculated
    ipem_calculated = calc.calculate_data_ipem([], [], params)

    return None


@callback(
    Output('map_div', 'children'),
    Output('single_table_div', 'children'),
    Input('cargo_select_mgn', 'value'),
    State('direction_select_mgn', 'value'),
    prevent_initial_call=True,
)
def draw_single_table_map(cargo_group, direction):
    condition = (ipem_calculated['Вид сообщения'] == direction) & (ipem_calculated['Группа груза'] == cargo_group)
    typical_indexes = ipem_calculated[condition]['typical_index'].unique()

    condition = ipem_calculated['index'] == typical_indexes[0]
    route = ipem_calculated[condition]

    table = tables.get(route['Группа груза'].values[0])
    map = html.Div(children=dcc.Graph(figure=parts.route_map(route)))
    return (map, table)


@callback(
    Output('currency_dollar_mgn', 'label'),
    Input('currency_dollar_mgn', 'value'),
)
def switch_table_currency(value):
    if value == False:
        return 'Цены в ₽'
    return 'Цены в $'


def count_mgn_table(current_route, rules_suffix, direction, dollar_prices, trip, currency_dollar_mgn, key=''):
    costs = []
    rules = []
    bases = []
    prices_rub = []
    prices = []
    oper = []
    per = []
    fraht = []

    for index, year in enumerate(FULL_YEARS):
        costs.append(round(current_route[f'Себестоимость добычи/производства, руб. т.'], 3))
        rules.append(current_route[f"rules%_{year}{rules_suffix}"])
        bases.append(round(current_route[f"base%_{year}"], 3))
        oper.append(round(current_route[f"Расходы по оплате услуг операторов_{year}, руб. за тонну"], 3))
        per.append(round(current_route[f"Расходы на перевалку_{year}, руб. за тонну"], 3))
        fraht.append(round(current_route[f"fraht_{year}"], 3))
        prices.append(round(current_route[f'Стоимость 1 тонны на рынке_{year}_$, руб./т.'], 3))
        prices_rub.append(round(current_route[f'Стоимость 1 тонны на рынке_{year}, руб./т.'], 3))
    rzd = []
    rzd_gr = []
    rzd_por = []

    price_rub = []
    marginality = []
    marginality_real = []
    marginality_real_percent = []

    transport = []
    years = []
    if trip == 'Кругорейс':
        trip_col = CON.RZD_TOTAL
        oper_coeff = 1
    else:
        trip_col = CON.RZD_GR
        gr_sr = current_route['Срок доставки, гружёный рейс']
        pr_sr = current_route['Срок доставки,порожний рейс']
        per_sr = current_route['Срок доставки, погр./выгр.']
        oper_coeff = gr_sr / (gr_sr + pr_sr + per_sr)

    for index, year in enumerate(FULL_YEARS):

        if year == 2024:
            rzd.append(current_route[f'{trip_col}_{year}'])

            rzd_gr.append(current_route[f'{CON.RZD_GR}_{year}'])
            if trip == 'Кругорейс':
                rzd_por.append(current_route[f'{CON.RZD_POR}_{year}'])

        else:
            rzd_val = rzd[-1] + rzd[-1] * (bases[index] - 1) + rzd[-1] * (rules[index] - 1)
            rzd.append(round(rzd_val, 2))
            rzd_gr_val = rzd_gr[-1] + rzd_gr[-1] * (bases[index] - 1) + rzd_gr[-1] * (
                        current_route[f'rules%_{year}_gr'] - 1)
            rzd_gr.append(round(rzd_gr_val, 2))
            if trip == 'Кругорейс':
                rzd_por_val = rzd_por[-1] + rzd_por[-1] * (bases[index] - 1) + rzd_por[-1] * (
                            current_route[f'rules%_{year}_por'] - 1)
                if current_route['Группа груза'] == 'Удобрения':
                    print(current_route[f'rules%_{year}_por'])
                rzd_por.append(round(rzd_por_val, 2))

        year_price = prices_rub[index] if direction == 'внутренние' else prices[index] * dollar_prices[index]

        price_rub.append(year_price)
        year_marginality = price_rub[index] - costs[index] - rzd[index] - per[index] - oper[index] - fraht[index]
        marginality_real.append(year_marginality)
        marginality_real_percent.append(year_marginality * 100 / price_rub[index])

        marginality.append(year_marginality if year_marginality > 0 else 0)

    years = FULL_YEARS
    costs = costs
    bases = bases

    oper = [val * oper_coeff for val in oper]
    per = per
    for index, year in enumerate(FULL_YEARS):
        transport.append(rzd[index] + per[index] + oper[index] + fraht[index])

    test_df = pd.DataFrame({
        'years': years, 'costs': costs, 'oper': oper, 'per': per, 'rzd': rzd, 'fraht': fraht,
        'marginality': marginality,
    })

    gdf = test_df.set_index('years').div(test_df.set_index('years').sum(axis=1), axis=0) * 100
    gdf = gdf.round(2).reset_index()


    test_df_tr = pd.DataFrame({
        'years': years, 'costs': costs, 'transport': transport, 'marginality': marginality
    })
    gdf_tr = test_df_tr.set_index('years').div(test_df_tr.set_index('years').sum(axis=1), axis=0) * 100
    gdf_tr = gdf_tr.round(2).reset_index()

    test_df2 = test_df.drop('rzd', axis=1)
    test_df2['rzd_gr'] = rzd_gr
    if trip == 'Кругорейс':
        test_df2['rzd_por'] = rzd_por

    gdf2 = test_df2.set_index('years').div(test_df2.set_index('years').sum(axis=1), axis=0) * 100
    gdf2 = gdf2.round(2).reset_index()
    test_df2['transport'] = test_df_tr['transport']
    gdf2['transport'] = gdf_tr['transport']

    structure_table = parts.make_structure_table(current_route, test_df, test_df2, gdf, test_df_tr, years, costs, bases,
                                                 rules, oper, per, prices, price_rub, dollar_prices, fraht, trip,
                                                 marginality_real, marginality_real_percent, currency_dollar_mgn, key)
    return structure_table
