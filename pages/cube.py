# import dash
#
# from dash import html, dcc, callback, ALL, MATCH
# from dash.dependencies import Input, Output, State
# from pages.data import get_ipem_data, get_indexes_data
# import dash_bootstrap_components as dbc
# from dash import callback_context
#
#
# import pandas as pd
# import pages.helpers as helpers
# import pages.calculations as calc
# from pages.constants import Constants as CON
#
# from pages.scenario_parameters.input_states import input_states
# import pages.scenario_parameters.scenario_parameters as sp
# import pages.analytics.equlizer as eq
#
# dash.register_page(__name__, name="Куб", path='/cube', order=3, my_class='my-navbar__icon-2')
#
#
#
# df = []
#
# df = get_ipem_data()
#
# ipem_calculated = []
# FULL_YEARS = [2024] + CON.YEARS
#
#
# def layout():
#     return html.Div([
#         sp.scenario_parameters(),
#         sp.toggle_button(),
#
#         html.Div(
#             results()
#         ),
#     ])
#
#
#
#
# def results():
#
#     return html.Div([
#         html.Div([], id='header_div'),
#         html.Section(className='my-section', children=[
#             html.Div(className='my-section__header', children=[
#                 html.H2(className='my-section__title',
#                         children='Оценка транспортной составляющей'),
#                 html.Span(className='my-section__badge', children='руб./т')
#             ]),
#             html.Div(
#                 className='my-separate my-separate_width_600 my-separate_vector_left'),
#             dbc.Row([
#                 dbc.Col([
#                     html.Label('Группа груза'),
#                     dcc.Dropdown(
#                         id='cargogroup2',
#                         options=df["Группа груза"].unique(),
#                         searchable=True,
#                         value=None
#                     ),
#                 ], width=3),
#                 dbc.Col([
#                     html.Label('Холдинг'),
#                     dcc.Dropdown(
#                         id='holding2',
#                         options=df["Холдинг грузоотправителя"].unique(),
#                         searchable=True,
#                         value=None
#                     ),
#                 ], width=4),
#                 dbc.Col([
#                     html.Label('Базовый год'),
#                     dcc.Dropdown(
#                         id='year2_base',
#                         options=[2024] + CON.YEARS,
#                         searchable=True,
#                         value=2024
#                     ),
#                 ], width=1),
#                 dbc.Col([
#                     html.Label('Год расчета'),
#                     dcc.Dropdown(
#                         id='year2',
#                         options=CON.YEARS,
#                         searchable=True,
#                         value=2025
#                     ),
#                 ], width=1),
#
#
#             ]),
#             dcc.Loading(
#                 id="loading",
#                 type="default",
#                 color="#e21a1a",
#                 fullscreen=False,
#                 children=[html.Div([], id='transport_div')]
#             ),
#         ]),
#
#     ])
#
#
#
#
#
#
# @callback(
#     Output('transport_div','children'),
#     Input('calculate-button','n_clicks'),
#     State('epl_change','value'),
#     [State(str(year) + '_year_total_index', 'children') for year in CON.YEARS],
#     State('cif_fob','value'),
#     State('index_sell_prices','value'),
#     State('price_variant','value'),
#     State('index_sell_coal','value'),
#     State('index_oper','value'),
#     State('index_per','value'),
#     Input('cargogroup2','value'),
#     Input('holding2','value'),
#     Input('year2','value'),
#     Input('year2_base','value'),
# )
# def update_transport(
#         calculate_button,
#         epl_change,
#         index_2025,index_2026,index_2027,index_2028,index_2029,index_2030,
#         cif_fob,
#         index_sell_prices, price_variant, index_sell_coal, index_oper, index_per,
#         cargogroup,holding,year2,year2_base
# ):
#     revenue_index_values = (
#     index_2025, index_2026, index_2027, index_2028, index_2029, index_2030)
#     if revenue_index_values == ([], [], [], [], [], []):
#         revenue_index_values = (1.06242, 1.048, 1.040, 1.039, 1.039, 1.039)
#     params = {
#         "label": 'Признак',
#         "revenue_index_values": revenue_index_values,
#         "epl_change": epl_change,
#         "ipem": {
#             "index_sell_prices": index_sell_prices,
#             "price_variant": price_variant,
#             "index_sell_coal": index_sell_coal,
#             "index_oper": index_oper,
#             "index_per": index_per,
#             "cif_fob": cif_fob,
#         }
#     }
#
#     helpers.save_last_params(params)
#     global ipem_calculated
#     ipem_calculated = calc.calculate_data_ipem([], [], params)
#
#     res = ipem_calculated.copy()
#     res[CON.PER_RUB] = res[CON.PER_RUB].fillna(0)
#
#
#     if cargogroup and len(cargogroup) > 0: res = res[res['Группа груза'] == cargogroup]
#     if holding and len(holding) > 0: res = res[res['Холдинг грузоотправителя'] == holding]
#
#
#     head = html.Div(className="my-table__header my-table__header_type_scroll",
#                     children=[
#                         html.Ul(className="my-table__row ", children=[
#                             html.Li(className="my-table__column", children=[
#                                 html.P(
#                                     className="my-table__text my-table__text_color_grey",
#                                     children=f"Груз, Холдинг")
#                             ]),
#
#                             html.Li(className="my-table__column", children=[
#                                 html.P(
#                                     className="my-table__text my-table__text_color_grey",
#                                     children=f"Маршрут")
#                             ]),
#                             html.Li(className="my-table__column", children=[
#                                 html.P(
#                                     className="my-table__text my-table__text_color_grey",
#                                     children=f"Цена на рынке {year2_base} г.")
#                             ]),
#                             html.Li(className="my-table__column", children=[
#                                 html.P(
#                                     className="my-table__text my-table__text_color_grey",
#                                     children=f"Транспортная составляющая {year2_base} г.")
#                             ]),
#                             html.Li(className="my-table__column", children=[
#                                 html.P(
#                                     className="my-table__text my-table__text_color_grey",
#                                     children=f"Инфраструктурная составляющая {year2_base} г.")
#                             ]),
#                             html.Li(className="my-table__column", children=[
#                                 html.P(
#                                     className="my-table__text my-table__text_color_grey",
#                                     children=f"Цена на рынке {year2} г.")
#                             ]),
#                             html.Li(className="my-table__column", children=[
#                                 html.P(
#                                     className="my-table__text my-table__text_color_grey",
#                                     children=f"Транспортная составляющая {year2} г.")
#                             ]),
#                             html.Li(className="my-table__column", children=[
#                                 html.P(
#                                     className="my-table__text my-table__text_color_grey",
#                                     children=f"Увеличение инфраструктурной составляющей {year2} г.")
#                             ]),
#                             html.Li(className="my-table__column", children=[
#                                 html.P(
#                                     className="my-table__text my-table__text_color_grey",
#                                     children=f"Увеличение инфраструктурной составляющей {year2} г. (только тарифные решения)")
#                             ]),
#                         ])
#                     ])
#     table_rows = []
#
#     res['rules_sum_2024'] = 0
#     res['rules_sum_2025'] = res['rules_2025']
#     res['rules_sum_2026'] = res['rules_sum_2025'] + res['rules_2026']
#     res['rules_sum_2027'] = res['rules_sum_2026'] + res['rules_2027']
#     res['rules_sum_2028'] = res['rules_sum_2027'] + res['rules_2028']
#     res['rules_sum_2029'] = res['rules_sum_2028'] + res['rules_2029']
#     res['rules_sum_2030'] = res['rules_sum_2029'] + res['rules_2030']
#
#     for index, route in res.iterrows():
#         gr_24 = route[CON.RZD_GR]
#         por_24 = route[CON.RZD_POR]
#         price_24 = route[CON.PRICE_RUB]
#         per_24 = route[CON.PER_RUB]
#         oper_24 = route[CON.OPER_RUB]
#
#         ir_2024 = gr_24 + por_24
#         ir_2024_p = ir_2024 * 100 / price_24
#         tr_2024 = ir_2024 + per_24 + oper_24
#         tr_2024_p = tr_2024 * 100 / price_24
#
#         if year2_base != 2024:
#
#             ir_2024 = route[f'РЖД_ИТОГО_{year2_base}']
#             tr_2024 = ir_2024 + route[
#                 f'Расходы по оплате услуг операторов_{year2_base}, руб. за тонну'] + \
#                       route[f'Расходы на перевалку_{year2_base}, руб. за тонну']
#             ir_2024_p = ir_2024 * 100 / route[f'Стоимость 1 тонны на рынке_{year2_base}, руб./т.']
#             tr_2024_p = tr_2024 * 100 / route[f'Стоимость 1 тонны на рынке_{year2_base}, руб./т.']
#
#         # base_2025 = route[f'РЖД_ИТОГО_{year2}'] - ir_2024
#         # dec_2025 = 0
#         # for rule_index, rule in enumerate(rules, start=1):
#         #     dec_2025 += route[f'РЖД_ИТОГО_{year2}_{rule_index}']
#
#         ir_2025 =  route[f'РЖД_ИТОГО_{year2}']
#         ir_2025_p = ir_2025 * 100 / route[f'Стоимость 1 тонны на рынке_{year2}, руб./т.']
#
#         ir_2025_dec =  route[f'rules_{year2}']
#         ir_2025_p_dec = ir_2025_dec * 100 / route[f'Стоимость 1 тонны на рынке_{year2}, руб./т.']
#         tr_2025 = ir_2025 + route[
#             f'Расходы по оплате услуг операторов_{year2}, руб. за тонну'] + \
#                   route[f'Расходы на перевалку_{year2}, руб. за тонну']
#         tr_2025_p = tr_2025 * 100 / route[
#             f'Стоимость 1 тонны на рынке_{year2}, руб./т.']
#         dec_diff = route[f'rules_sum_{year2}'] - route[f'rules_sum_{year2_base}']
#         dec_diff_p = dec_diff * 100 / route[f'Стоимость 1 тонны на рынке_{year2}, руб./т.']
#         table_rows.append(
#             html.Ul(className=f"my-table__row", children=[
#                 html.Li(className="my-table__column", children=[
#                     html.P(
#                         className=f"my-table__text my-table__text_weight_bold ",
#                         children=[
#                             route['Группа груза']," (",route['Груз'], ")",
#                             html.Br(),
#                             route['Холдинг грузоотправителя']
#                         ])
#                 ]),
#                 html.Li(className="my-table__column", children=[
#                     html.P(
#                         className=f"my-table__text my-table__text_weight_bold",
#                         children=[
#                             route['Станция отправления'], '-',
#                             route['Станция назначения'],
#                             html.Br(),
#                             "(", route['Вид сообщения'], ',', route['Полигон'],
#                             ")"
#                         ])
#                 ]),
#                 html.Li(className="my-table__column", children=[
#                     html.P(
#                         className=f"my-table__text my-table__text_weight_bold",
#                         children=[
#                             round(route[
#                                       f'Стоимость 1 тонны на рынке_{year2_base}, руб./т.'],
#                                   1) if year2_base != 2024 else round(price_24,1)
#                         ])
#                 ]),
#                 html.Li(className="my-table__column", children=[
#                     html.P(
#                         className=f"my-table__text my-table__text_weight_bold",
#                         children=[
#                             round(tr_2024_p, 1), "%", html.Br(), "(",
#                             round(tr_2024, 1), ")"
#                         ])
#                 ]),
#                 html.Li(className="my-table__column", children=[
#                     html.P(
#                         className=f"my-table__text my-table__text_weight_bold",
#                         children=[
#                             round(ir_2024_p, 1), "%", html.Br(), "(",
#                             round(ir_2024, 1), ")"
#                         ])
#                 ]),
#                 html.Li(className="my-table__column", children=[
#                     html.P(
#                         className=f"my-table__text my-table__text_weight_bold",
#                         children=[
#                             round(route[
#                                       f'Стоимость 1 тонны на рынке_{year2}, руб./т.'],
#                                   1)
#                         ])
#                 ]),
#                 html.Li(className="my-table__column", children=[
#                     html.P(
#                         className=f"my-table__text my-table__text_weight_bold",
#                         children=[
#                             round(tr_2025_p, 1), "%", html.Br(), "(",
#                             round(tr_2025, 1), ")"
#                         ])
#                 ]),
#                 html.Li(className="my-table__column", children=[
#                     html.P(
#                         className=f"my-table__text my-table__text_weight_bold",
#                         children=[
#                             "+", round(ir_2025-ir_2024, 1), html.Br(), "(",
#                             "+" if round(ir_2025_p - ir_2024_p, 1) > 0 else "",
#                             round(ir_2025_p - ir_2024_p, 1), "%)"
#                         ])
#                 ]),
#                 html.Li(className="my-table__column", children=[
#                     html.P(
#                         className=f"my-table__text my-table__text_weight_bold",
#                         children=[
#                             "+", round(dec_diff, 1), html.Br(), "(",
#                             "+" if round(dec_diff_p, 1) > 0 else "",
#                             round(dec_diff_p, 1), "%)"
#                         ])
#                 ]),
#             ])
#         )
#     table = html.Div(className="my-table my-table_margin_top", children=[
#         head,
#         html.Div(
#             className="my-table__main my-table__main_type_scroll scroll my-table__main_height_450",
#             children=table_rows
#         ),
#     ])
#
#     return table
#
#
# @callback(
#     Output('holding2','options'),
#     Output('holding2','value'),
#     Input('cargogroup2','value'),
#     State('holding2','value'),
#     prevent_initial_call=True
# )
# def cargo_select(cargo, cur_holding):
#     if cargo == None:
#         options = list(df['Холдинг грузоотправителя'].unique())
#     else:
#         options = list(df.loc[df['Группа груза'] == cargo, 'Холдинг грузоотправителя'].unique())
#
#     if cur_holding in options:
#         val = cur_holding
#     else:
#         val = None
#     return (options,val)