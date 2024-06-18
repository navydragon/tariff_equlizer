import dash

from dash import html, dcc, callback, ALL, MATCH
from dash.dependencies import Input, Output, State
from pages.data import get_ipem_data, get_main_data, calculate_total_index, get_ipem_csr_data
import dash_bootstrap_components as dbc

import plotly.graph_objects as go

import pandas as pd
import pages.helpers as helpers
import pages.calculations_csr as calc
from pages.constants import Constants as CON
import pages.scenario_parameters.tarif_rules as tr
import pages.scenario_parameters.scenario_parameters as sp
import pages.analytics.equlizer as eq
import pages.analytics.parts as parts

dash.register_page(__name__, name="Тарифный эквалайзер ЦСР", path='/equlizer_csr', order=3, my_class='my-navbar__icon-2')


df = []

df = get_ipem_csr_data()

ipem_calculated = []
FULL_YEARS = [2024] + CON.YEARS


def layout():
    return html.Div([
        sp.scenario_parameters(),
        sp.toggle_button(),

        html.Div(
            equlizer()
        ),
    ])



def equlizer():
    return html.Div([
        html.Section(className='my-section', style={'margin-top':'0px'}, children=[
            dbc.Row([
                dbc.Col(html.Div(className='my-section__header', children=[
                    html.H2(className='my-section__title',
                            children='Тарифный эквалайзер', ),
                    # html.Span(className='my-section__badge', children='руб./т')
                ]),width=3),
                dbc.Col([
                    html.Ul([
                            html.Li(html.A('Тренды', href='#pill-tab-trends', id='pill-trends-tab', role="tab", className='nav-link nav-pills-link active',  **{'data-bs-toggle': 'tab'}), style={'margin-right':'12px'}),
                            html.Li(html.A('Структура', href='#pill-tab-structure', id='pill-structure-tab',role="tab", className='nav-link nav-pills-link', **{'data-bs-toggle': 'tab'}), style={'margin-right':'12px'}),
                            html.Li(html.A('Структура (табл.)', href='#pill-tab-structure-table', id='pill-structure-tab',role="tab", className='nav-link nav-pills-link', **{'data-bs-toggle': 'tab'}), style={'margin-right':'12px'}),
                            html.Li(html.A('Структура укрупненная', href='#pill-tab-structure-v', id='pill-structure-v-tab',role="tab", className='nav-link nav-pills-link', **{'data-bs-toggle': 'tab'}), style={'margin-right':'12px'}),
                            html.Li(html.A('Структура ТС', href='#pill-tab-structure-ts', id='pill-structure-v-tab',role="tab", className='nav-link nav-pills-link', **{'data-bs-toggle': 'tab'}), style={'margin-right':'12px'}),
                            # html.Li(html.A('Ключевые показатели', href='#pill-tab-kpi', id='pill-kpi-tab',role="tab", className='nav-link nav-pills-link', **{'data-bs-toggle': 'tab'}), style={'margin-right':'12px'}),
                            html.Li(html.A('Эффект от решений', href='#pill-tab-effects', id='pill-effects-tab',role="tab", className='nav-link nav-pills-link', **{'data-bs-toggle': 'tab'}), style={'margin-right':'12px'}),
                    ], className='nav nav-pills', id='pill-myTab', role='tablist')
                ],width=9)
            ]),

            html.Div(
                className='my-separate my-separate_width_600 my-separate_vector_left'),
            html.Div([

            ]),

            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Label('Груз'),
                        dcc.Dropdown(
                            id='cargo_select',
                            options=df['Груз'].unique(),
                            searchable=True,
                            value=None,
                            placeholder='Выберите груз'
                        ),
                        html.Label('Вид сообщения'),
                        dcc.Dropdown(
                            id='message_select_csr',
                            options=df['Вид сообщения'].unique(),
                            searchable=True,
                            value=None,
                            disabled=True,
                            placeholder=''
                        ),

                        html.Label('Маршрут'),
                        dcc.Dropdown(
                            id='route_select_csr',
                            options=df['route'].unique(),
                            searchable=True,
                            value=None,
                            disabled=True,
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

                    ], id='particular_route_csr'),
                    html.Label('Период'),
                    dcc.Dropdown(
                        id='period_select_csr',
                        options=FULL_YEARS,
                        #searchable=True,
                        value=FULL_YEARS,
                        #inline=True,
                        multi=True,
                        clearable=False
                    ),
                ], width=3),
                dbc.Col([
                    html.Div([
                        html.Div([
                            dcc.Loading(
                                id="loading",
                                type="default",
                                color="#e21a1a",
                                fullscreen=False,
                                children=[html.Div([
                                    html.Div(html.Em(
                                        'Последовательно выберите груз, холдинг, вид сообщения и маршрут'))
                                ], id='equlizer_trends_csr')],
                            ),
                        ], id='pill-tab-trends', className='tab-pane fade show active', role='tabpanel'),
                        html.Div([
                            dcc.Loading(
                                id="loading",
                                type="default",
                                color="#e21a1a",
                                fullscreen=False,
                                children=[html.Div([], id='eqilizer_graph_csr')],
                            ),
                        ], id='pill-tab-structure', className='tab-pane fade show', role='tabpanel'),
                        html.Div([
                            html.Div([
                                dbc.Switch(id='currency_dollar_csr', value=False, label='Цены в ₽'),
                                html.Hr(),
                            ], className='d-flex flex-row mt-2 mb-2 ml-2'),
                            dcc.Loading(
                                id="loading",
                                type="default",
                                color="#e21a1a",
                                fullscreen=False,
                                children=[html.Div([], id='eqilizer_table_csr')],
                            ),
                        ], id='pill-tab-structure-table', className='tab-pane fade show', role='tabpanel'),
                        html.Div([
                            dcc.Loading(
                                id="loading",
                                type="default",
                                color="#e21a1a",
                                fullscreen=False,
                                children=[html.Div([], id='eqilizer_graph_csrv')],
                            ),
                        ], id='pill-tab-structure-v', className='tab-pane fade show', role='tabpanel'),
                        html.Div([
                            dcc.Loading(
                                id="loading",
                                type="default",
                                color="#e21a1a",
                                fullscreen=False,
                                children=[html.Div([
                                    html.Div(html.Em(
                                        'Последовательно выберите груз, холдинг, вид сообщения и маршрут'))
                                ], id='eqilizer_ts_csr')],
                            ),
                        ], id='pill-tab-structure-ts', className='tab-pane fade show',
                            role='tabpanel'),
                        # html.Div([
                        #     dcc.Loading(
                        #         id="loading",
                        #         type="default",
                        #         color="#e21a1a",
                        #         fullscreen=False,
                        #         children=[html.Div([
                        #             html.Div(html.Em(
                        #                 'Последовательно выберите груз, холдинг, вид сообщения и маршрут'))
                        #         ], id='equlizer_kpi_csr')],
                        #     ),
                        # ], id='pill-tab-kpi', className='tab-pane fade show', role='tabpanel'),
                        html.Div([
                            dcc.Loading(
                                id="loading",
                                type="default",
                                color="#e21a1a",
                                fullscreen=False,
                                children=[html.Div([
                                    html.Div(html.Em(
                                        'Последовательно выберите груз, холдинг, вид сообщения и маршрут'))
                                ], id='equlizer_effects_csr')],
                            ),
                        ], id='pill-tab-effects', className='tab-pane fade show', role='tabpanel')
                    ], className="tab-content", id="pill-myTabContent"),

                ], width=9),
            ]),

            html.Div(
                children=[html.Div([], id='eqilizer_tabs_csr')]
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

def fake_gdf_tr(df):
    fake_df = df.copy()
    # назначение части данных себестоимости, которые можно менять
    part_ch = 0.2

    for year in fake_df["years"].to_list():
        df_w = fake_df[fake_df["years"] == year]
        df_w = df_w.to_dict('records')
        dict_df_w = df_w[0]

        hvost = (dict_df_w['costs'] * (part_ch))
        list_to_sum = [
            'transport',
            'marginality',
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
    Output('eqilizer_tabs_csr','children'),
    Output('eqilizer_graph_csr','children'),
    Input('route_select_csr','value'),
    Input('trip_select','value'),

    Input('period_select_csr', 'value'),
    State('message_select_csr','value'),
    State('index_sell_prices','value'),
    State('price_variant','value'),
    State('cif_fob','value'),
)
def update_equlizer(route,trip,period,message, prices_change, prices_variant, cif_fob):
    period = sorted(period)

    no = html.Div(html.Em('Последовательно выберите груз, холдинг, вид сообщения и маршрут'))
    prices_message = get_prices_message(prices_change,prices_variant)

    if route is None: return ([],no)
    current_route = ipem_calculated[ipem_calculated['route'] == route]


    tabs = html.Div(make_tabs(current_route,trip, message, prices_message, period, cif_fob))
    return (tabs,[])


@callback(
    Output('eqilizer_graph_csr','children', allow_duplicate=True),
    Output('equlizer_trends_csr','children', allow_duplicate=True),
    Output('eqilizer_graph_csrv','children', allow_duplicate=True),
    Output('eqilizer_ts_csr','children', allow_duplicate=True),
    # Output('equlizer_kpi_csr','children', allow_duplicate=True),
    Output('equlizer_effects_csr','children', allow_duplicate=True),
    Output('eqilizer_table_csr','children', allow_duplicate=True),
    Input({'type': 'cost_input', 'index': ALL}, 'value'),
    Input({'type': 'base_input', 'index': ALL}, 'value'),
    Input({'type': 'rules_input', 'index': ALL}, 'value'),
    Input({'type': 'oper_input', 'index': ALL}, 'value'),
    Input({'type': 'per_input', 'index': ALL}, 'value'),
    Input({'type': 'price_input', 'index': ALL}, 'value'),
    Input({'type': 'price_rub_input', 'index': ALL}, 'value'),
    Input({'type': 'dollar_price_input', 'index': ALL}, 'value'),
    Input({'type': 'fraht_input', 'index': ALL}, 'value'),
    Input('currency_dollar_csr', 'value'),
    State('trip_select', 'value'),
    State('period_select_csr', 'value'),
    State('route_select_csr','value'),
    State('message_select_csr','value'),
    prevent_initial_call=True
)
def recount_graph(costs,bases, rules,
                  oper,per,prices,prices_rub,dollar_prices, fraht,
                  currency_dollar_csr,
                  trip,period, route,message,key=''):
    period = sorted(period)

    no = html.Div(html.Em('Последовательно выберите груз, холдинг, вид сообщения и маршрут'))

    if route is None:
        return (no,no,no,no,no,no)
    current_route = ipem_calculated[ipem_calculated['route'] == route]

    names = [
        'Маржинальность холдинга',
        'Себестоимость производства',
        'Расходы на оплату услуг ОАО "РЖД"',
        'Расходы по оплате услуг операторов',
        'Расходы на перевалку',
        'Расходы на фрахт'
    ]
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
        gr_sr = current_route.iloc[0]['Срок доставки, гружёный рейс'].round()
        pr_sr = current_route.iloc[0]['Срок доставки,порожний рейс'].round()
        per_sr = current_route.iloc[0]['Срок доставки, погр./выгр.'].round()
        oper_coeff =  gr_sr / (gr_sr + pr_sr + per_sr)



    for index,year in enumerate(FULL_YEARS):

        if year == 2024:
            rzd.append(current_route.iloc[0][f'{trip_col}_{year}'].round(2))

            rzd_gr.append(current_route.iloc[0][f'{CON.RZD_GR}_{year}'].round(2))
            if trip=='Кругорейс':
                rzd_por.append(current_route.iloc[0][f'{CON.RZD_POR}_{year}'].round(2))

        else:
            rzd_val = rzd[-1] + rzd[-1]*(bases[index]-1) + rzd[-1]*(rules[index]-1)
            rzd.append(rzd_val)
            rzd_gr_val = rzd_gr[-1] + rzd_gr[-1]*(bases[index]-1) + rzd_gr[-1]*(current_route.iloc[0][f'rules%_{year}_gr']-1)
            rzd_gr.append(rzd_gr_val)
            if trip == 'Кругорейс':
                rzd_por_val = rzd_por[-1] + rzd_por[-1]*(bases[index]-1) + rzd_por[-1]*(current_route.iloc[0][f'rules%_{year}_por']-1)
                rzd_por.append(rzd_por_val)


        year_price = prices_rub[index] if message == 'внутренние' else prices[index]*dollar_prices[index]


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
    for index,year in enumerate(FULL_YEARS):
        transport.append(rzd[index]+per[index]+oper[index]+fraht[index])


    test_df = pd.DataFrame({
                'years': years, 'costs': costs, 'oper':oper, 'per': per, 'rzd':rzd, 'fraht':fraht,
        'marginality':marginality,
    })

    gdf = test_df.set_index('years').div(test_df.set_index('years').sum(axis=1), axis=0) * 100
    gdf = gdf.round(2).reset_index()

    fgdf = fake_gdf(gdf)


    test_df_tr = pd.DataFrame({
        'years': years, 'costs': costs, 'transport':transport, 'marginality':marginality
    })
    gdf_tr = test_df_tr.set_index('years').div(test_df_tr.set_index('years').sum(axis=1), axis=0) * 100
    gdf_tr = gdf_tr.round(2).reset_index()

    fgdf_tr = fake_gdf_tr(gdf_tr)


    test_df2 = test_df.drop('rzd', axis=1)
    test_df2['rzd_gr'] = rzd_gr
    if trip == 'Кругорейс':
        test_df2['rzd_por'] = rzd_por

    gdf2 = test_df2.set_index('years').div(test_df2.set_index('years').sum(axis=1), axis=0) * 100
    gdf2 = gdf2.round(2).reset_index()
    test_df2['transport'] = test_df_tr['transport']
    gdf2['transport'] = gdf_tr['transport']

    colors1=['#44445A','#161B77','#3B4FB1','#4274D6','#6DA4C1','#BE7D64']

    colors = ['#4fb4ff','#0091fe','#0072c8','#005da2','#004d86','#003256']

    width=0.9

    fig = graph_bar_h(test_df, gdf, fgdf, marginality, period, colors, width,names)
    fig2 = graph_bar_trend(test_df, gdf, marginality, period, colors, width,names)

    fig3 = graph_bar_v(test_df_tr, gdf_tr, fgdf_tr, marginality, period, colors, width,names)
    fig4 = graph_bar_ts(test_df2, gdf2, marginality, period, colors, width,names, trip)


    graph = html.Div([dcc.Graph(figure=fig)], id='cargo-graph')
    graph2 = html.Div([dcc.Graph(figure=fig2)], id='cargo-graph2')
    graph3 = html.Div([dcc.Graph(figure=fig3)], id='cargo-graph3')
    graph4 = html.Div([dcc.Graph(figure=fig4)], id='cargo-graph4')

    cards = []
    main_df = get_main_data()
    key = current_route['ipem_gr'].values[0]
    main_row = main_df.loc[main_df['Ключ ИПЕМ']==key]
    main_row = main_row.groupby(['Группа груза','Холдинг']).sum().reset_index()
    main_row = main_row.iloc[0]

    conditions = (main_df['Группа груза'] == main_row['Группа груза']) & (main_df['Холдинг'] == main_row['Холдинг'])
    all_rows = main_df.loc[conditions].sum()

    for index,row in test_df.loc[1:].iterrows():
        gdf_row = gdf.loc[index]
        tr = round(row['rzd'] + row['oper'] + row['per'])
        tr_perc = round(gdf_row['rzd'] + gdf_row['oper'] + gdf_row['per'],2)
        year = row['years']
        prev_year_row = gdf.loc[test_df['years']==year-1]
        tr_perc_prev = round(prev_year_row['rzd'].iloc[0] + prev_year_row['oper'].iloc[0] + prev_year_row['per'].iloc[0],2)
        rzd_change = round (gdf_row['rzd'] - prev_year_row['rzd'].iloc[0],2)
        rzd_plus = '+' if rzd_change > 0 else ''
        tr_change = round(tr_perc - tr_perc_prev,2)

        tr_plus = '+' if tr_change > 0 else ''
        mg_change = round(gdf_row['marginality'] - prev_year_row['marginality'].iloc[0],2)
        mg_plus = '+' if mg_change > 0 else ''

        year = int(year)
        coef = main_row[f'{year} ЦЭКР груззоборот, тыс ткм'] / main_row['2024 ЦЭКР груззоборот, тыс ткм']
        ep_perc = round(main_row[f'{year} ЦЭКР груззоборот, тыс ткм'] * 100 / all_rows[f'{year} ЦЭКР груззоборот, тыс ткм'],2)
        ep_val = round(main_row['2023 Объем перевозок, т.'] / 1000 * coef,2)

        # cards.append(
        #     html.Div(className="my-card__item", style={"background-color":"#F4F7FE"}, children=[
        #         html.Div(className="my-card__caption",
        #                  children=f"{int(row['years'])} год"),
        #         html.Div(className="my-card__body",  children=[
        #             html.Div(className="custom-card__list", children=[
        #                 html.Div(className="custom-card__item", children=[
        #                     html.Div(className="custom-card__row", children=[
        #                         html.P(className="custom-card__procent",
        #                                children=f"{tr_perc}%",
        #                                style={'display': 'inline-block'}),
        #                         html.P(
        #                             className="custom-card__text custom-card__text-count",
        #                             children=f"{tr} руб.",
        #                         ),
        #                     ]),
        #                     html.P(
        #                         className="custom-card__text",
        #                         children='Транспортная составляющая',
        #                     ),
        #                 ]),
        #                 html.Div(className="custom-card__item", children=[
        #                     html.Div(className="custom-card__row", children=[
        #                         html.P(className="custom-card__procent",
        #                                children=f"{gdf_row['rzd']}%",
        #                                style={'display': 'inline-block'}),
        #                         html.P(
        #                             className="custom-card__text custom-card__text-count",
        #                             children=f" {round(test_df.loc[index, 'rzd'])} руб.",
        #                         ),
        #                     ]),
        #                     html.P(
        #                         className="custom-card__text",
        #                         children='Расходы на оплату услуг ОАО "РЖД"',
        #                     ),
        #                 ]),
        #                 html.Div(className="custom-card__item", children=[
        #                     html.Div(className="custom-card__row", children=[
        #                         html.P(className="custom-card__procent",
        #                                children=f"{ep_perc}%",
        #                                style={'display': 'inline-block'}),
        #                         html.P(
        #                             className="custom-card__text custom-card__text-count",
        #                             children=f" {ep_val} тыс. т.",
        #                         ),
        #
        #                     ]),
        #                     html.P(
        #                         className="custom-card__text",
        #                         children='Доля в объеме перевозок',
        #                     ),
        #                 ]),
        #                 html.Div(className="custom-card__item", children=[
        #                     html.Div(className="custom-card__row", children=[
        #                         html.P(className="custom-card__procent",
        #                                children=f"{gdf_row['marginality']}%",
        #                                style={'display': 'inline-block'}),
        #                         html.P(
        #                             className="custom-card__text custom-card__text-count",
        #                             children=f" {round(test_df.loc[index, 'marginality'])} руб.",
        #                         ),
        #                     ]),
        #                     html.P(
        #                         className="custom-card__text",
        #                         children='Маржинальность грузоотправителя',
        #                     ),
        #                 ]),
        #
        #             ]),
        #         ]),
        #     ]),
        # )
    # cards = html.Div(className="my-cards", children=cards)
    # map = html.Div(children=dcc.Graph(figure=parts.route_map(current_route)))
    # kpi = html.Div([
    #     map,
    #     cards
    # ])
    effects = parts.effects_table(current_route,rzd,bases,rules, trip)
    current_route = current_route.iloc[0]
    structure_table = parts.make_structure_table(current_route,test_df,test_df2,gdf, test_df_tr, years,costs,bases, rules,oper,per,prices,price_rub,dollar_prices, fraht, trip, marginality_real, marginality_real_percent,currency_dollar_csr,key)
    return (graph, graph2, graph3, graph4, effects, structure_table)



def make_tabs(route,trip, message, price_message,period,cif_fob):

    PRICES_DOLLAR = pd.read_excel('data/prices$.xlsx')
    is_export = 'block' if message != 'внутренние' else 'none'
    is_fraht = 'block' if (cif_fob == 'CIF')and(message != 'внутренние') else 'none'
    is_internal = 'block' if message == 'внутренние' else 'none'
    cost = round(route.iloc[0]['Себестоимость добычи/производства, руб. т.'])
    rules_suffix = '_gr' if trip == 'Груженый рейс' else ''

    res = dcc.Tabs(
        id="tabs-with-classes",
        value='tab-2',
        parent_className='custom-tabs',
        className='custom-tabs-container',
        vertical=True,
        children=[
            dcc.Tab(
                label='Индексация',
                value='tab-2',
                className='custom-tab',
                selected_className='custom-tab--selected',
                children=[html.Div([
                    html.Div(
                        className='my-section__header',
                        children=[
                            html.H2(className='my-section__title',children='Базовая индексация'),
                            html.Span(className='my-section__badge', children='Индекс')
                        ]
                    ),
                    dbc.Row([ *[dbc.Col(year, className='my-slider__text', style={'display':'block'} if year in period else {'display':'none'}) for year in FULL_YEARS]], className='my-row_type_full'),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_input(type='base',year=year,value=round(route.iloc[0][f"base%_{year}"],3))
                        ], className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ], className='my-row_type_full'),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_slider(type='base',year=year,value=round(route.iloc[0][f"base%_{year}"],3), step=0.001)
                        ], id={'type': 'base_container', 'index': year}, className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ], className='my-row_type_full'),
                ], className='mx-5')]
            ),
            dcc.Tab(
                label='Тарифные решения',
                value='tab-3', className='custom-tab',
                selected_className='custom-tab--selected',
                style={'display':'none'},
                children=[html.Div([
                    html.Div(
                        className='my-section__header',
                        children=[
                            html.H2(className='my-section__title',children='Отдельные тарифные решения'),
                            html.Span(className='my-section__badge', children='руб. за 1 т.')
                        ]
                    ),
                    dbc.Row([ *[dbc.Col(year, className='my-slider__text', style={'display':'block'} if year in period else {'display':'none'}) for year in FULL_YEARS]]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_input(type='rules',year=year,value=route.iloc[0][f"rules%_{year}{rules_suffix}"])
                        ], className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_slider(type='rules',year=year,value=route.iloc[0][f"rules%_{year}{rules_suffix}"], step=0.001)
                        ], id={'type': 'rules_container', 'index': year}, className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ]),
                ], className='mx-5')]
            ),
            dcc.Tab(
                label='Операторы',
                value='tab-4', className='custom-tab',
                selected_className='custom-tab--selected',
                children=[html.Div([
                    html.Div(
                        className='my-section__header',
                        children=[
                            html.H2(className='my-section__title',children='Расходы по оплате услуг операторов'),
                            html.Span(className='my-section__badge', children='руб. за 1 т.')
                        ]
                    ),
                    dbc.Row([ *[dbc.Col(year, className='my-slider__text', style={'display':'block'} if year in period else {'display':'none'}) for year in FULL_YEARS]]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_input(type='oper',year=year,value=round(route.iloc[0][f"Расходы по оплате услуг операторов_{year}, руб. за тонну"]))
                        ], className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_slider(type='oper',year=year,value=round(route.iloc[0][f"Расходы по оплате услуг операторов_{year}, руб. за тонну"]))
                        ], id={'type': 'oper_container', 'index': year}, className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ]),
                ], className='mx-5')]
            ),
            dcc.Tab(
                label='Перевалка',
                value='tab-5', className='custom-tab',
                selected_className='custom-tab--selected',
                style={'display': is_export},
                children=[html.Div([
                    html.Div(
                        className='my-section__header',
                        children=[
                            html.H2(className='my-section__title',
                                    children='Расходы по по перевалке грузов'),
                            html.Span(className='my-section__badge',
                                      children='руб. за 1 т.')
                        ]
                    ),
                    dbc.Row([*[dbc.Col(year, className='my-slider__text', style={'display':'block'} if year in period else {'display':'none'}) for
                               year in FULL_YEARS]]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_input(type='per', year=year, value=round(route.iloc[0][f"Расходы на перевалку_{year}, руб. за тонну"]))
                        ], className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index, year in
                            enumerate(FULL_YEARS)]
                    ]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_slider(type='per', year=year, value=round(
                                route.iloc[0][
                                    f"Расходы на перевалку_{year}, руб. за тонну"]))
                        ], id={'type': 'per_container', 'index': year},
                            className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index, year in
                            enumerate(FULL_YEARS)]
                    ]),
                ], className='mx-5')]
            ),
            dcc.Tab(
                label='Фрахт',
                value='tab-9', className='custom-tab',
                selected_className='custom-tab--selected',
                style={'display': is_fraht },
                children=[html.Div([
                    html.Div(
                        className='my-section__header',
                        children=[
                            html.H2(className='my-section__title',children='Фрахт'),
                            html.Span(className='my-section__badge', children='руб. за 1 т.')
                        ]
                    ),
                    dbc.Row([ *[dbc.Col(year, className='my-slider__text', style={'display':'block'} if year in period else {'display':'none'}) for year in FULL_YEARS]]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_input(type='fraht',year=year,value=route.iloc[0][f"fraht_{year}"])
                        ], className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_slider(type='fraht',year=year,value=route.iloc[0][f"fraht_{year}"], step=1, max=round(route.iloc[0][f"Расходы на перевалку_{year}, руб. за тонну"])*2)
                        ], id={'type': 'rules_container', 'index': year}, className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ]),
                ], className='mx-5')]
            ),
            dcc.Tab(
                label='Курс $',
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
                        style={'display':'block'} if year in period else {'display':'none'}
                    ) for year in FULL_YEARS]],
                            className='my-row_type_full'),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_input(type='dollar_price', year=year, value=PRICES_DOLLAR.loc[index, 'prices'])
                        ], className='text-center', style={'display':'block'} if year in period else {'display':'none'}
                        ) for index, year in enumerate(FULL_YEARS)]
                    ], className='my-row_type_full'),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_slider(type='dollar_price', year=year,value=PRICES_DOLLAR.loc[index, 'prices'], max=200, step=0.1)
                        ], id={'type': 'dollar_price_container', 'index': year},
                            className='text-center', style={'display':'block'} if year in period else {'display':'none'}
                        ) for index, year in enumerate(FULL_YEARS)]
                    ]),
                ])]
            ),
            dcc.Tab(
                label='Цена $',
                value='tab-6',
                className='custom-tab',
                selected_className='custom-tab--selected',
                style={'display': is_export},
                children=[html.Div([
                    html.Div(
                        className='my-section__header',
                        children=[
                            html.H2(className='my-section__title',children=['Стоимость 1 тонны на рынке',' (',
                                html.Em(price_message),')'
                            ]),
                            html.Span(className='my-section__badge', children='$ за 1 т.')
                        ]
                    ),
                    dbc.Row([ *[dbc.Col(year, className='my-slider__text', style={'display':'block'} if year in period else {'display':'none'}) for year in FULL_YEARS]]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_input(type='price',year=year,value=round(route.iloc[0][f'Стоимость 1 тонны на рынке_{year}_$, руб./т.'],1))
                        ], className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_slider(type='price',year=year,value=round(route.iloc[0][f'Стоимость 1 тонны на рынке_{year}_$, руб./т.'],1))
                        ], id={'type': 'price_container', 'index': year}, className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ]),
                ], className='mx-5')]
            ),
            dcc.Tab(
                label='Цена (руб.)',
                value='tab-61',
                className='custom-tab',
                selected_className='custom-tab--selected',
                style={'display': is_internal},
                children=[html.Div([
                    html.Div(
                        className='my-section__header',
                        children=[
                            html.H2(className='my-section__title',children=['Стоимость 1 тонны на рынке',' (',
                                html.Em(price_message),')'
                            ]),
                            html.Span(className='my-section__badge',
                                      children='руб. за 1 т.')
                        ]
                    ),
                    dbc.Row([*[dbc.Col(year, className='my-slider__text', style={'display':'block'} if year in period else {'display':'none'}) for year in FULL_YEARS]]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_input(type='price_rub', year=year, value=round(
                                route.iloc[0][
                                    f'Стоимость 1 тонны на рынке_{year}, руб./т.'],
                                1))
                        ], className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index, year in
                            enumerate(FULL_YEARS)]
                    ]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_slider(type='price_rub', year=year, value=round(
                                route.iloc[0][
                                    f'Стоимость 1 тонны на рынке_{year}, руб./т.'],
                                1))
                        ], id={'type': 'price_rub_container', 'index': year},
                            className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index, year in
                            enumerate(FULL_YEARS)]
                    ]),
                ], className='mx-5')]
            ),


            dcc.Tab(
                label='Себестоимость',
                value='tab-1',
                className='custom-tab',
                selected_className='custom-tab--selected',
                children=[html.Div([
                    html.Div(
                        className='my-section__header',
                        children=[
                            html.H2(className='my-section__title',children='Себестоимость добычи/производства'),
                            html.Span(className='my-section__badge', children='руб. за 1 т.')
                        ]
                    ),
                    dbc.Row([ *[dbc.Col(year, className='my-slider__text', style={'display':'block'} if year in period else {'display':'none'}) for year in FULL_YEARS]]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_input(type='cost',year=year,value=cost)
                        ], className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ]),
                    dbc.Row([
                        *[dbc.Col([
                            eq.draw_slider(type='cost',year=year,value=cost)
                        ], id={'type': 'cost_container', 'index': year}, className='text-center', style={'display':'block'} if year in period else {'display':'none'}) for index,year in enumerate(FULL_YEARS)]
                    ]),
                ], className='mx-5')]
            ),
        ])

    return res




