
from dash import html, dcc, callback, ALL, MATCH
from dash.dependencies import Input, Output, State
from pages.data import get_ipem_data, get_main_data, make_ipem_related_routes
import dash_bootstrap_components as dbc
import pages.scenario_parameters.tarif_rules as tr
from pages.constants import Constants as CON

from pages.map_figure import mapFigure, convert_crs
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

@callback(
    Output({'type': 'trip_details', 'index': MATCH},'children'),
    Output({'type': 'st_rzd_gr', 'index': MATCH},'style'),
    Output({'type': 'st_rzd_por', 'index': MATCH},'style'),
    Input({'type': 'trip_details', 'index': MATCH},'n_clicks'),
    State({'type': 'trip_details', 'index': MATCH},'children'),
    # prevent_initial_call=True
)
def switch_trip_details (click,current):
    details = '-' if current == '+' else '+'
    style = {'display':''} if current == '+' else {'display':'none'}
    return (details,style,style)

@callback(
    Output({'type': 'transport_details', 'index': MATCH},'children'),
    Output({'type': 'rzd_total', 'index': MATCH},'style'),
    Input({'type': 'transport_details', 'index': MATCH},'n_clicks'),
    State({'type': 'transport_details', 'index': MATCH},'children'),
    # prevent_initial_call=True
)
def switch_transport_details (click,current):
    details = '-' if current == '+' else '+'
    style = {'display':''} if current == '+' else {'display':'none'}
    return (details,style)

def make_structure_table(route, test_df, test_df2, gdf, test_df_tr, years, costs,bases, rules,
                         oper,per,prices,prices_rub,dollar_prices, fraht,trip, marginality_real, marginality_real_percent,
                         currency_dollar,key):
    key = str(key)
    if currency_dollar == False:
        currency_symbol = '₽'
        dollar_prices = [1] * len(dollar_prices)
    else:
        currency_symbol = '$'
    return html.Table([
        html.Thead([
            html.Tr([
                html.Th(html.Strong('Параметр', className="my-card__caption__table"),className="text-center", style={'width':'25%'}),
                *[html.Th(html.Span(year, className="my-card__caption__table"), className="text-center") for year in years]
            ],style={"border-top":"none"})
        ]),
        html.Tbody([
            html.Tr([
                html.Th('Цена, $'),
                *[html.Th("{:.2f}".format(round(prices[index], 2)), className="text-end") for (index, year) in enumerate(years)]
            ]),
            html.Tr([
                html.Th('Цена, руб.'),
                *[html.Th("{:.2f}".format(round(prices_rub[index], 2)), className="text-end") for (index,year) in enumerate(years)]
            ], id={'type':'rub_price','index':str(route['index'])}) if currency_dollar == False else '',
            html.Tr([
                html.Th(f'Себестоимость, {currency_symbol}'),
                *[html.Th("{:.2f}".format(round(costs[index] / dollar_prices[index], 2)), className="text-end") for (index, year) in enumerate(years)]
            ]),
            html.Tr([
                html.Th([
                    html.Span(f'Транспортные затраты, {currency_symbol}', style={'margin-right':'5px'}),
                    dbc.Button('-', id={'type': 'transport_details', 'index': str(route['index'])+key}, color="secondary",size="sm")
                ]),
                *[html.Th("{:.2f}".format(round(test_df_tr['transport'][index] / dollar_prices[index], 2)), className="text-end") for (index, year) in enumerate(years)]
            ],style={'background-color':'#f0f8ff'}),
        ]),
        html.Tbody([
            html.Tr([
                html.Th([
                    html.Span(f'Ж/Д тариф({trip}), {currency_symbol}', style={'margin-right': '5px'}),
                    dbc.Button('-', id={'type': 'trip_details', 'index': str(route['index'])+key}, color="secondary",size="sm") if trip == 'Кругорейс' else ''
                ]),
                *[html.Th("{:.2f}".format(
                    round(test_df['rzd'][index] / dollar_prices[index], 2)),
                          className="text-end") for (index, year) in
                  enumerate(years)]
            ]),
            html.Tr([
                html.Td([
                    html.Span(f'Ж/Д тариф(груженый)'),
                ]),
                *[html.Th("{:.2f}".format(
                    round(test_df2['rzd_gr'][index] / dollar_prices[index],
                          2)), className="text-end") for (index, year) in
                  enumerate(years)]
            ], id={'type': 'st_rzd_gr', 'index': str(route['index'])+key},
                style={'display': ''}) if trip == 'Кругорейс' else '',
            html.Tr([
                html.Td([html.Span(f'Ж/Д тариф(порожний)')]),
                *[html.Th("{:.2f}".format(
                    round(test_df2['rzd_por'][index] / dollar_prices[index],
                          2)), className="text-end") for (index, year) in
                  enumerate(years)]
            ], id={'type': 'st_rzd_por', 'index': str(route['index'])+key},
                style={'display': ''}) if trip == 'Кругорейс' else '',
            html.Tr([
                html.Th(f'Вагонная составляющая, {currency_symbol}'),
                *[html.Th("{:.2f}".format(
                    round(test_df['oper'][index] / dollar_prices[index], 2)),
                    className="text-end") for (index, year) in
                    enumerate(years)]
            ]),
            html.Tr([
                html.Th(f'Перевалка, {currency_symbol}'),
                *[html.Th("{:.2f}".format(
                    round(test_df['per'][index] / dollar_prices[index], 2)),
                    className="text-end") for (index, year) in
                    enumerate(years)]
            ]),
        ], id={'type':'rzd_total', 'index': str(route['index'])+key}),
        html.Tbody([
             html.Tr([
                html.Th(f'Маржинальная прибыль, {currency_symbol} (%)'),
                *[html.Th('{:.2f} ({:.2f}%)'.format(round(marginality_real[index] / dollar_prices[index], 2), round(marginality_real_percent[index], 2)), className=f"text-end {get_color(marginality_real[index])}") for (index, year) in enumerate(years)]
            ]),
        ])
    ], className='table table-bordered table-sm mt-1 border-secondary')