def effects_table(route,rzd,bases,rules, trip_type):
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
                html.P(children='Совокупная тарифная нагрузка', className=f"my-table__text my-table__text_weight_bold", )
            ]),
            *[html.Li(
                className="my-table__column my-table__column_align_center my-table__column_width_120",
                children=[
                    html.P(
                        className="my-table__text my-table__text_weight_bold",
                        children=[
                            round(
                                rzd[index - 1] * (route[f'rules%_{year}{suffix}'].values[0] - 1) + rzd[index - 1] * (bases[index] - 1)
                                , 2),
                            html.Br(),
                            '(', '+', round(
                                (rzd[index - 1] * (route[f'rules%_{year}{suffix}'].values[0] - 1) + rzd[index - 1] * (bases[index] - 1))
                                * 100 / rzd[index - 1], 2),
                            '%)'
                        ]
                    )
                ]) for index, year in enumerate(CON.YEARS, start=1)],

        ]),
        html.Ul(className="my-table__row", children=[
            html.Li(className="my-table__column", children=[
                html.P(children='Базовая индексация с надбавками',  className=f"my-table__text my-table__text_weight_bold", )
            ]),
            *[html.Li(
                className="my-table__column my-table__column_align_center my-table__column_width_120",
                children=[
                    html.P(
                        className="my-table__text my-table__text_weight_bold",
                        children=[
                            round(rzd[index-1]*(bases[index]-1),2),
                            html.Br(),
                            '(', '+', round(rzd[index-1]*(bases[index]-1)*100 / rzd[index-1], 2),
                            '%)'
                        ]
                    )
                ]) for index, year in enumerate(CON.YEARS,start=1)],

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
                            '(', '+', round( rzd[index - 1] * (route[f'rules%_{year}{suffix}'].values[0] - 1) * 100 / rzd[index - 1], 2),
                            '%)'
                        ]
                    )
                ]) for index, year in enumerate(CON.YEARS, start=1)],
        ]),
    ]
    rules = tr.load_rules(active_only=True)
    for rule_index, rule in enumerate(rules,start=1):
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
                                '(',round(route[f'rules%_{year}_{rule_index}{suffix}'].values[0]*100,2),'%)'
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
@callback(
    Output('route_select_csr','value'),
    Input('calculate-button','n_clicks'),
    State('epl_change','value'),
    State('cif_fob','value'),
    State('index_sell_prices','value'),
    State('price_variant','value'),
    State('index_sell_coal','value'),
    State('index_oper','value'),
    State('index_per','value'),
    [State(str(year) + '_year_total_index', 'children') for year in CON.YEARS],
)
def update_transport(
    calculate_button,
    epl_change,
    cif_fob,
    index_sell_prices, price_variant, index_sell_coal, index_oper, index_per,
    *revenue_index_values
):
    if all(value == 0 for value in revenue_index_values):
        revenue_index_values = calculate_total_index()
    params = {
        "label": 'Признак',
        "revenue_index_values": revenue_index_values,
        "epl_change": epl_change,
        "ipem": {
            "index_sell_prices": index_sell_prices,
            "price_variant": price_variant,
            "index_sell_coal": index_sell_coal,
            "index_oper": index_oper,
            "index_per": index_per,
            "cif_fob": cif_fob,
        }
    }

    helpers.save_last_params(params)
    global ipem_calculated
    ipem_calculated = calc.calculate_data_ipem([], [], params)


    return None


@callback(
    Output('message_select_csr','options'),
    Output('message_select_csr','disabled'),
    Output('message_select_csr','value'),
    Output('message_select_csr','placeholder'),
    Input('cargo_select','value'),
    prevent_initial_call=True
)
def cargo_select(cargo):
    disabled = True if cargo is None else False
    placeholder = '' if cargo is None else 'Выберите вид сообщения'
    options = df.loc[df['Груз'] == cargo, 'Вид сообщения'].unique()

    return (options,disabled,None,placeholder)


@callback(
    Output('route_select_csr','options'),
    Output('route_select_csr','disabled'),
    Output('route_select_csr','value', allow_duplicate=True),
    Output('route_select_csr','placeholder'),
    Input('message_select_csr','value'),
    State('cargo_select','value'),
    prevent_initial_call=True
)
def message_select_csr(message,cargo):
    disabled = True if message is None else False
    placeholder = '' if message is None else 'Выберите маршрут'
    condition = (df['Груз'] == cargo) & (df['Вид сообщения'] == message)
    options = df.loc[condition, 'route'].unique()

    return (options,disabled,None,placeholder)





def graph_bar_h(test_df,gdf,fake_gdf,marginality,years,colors,width,names):
    test_df = test_df.loc[test_df['years'].isin(years)]
    gdf = gdf.loc[gdf['years'].isin(years)]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name=names[1], y=years, x=fake_gdf['costs'], text=gdf['costs'],
        texttemplate='%{text:.1f}%', marker=dict(color=colors[0]),
        insidetextanchor='middle',
        width=width, orientation='h',
        customdata=test_df['costs'],
        hovertemplate="%{y} г. <br>%{customdata:.1f} руб."
    )) if sum(test_df['costs']) > 0 else ''
    fig.add_trace(go.Bar(name=names[2], y=years, x=fake_gdf['rzd'],
        text=gdf['rzd'], texttemplate='%{text:.1f}%',
        marker=dict(color=colors[1]), insidetextanchor='middle',
        width=width, orientation='h',
        customdata=test_df['rzd'],
        hovertemplate="%{y} г. <br>%{customdata:.1f} руб."
    )) if sum(test_df['rzd']) > 0 else ''
    fig.add_trace(go.Bar(
        name=names[3], y=years, x=fake_gdf['oper'], text=gdf['oper'],
        texttemplate='%{text:.1f}%', marker=dict(color=colors[2]),
        insidetextanchor='middle',
        width=width, orientation='h',
        customdata=test_df['oper'],
        hovertemplate="%{y} г. <br>%{customdata:.1f} руб."
    )) if sum(test_df['oper']) > 0 else ''
    fig.add_trace(go.Bar(
        name=names[4], y=years, x=fake_gdf['per'], text=gdf['per'],
        texttemplate='%{text:.1f}%', marker=dict(color=colors[3]),
        insidetextanchor='middle',
        width=width, orientation='h',
        customdata=test_df['per'],
        hovertemplate="%{y} г. <br>%{customdata:.1f} руб."
    )) if sum(test_df['per']) > 0 else ''

    fig.add_trace(go.Bar(
        name=names[5], y=years, x=fake_gdf['fraht'], text=gdf['fraht'],
        texttemplate='%{text:.1f}%', marker=dict(color=colors[4]),
        insidetextanchor='middle',
        width=width, orientation='h',
        customdata=test_df['fraht'],
        hovertemplate="%{y} г. <br>%{customdata:.1f} руб."
    )) if sum(test_df['fraht']) > 0 else ''
    fig.add_trace(go.Bar(
        name=names[0], y=years, x=fake_gdf['marginality'],
        text=gdf['marginality'], texttemplate='%{text:.1f}%',
        marker=dict(color=colors[5]), insidetextanchor='middle',
        orientation='h', width=width, textposition='auto',
        customdata=test_df['marginality'],
        hovertemplate="%{y} г. <br>%{customdata:.1f} руб."
    )) if sum(test_df['marginality']) > 0 else ''

    fig.update_layout(uniformtext_minsize=12)
    fig.update_layout(uniformtext_mode='show')

    fig.update_layout(barmode='stack')
    fig.update_layout(yaxis_title=None, xaxis_title=None)
    fig.update_layout(margin=dict(t=0))
    fig.update_layout(yaxis=dict(autorange="reversed"))
    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", xanchor="left",
                    title=None, x=0.0, traceorder="normal"))
    fig.update_layout(plot_bgcolor='white', )
    fig.update_layout(
        legend_tracegroupgap=0,
        legend_traceorder='normal'
    )
    fig.update_layout(
        height=400,
        margin=dict(l=0, r=0, t=0, pad=0),
    )
    fig.update_layout(
        yaxis=dict(
            tickmode='array',
            tickvals=years,
            ticktext=years
        ),
        xaxis = dict(
            showticklabels=False
        )
    )
    return fig