def effects_table(route,rzd,bases,rules, trip_type):

    suffix = '_gr' if trip_type == 'Груженый рейс' else ''
    head = html.Thead([
        html.Tr([
            html.Th(html.Strong('Правило', className="my-card__caption__table"),className="text-center"),
            *[html.Th(html.Span(year, className="my-card__caption__table"), className="text-center") for year in CON.YEARS]
        ], style={"border-top":"none"})
    ])
    table_rows = [
        html.Tr(children=[
            html.Th(children=[
                html.Span(children='Совокупная тарифная нагрузка', )
            ], className="fw-bold w-25"),
            *[html.Th(
                children=[
                    html.P(
                        className="text-end m-0",
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
                ], ) for index, year in enumerate(CON.YEARS, start=1)],
        ]),
        html.Tr(children=[
            html.Th(children=[
                html.P(children='Базовая индексация с надбавками',className='m-0')
            ], className="fw-bold w-25"),
            *[html.Th(
                children=[
                    html.P(
                        className="text-end m-0",
                        children=[
                            round(rzd[index-1]*(bases[index]-1),2),
                            html.Br(),
                            '(', '+', round(rzd[index-1]*(bases[index]-1)*100 / rzd[index-1], 2),
                            '%)'
                        ]
                    )
                ]) for index, year in enumerate(CON.YEARS,start=1)],
        ]),
        html.Tr(children=[
            html.Th(children=[
                html.P(
                    children='Тарифные решения, в т.ч.',
                    className='m-0'
                )
            ], className="fw-bold w-25"),
            *[html.Th(
                children=[
                    html.P(
                        className="text-end m-0",
                        children=[
                            round(rzd[index - 1] * (route[f'rules%_{year}{suffix}'].values[0] - 1), 2),
                            html.Br(),
                            '(', '+' if route[f'rules%_{year}{suffix}'].values[0] > 0 else '' , round( rzd[index - 1] * (route[f'rules%_{year}{suffix}'].values[0] - 1) * 100 / rzd[index - 1], 2),
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
            html.Tr(children=[
                html.Th(children=[rule['name']], className="fw-bold w-25"),
                *[html.Th(
                    style={'width': '10%'},
                    className="text-end",
                    children=[
                        round(rzd[index - 1] * route[f'rules%_{year}_{rule_index}{suffix}'].values[0], 2),
                        html.Br(),
                        '(', '+' if route[f'rules%_{year}_{rule_index}{suffix}'].values[0] > 0 else '', round(route[f'rules%_{year}_{rule_index}{suffix}'].values[0] * 100, 2), '%)'
                    ]) for index, year in enumerate(CON.YEARS, start=1)]
            ]) if rule_sum > 0 else None
        )
    coeff = route['2024_coeff'].values[0] if suffix != '_gr' else route['2024_coeff_x'].values[0]

    table2 = []
    if coeff < 1:
        table2 = html.Table(
            className="table table-bordered table-sm mt-1 border-secondary",
            children=[html.Tbody(
                className="",
                children=[
                html.Tr(children=[
                    html.Td(children=[
                        html.Span(children='Совокупная тарифная нагрузка', )
                    ], className="fw-bold w-25"),
                    *[html.Td(
                        style= {'width':'10%'},
                        children=[
                            html.P(
                                className="text-end m-0",
                                children=[
                                    round(
                                        rzd[index - 1] * (route[
                                                              f'rules%_{year}{suffix}'].values[
                                                              0] - 1) + rzd[
                                            index - 1] * (bases[index] - 1)
                                        , 2),
                                    html.Br(),
                                    '(', '+', round(
                                        (rzd[index - 1] * (route[ f'rules%_{year}{suffix}'].values[0] - 1) + rzd[
                                             index - 1] * (bases[index] - 1))
                                        * 100 / rzd[index - 1], 2),
                                    '%)'
                                ]
                            )
                        ], ) for index, year in enumerate(CON.YEARS, start=1)],
                ]),
                html.Tr(children=[
                    html.Th(children=[
                        html.P(
                            children='в т.ч. эффект от принятых ранее тарифных решений',
                            className='m-0'
                        )
                    ], className="fw-bold w-25"),
                    *[html.Th(
                        children=[
                            html.P(
                                className="text-end m-0",
                                children=get_previous_change(route, index, rzd, year, suffix, bases)
                            ),
                        ]) for index, year in enumerate(CON.YEARS, start=1)],
                ])
            ]
            )])



    table = html.Table(className="table table-bordered table-sm mt-1 border-secondary", children=[
        head,
        html.Tbody(
            className="",
            children=table_rows
        ),
    ])
    return html.Div([
        table,
        table2
    ])

def get_color (val):
    if val > 0 : return "text-success"
    if val < 0 : return "text-danger"
    return ""


def get_previous_change(route,index,rzd,year,suffix, bases):
    rzd_changed = rzd[index - 1]
    if suffix == '_gr':
        coeff = route['2024_coeff_x'].values[0]
    else:
        coeff = route['2024_coeff'].values[0]

    rzd_initial = rzd[index - 1] / coeff
    changed = round(
        (rzd_changed - rzd_initial) * (route[f'rules%_{year}{suffix}'].values[0] - 1) + (rzd_changed - rzd_initial) * (bases[index] - 1)
            , 2)

    return [
        changed,
        html.Br(),
        '(', '+' if changed > 0 else '', round(
            (changed)
            * 100 / rzd[index - 1], 2),
        '%)'
    ]


def route_map(route):
    stations = pd.read_excel('data/map/stations.xlsx')
    route_maps = pd.read_excel('data/map/route_maps.xlsx')

    # route_key = str(route['КЛЮЧ_КОД_МАРШРУТА'].values[0]).strip()
    # print(route_key)
    # route_maps['КЛЮЧ_КОД_МАРШРУТА'] = route_maps['КЛЮЧ_КОД_МАРШРУТА'].astype(str).str.strip()
    route_key = route['index'].values[0]

    route_df = route_maps[route_maps['index']==route_key].sort_values(by='№', ascending=True)


    # Слияние с данными станций
    route_df = pd.merge(route_df, stations, how='inner', left_on='КОД СТ', right_on='Код станции РФ')


    # Преобразование координат
    route_df['x'], route_df['y'] = convert_crs(route_df['longitude'], route_df['latitude'])


    # Построение карты
    russia_map = mapFigure()
    russia_map.add_trace(go.Scatter(
        x=route_df['x'], y=route_df['y'], name='Станция',
        text="<b>" + route_df['Станция РФ'] + "</b><br>",
        hoverinfo="text", showlegend=False, mode='markers',
        marker=dict(
            size=3,
            color='red'
        )
    ))

    first_station = route_df.iloc[0]
    last_station = route_df.iloc[-1]
    middle_index = len(route_df) // 2
    middle_station = route_df.iloc[middle_index]

    russia_map.add_annotation(
        x=first_station['x'],
        y=first_station['y'],
        text=first_station['Станция РФ'],
        ax=10,
        ay=-10,
        bgcolor="white"
    )

    russia_map.add_annotation(
        x=last_station['x'],
        y=last_station['y'],
        text=last_station['Станция РФ'],
        ax=10,
        ay=-10,
        bgcolor="white"
    )
    russia_map.add_annotation(
        x=middle_station['x'],
        y=middle_station['y'],
        text=f"{last_station['КИЛОМЕТРАЖ']} км",
        ax=10,
        ay=-10,
        bgcolor="white"
    )

    return russia_map