def graph_bar_v(test_df,gdf,fake_gdf, marginality,years,colors,width,names):
    test_df = test_df.loc[test_df['years'].isin(years)].reset_index()
    gdf = gdf.loc[gdf['years'].isin(years)].reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name=names[1], x=years, y=fake_gdf['costs'], text=gdf['costs'],
        texttemplate='%{text:.1f}%', marker=dict(color=colors[0]),
        insidetextanchor='middle',
        width=width,
        customdata=test_df['costs'],
        hovertemplate="%{x} г. <br>%{customdata:.1f} руб."
    )) if sum(test_df['costs']) > 0 else ''

    fig.add_trace(go.Bar(
        name='Транспортная составляющая', x=years, y=fake_gdf['transport'],
        text=gdf['transport'], texttemplate='%{text:.1f}%',
        marker=dict(color=colors[1]), insidetextanchor='middle',
        width=width,
        customdata=test_df['transport'],
        hovertemplate="%{x} г. <br>%{customdata:.1f} руб."
    )) if sum(test_df['transport']) > 0 else ''

    fig.add_trace(go.Bar(
        name=names[0], x=years, y=fake_gdf['marginality'],
        text=gdf['marginality'], texttemplate='%{text:.1f}%',
        marker=dict(color=colors[5]), insidetextanchor='middle',
        width=width, textposition='auto',
        customdata=test_df['marginality'],
        hovertemplate="%{x} г. <br>%{customdata:.1f} руб."
    )) if sum(test_df['marginality']) > 0 else ''

    fig.update_layout(barmode='stack')
    fig.update_layout(yaxis_title=None, xaxis_title=None)
    # fig.update_xaxes(nticks=len(years))
    fig.update_layout(uniformtext_minsize=12)
    fig.update_layout(uniformtext_mode='show')

    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", xanchor="center", traceorder="normal",
                    title=None, x=0.5))
    fig.update_layout(plot_bgcolor='white', )
    fig.update_layout(
        xaxis=dict(
            tickmode='array',
            tickvals=years,
            ticktext=years
        ),
        yaxis=dict(
            showticklabels=False
        )
    )

    fig.update_layout(
        height=400,
        margin=dict(l=0, r=0, t=0, pad=0),
    )
    return fig


def graph_bar_ts(test_df,gdf,marginality,years,colors,width,names, trip):
    test_df = test_df.loc[test_df['years'].isin(years)].reset_index()
    gdf = gdf.loc[gdf['years'].isin(years)].reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name='Расходы на оплату услуг ОАО "РЖД (груженый рейс)', x=years, y=test_df['rzd_gr'], text=test_df['rzd_gr'],
        texttemplate='%{text:.1f}', marker=dict(color=colors[1]),
        insidetextanchor='middle',
        width=width,
        customdata=gdf['rzd_gr'],
        hovertemplate="%{x} г. <br>%{y} руб. <br>%{customdata:.1f}%"
    )) if sum(test_df['rzd_gr']) > 0 else ''

    if trip == 'Кругорейс':
        fig.add_trace(go.Bar(
            name='Расходы на оплату услуг ОАО "РЖД (порожний рейс)', x=years, y=test_df['rzd_por'],
            text=test_df['rzd_por'],
            texttemplate='%{text:.1f}', marker=dict(color=colors[0]),
            insidetextanchor='middle',
            width=width,
            customdata=gdf['rzd_por'],
            hovertemplate="%{x} г. <br>%{y} руб. <br>%{customdata:.1f}%"
        )) if sum(test_df['rzd_por']) > 0 else ''
    fig.add_trace(go.Bar(
        name='Расходы по оплате услуг операторов', x=years, y=test_df['oper'],
        text=test_df['oper'],
        texttemplate='%{text:.1f}', marker=dict(color=colors[2]),
        insidetextanchor='middle',
        width=width,
        customdata=gdf['oper'],
        hovertemplate="%{x} г. <br>%{y} руб. <br>%{customdata:.1f}%"
    )) if sum(test_df['oper']) > 0 else ''

    fig.add_trace(go.Bar(
        name='Расходы на перевалку', x=years, y=test_df['per'],
        text=test_df['per'],
        texttemplate='%{text:.1f}', marker=dict(color=colors[3]),
        insidetextanchor='middle',
        width=width,
        customdata=gdf['per'],
        hovertemplate="%{x} г. <br>%{y} руб. <br>%{customdata:.1f}%"
    )) if sum(test_df['per']) > 0 else ''
    for index, row in gdf.iterrows():
        fig.add_annotation(x=row['years'], y=-0,text=f'{row["transport"]}%', yshift=-20, showarrow=False, bgcolor="#003256", font=dict(color="#ffffff"))
    fig.add_shape(
        name="Транспортная составляющая, %",
        showlegend=True,
        type="rect",
        xref="paper",
        fillcolor="#003256",
        line_width =0,
        legend="legend2",
        legendrank=5,
        x0=0.85,x1=0.95,y0=0,y1=1,
    )
    for index, row in test_df.iterrows():
        fig.add_annotation(x=row['years'], y=-0,text=f'{gdf.iloc[index]["marginality"]}%', yshift=-40, showarrow=False, bgcolor="#000000", font=dict(color="#ffffff"))
        # fig.add_annotation(x=row['years'], yref="paper", y=0.95,text=f'{gdf.iloc[index]["marginality"]}%', yshift=10, xshift=10, showarrow=False, bgcolor="#000000", font=dict(color="#FFFFFF"))

    fig.add_shape(
        name="Оценка маржинальности, %",
        showlegend=True,
        type="rect",
        xref="paper",
        fillcolor="#000000",
        legend="legend2",
        line_width=0,
        legendrank=10,
        x0=0.85, x1=0.95, y0=0, y1=1,
    )

    fig.update_layout(barmode='stack')
    fig.update_layout(yaxis_title=None, xaxis_title=None)

    fig.update_layout(
        height=400,
        margin=dict(l=0, r=0, t=0, pad=0),
    )
    fig.update_layout(margin_pad=30)
    fig.update_layout(uniformtext_minsize=12)
    fig.update_layout(uniformtext_mode='show')
    fig.update_layout(plot_bgcolor='white', yaxis=dict(showticklabels=False) )
    fig.update_layout(
        legend=dict(
            x=1.1,
            y=0.6,
            orientation='v',
            itemwidth=40
        ),
        legend2=dict(
            x=1.1,
            y=0,
            orientation='v',
            itemwidth=40
        )
    )

    return fig

def graph_bar_trend(test_df,gdf,marginality,years,colors,width,names):
    test_df = test_df.loc[test_df['years'].isin(years)]
    gdf = gdf.loc[gdf['years'].isin(years)]
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=years, y=test_df['costs'],
        mode='lines+markers+text', name=names[1],
        line=dict(width=1, color=colors[0]),
        text=test_df['costs'], texttemplate='%{text:.1f}',
        textposition='top center',
        customdata=test_df['costs'],
        hovertemplate="%{x} г. <br>%{y}% <br>%{customdata:.1f} руб."
    )) if sum(test_df['costs']) > 0 else ''
    fig.add_trace(go.Scatter(
        x=years, y=test_df['rzd'],
        mode='lines+markers+text', name=names[2],
        line=dict(width=1, color=colors[1]),
        text=test_df['rzd'], texttemplate='%{text:.1f}',
        textposition='top center',
        customdata=test_df['rzd'],
        hovertemplate="%{x} г. <br>%{y}% <br>%{customdata:.1f} руб."
    )) if sum(test_df['rzd']) > 0 else ''
    fig.add_trace(go.Scatter(
        x=years, y=test_df['oper'],
        mode='lines+markers+text', name=names[3],
        line=dict(width=1, color=colors[2]),
        text=test_df['oper'], texttemplate='%{text:.1f}',
        textposition='top center',
        customdata=test_df['oper'],
        hovertemplate="%{x} г. <br>%{y}% <br>%{customdata:.1f} руб."
    )) if sum(test_df['oper']) > 0 else ''
    fig.add_trace(go.Scatter(
        x=years, y=test_df['per'],
        mode='lines+markers+text', name=names[4],
        line=dict(width=1, color=colors[3]),
        text=test_df['per'], texttemplate='%{text:.1f}',
        textposition='top center',
        customdata=test_df['per'],
        hovertemplate="%{x} г. <br>%{y}% <br>%{customdata:.1f} руб."
    )) if sum(test_df['per']) > 0 else ''

    fig.add_trace(go.Scatter(
        x=years, y=test_df['fraht'],
        mode='lines+markers+text', name=names[5],
        line=dict(width=1, color=colors[4]),
        text=test_df['fraht'], texttemplate='%{text:.1f}',
        textposition='top center',
        customdata=test_df['fraht'],
        hovertemplate="%{x} г. <br>%{y}% <br>%{customdata:.1f} руб."
    )) if sum(test_df['fraht']) > 0 else ''
    fig.add_trace(go.Scatter(
        x=years, y=test_df['marginality'],
        mode='lines+markers+text', name=names[0],
        line=dict(width=1, color=colors[5]),
        text=test_df['marginality'], texttemplate='%{text:.1f}',
        textposition='top center',
        customdata=test_df['marginality'],
        hovertemplate="%{x} г. <br>%{y}% <br>%{customdata:.1f} руб."
    )) if sum(test_df['marginality']) > 0 else ''

    fig.update_layout(legend=dict(x=1, y=0.5))
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(
            visible=False  # Скрыть ось Y (ось ординат)
        ),
    )
    fig.update_xaxes(ticks="inside", tickwidth=2, tickcolor='black', ticklen=10)

    fig.update_xaxes(showgrid=True, showline=False, zeroline=True,  # Скрыть линию оси X
        tickfont=dict(color='black')
    )
    fig.update_yaxes(showgrid=False)
    fig.update_layout(
        xaxis=dict(
            tickmode='array',
            tickvals=years,
            ticktext=years
        )
    )
    fig.update_layout(
        height=400,
        margin=dict(l=0, r=0, t=0, pad=0),
    )

    return fig




def get_prices_message(prices_change, prices_variant):
    if prices_change == []: return 'Прогноз цен не задан'
    if 'Минэк' in prices_variant: return 'Прогноз цен приведен по оценкам Минэк'
    if 'ЦСР' in prices_variant: return 'Прогноз цен приведен по оценкам ЦСР'
    return ''


@callback(
    Output('period_select_csr', 'value'),
    Input('period_select_csr', 'value')
)
def sort_selected_values(selected_values):
    if selected_values:
        sorted_values = sorted(selected_values)
        return sorted_values
    return selected_values




@callback(
    Output('currency_dollar_csr','label'),
    Input('currency_dollar_csr','value'),
)
def switch_table_currency(value):
    if value == False:
        return 'Цены в ₽'
    return 'Цены в $'