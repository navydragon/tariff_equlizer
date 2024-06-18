import pandas as pd
from dash import html, dcc, callback, MATCH, ALL
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from pages.constants import Constants as CON

cargos = CON.IPEM_CARGOS

# DIRECTIONS = ['экспорт_дв', 'экспорт_сз', 'экспорт_юг', 'внутренние']
DIRECTIONS = ['экспорт (Восток)',
'экспорт (Северо-Запад)',
'экспорт (Юг)',
'внутренние'
]

def ipem_layout(params):
    coeffs = pd.read_excel('data/ipem_coeffs.xlsx')
    coal = pd.read_excel('data/ipem_coal.xlsx')
    csr_coeffs = pd.read_excel('data/csr_coeffs.xlsx')
    prices_dollar = pd.read_excel('data/prices$.xlsx')
    return html.Div([
        html.Div([
            html.Div([
                html.H2('Параметры транспортной составляющей', className='my-section__title'),
                # html.Span('Варьируемые параметры', className='my-section__badge')
            ], className="my-section__header"),
            html.Div('',className='my-separate my-separate_width_300 my-separate_vector_left'),
            html.Div([
                html.Div([
                    html.Label('Условия международной торговли'),
                    dcc.Dropdown(
                        options=['CIF','FOB'],
                        value=params.get('ipem').get('cif_fob'),
                        id='cif_fob'
                    ),
                ]),
                html.Div([
                    dbc.Checklist(
                        id='index_sell_prices',
                        options=[
                            {'label': 'Учитывать рост цен на товарных рынках (не действвует на эквалайзер ЦСР)', 'value': True}
                        ],
                        value=params.get("ipem",[]).get("index_sell_prices",[]),
                        inline=True,
                        switch=True,

                        label_class_name='form-check-label'
                    )
                ], className='form-check form-switch'),
                html.Div([
                    html.Label('Вариант',  className='mt-2 mx-2'),
                    dcc.Dropdown(
                        id='price_variant',
                        options=['Минэк','ЦСР'],
                        searchable=True,
                        value=params.get("ipem",[]).get("price_variant",[]),
                        className='mb-2'
                    ),
                    html.Table([
                        html.Thead([
                            html.Tr([
                                html.Th('Группа груза', style={'fontSize':'12px','color':'#797D8C', 'width':'20%'}, className='revenue_th', scope='col'),
                                *[html.Th(year, className='revenue_th', scope='col') for year in CON.YEARS]
                            ])
                        ]),
                        html.Tbody([
                            *[html.Tr([
                                html.Td(cargo, className='revenue_totals'),
                                *[html.Td([
                                    dbc.Input(
                                        id={'type': f'ipem_price_{year}', 'index': cargo},
                                        value=coeffs.loc[coeffs['Группа груза'] == cargo, f'ЦЕНА_{year}'].iloc[0],
                                        type='number',  min=0.01,
                                        className="form-control")
                                ]) for year in CON.YEARS]
                            ], className='text-center') for cargo in cargos],
                        ])
                    ], id='prices_table', className='table table-sm'),
                    html.Table([
                        html.Thead([
                            html.Tr([
                                html.Th('Группа груза', style={'fontSize':'12px','color':'#797D8C', 'width':'20%'}, className='revenue_th', scope='col'),
                                html.Th('Направление', style={'fontSize':'12px','color':'#797D8C', 'width':'20%'}, className='revenue_th', scope='col'),
                                *[html.Th(year, className='revenue_th', scope='col') for year in CON.YEARS]
                            ])
                        ]),
                        html.Tbody([
                            *[html.Tr([
                                html.Td(cargo, className='revenue_totals'),
                                html.Td(direction, className='revenue_totals'),
                                *[html.Td([
                                    dbc.Input(
                                        id={'type': f'ipem_price_csr_{year}', 'index': f"{cargo}_{direction}"},
                                        value=csr_coeffs.loc[(csr_coeffs['Группа груза'] == cargo) &(csr_coeffs['Вид сообщения'] == direction), f'ЦЕНА_ЦСР_{year}'].iloc[0],
                                        type='number', min=0.01,
                                        className="form-control")
                                ]) for year in CON.YEARS]
                            ], className='text-center') for cargo in cargos for direction in DIRECTIONS],
                        ])
                    ], className='table table-sm', id='prices_table_csr'),
                    html.Div([
                        dbc.Checklist(
                            id='index_sell_coal',
                            options=[
                                {
                                    'label': 'Отдельные коэффициенты для угля',
                                    'value': True}
                            ],
                            value=params.get("ipem",[]).get("index_sell_coal",[]),
                            inline=True,
                            switch=True,
                            label_class_name='form-check-label'
                        )
                    ], className='form-check form-switch'),
                    html.Div([
                        html.Label('Курс доллара (Руб. за 1 $)', className='mt-2 mx-2'),
                        html.Table([
                            html.Tr([
                                # html.Th('', style={'fontSize':'12px','color':'#797D8C', 'width':'20%'}, className='revenue_th', scope='col'),
                                html.Th('2024', className='revenue_th', scope='col'),
                                *[html.Th(year, className='revenue_th', scope='col') for year in CON.YEARS]
                            ]),
                            html.Tr([
                                # html.Td('', className='revenue_totals'),
                                html.Td([
                                dbc.Input(
                                    id={'type': f'$_price', 'index': '2024'},
                                    value=prices_dollar.loc[0,'prices'],
                                    type='number', min=0.01,
                                    className="form-control")
                                ]),
                                *[html.Td([
                                    dbc.Input(
                                        id={'type': f'$_price', 'index': year},
                                        value=prices_dollar.loc[index,'prices'],
                                        type='number', step=0.001, min=0.01,
                                        className="form-control")
                                ]) for index, year in enumerate(CON.YEARS,start=1)]
                            ], className='text-center')
                        ]),
                        html.Label('Индексы для угля', className='mt-2 mx-2'),
                        html.Table([
                            html.Thead([
                                html.Tr([
                                    html.Th('Направление', style={'fontSize':'12px','color':'#797D8C', 'width':'20%'}, className='revenue_th', scope='col'),
                                    *[html.Th(year, className='revenue_th', scope='col') for year in [2024]+CON.YEARS]
                                ])
                            ]),
                            html.Tbody([
                                *[html.Tr([
                                    html.Td(direction, className='revenue_totals'),
                                    *[html.Td([
                                        dbc.Input(
                                            id={'type': f'coal_price_{year}', 'index': direction},
                                            value=coal.loc[coal['Вид сообщения'] == direction, f'ЦЕНА_УГОЛЬ_{year}'].iloc[0],
                                            type='number', step=0.001, min=0.01,
                                            className="form-control")
                                    ]) for year in [2024]+CON.YEARS]
                                ], className='text-center') for direction in DIRECTIONS],
                            ])
                       ], className='table table-sm')
                    ], 'ipem_price_coal'),
                ], id='ipem_price_coeffs'),

                html.Div([
                    dbc.Checklist(
                        id='index_oper',
                        options=[
                            {'label': 'Учитывать рост операторской составляющей', 'value': True}
                        ],
                        inline=True,
                        switch=True,
                        value=params.get("ipem",[]).get("index_oper",[]),
                        label_class_name='form-check-label'
                    )
                ], className='form-check form-switch'),
                html.Div([
                    html.Table([
                        html.Thead([
                            html.Tr([
                                html.Th('Группа груза', style={'fontSize':'12px','color':'#797D8C', 'width':'20%'}, className='revenue_th', scope='col'),
                                *[html.Th(year, className='revenue_th', scope='col') for year in CON.YEARS]
                            ])
                        ]),
                        html.Tbody([
                            *[html.Tr([
                                html.Td(cargo, className='revenue_totals'),
                                *[html.Td([
                                    dbc.Input(
                                        id={'type': f'ipem_oper_{year}', 'index': cargo},
                                        value=coeffs.loc[coeffs['Группа груза'] == cargo, f'ОПЕРАТОРЫ_{year}'].iloc[0],
                                        type='number', step=0.001, min=0.01,
                                        className="form-control")
                                ]) for year in CON.YEARS]
                            ], className='text-center') for cargo in cargos],
                        ])
                ], className='table table-sm'),], id='ipem_oper_coeffs'),
                html.Div([
                    dbc.Checklist(
                        id='index_per',
                        options=[
                            {'label': 'Учитывать рост расходов на перевалку', 'value': True}
                        ],
                        value=params.get("ipem",[]).get("index_per",[]),
                        inline=True,
                        switch=True,
                        label_class_name='form-check-label'
                    )
                ], className='form-check form-switch'),
                html.Div([
                    html.Table([
                        html.Thead([
                            html.Tr([
                                html.Th('Группа груза', style={'fontSize':'12px','color':'#797D8C', 'width':'20%'}, className='revenue_th', scope='col'),
                                *[html.Th(year, className='revenue_th', scope='col') for year in CON.YEARS]
                            ])
                        ]),
                        html.Tbody([
                            *[html.Tr([
                                html.Td(cargo, className='revenue_totals'),
                                *[html.Td([
                                    dbc.Input(
                                        id={'type': f'ipem_per_{year}', 'index': cargo},
                                        value=coeffs.loc[coeffs['Группа груза'] == cargo, f'ПЕРЕВАЛКА_{year}'].iloc[0],
                                        type='number', step=0.001, min=0.01,
                                        className="form-control")
                                ]) for year in CON.YEARS]
                            ], className='text-center') for cargo in cargos],
                        ])
                ], className='table table-sm'),], id='ipem_per_coeffs'),
            ], className='my-section__item my-coefficient__container'),
            html.Div([], id='result_diff_ipem'),
            html.Div([], id='result_diff_ipem2'),
            html.Div([], id='result_diff_ipem3'),
        ], className="my-section my-section_margin_top"),

], id='pill-tab-transport', className='tab-pane fade show', role='tabpanel')


@callback(
    Output('result_diff_ipem', 'children',allow_duplicate=True),
    *[Input({'type': f'ipem_price_{year}', 'index': ALL}, 'value') for year in CON.YEARS],
    *[Input({'type': f'ipem_oper_{year}', 'index': ALL}, 'value') for year in CON.YEARS],
    *[Input({'type': f'ipem_per_{year}', 'index': ALL}, 'value') for year in CON.YEARS],
    prevent_initial_call = True
)
def update_coefs (*args):
    num_params_per_year = len(CON.YEARS)
    ipem_prices = args[:num_params_per_year]
    ipem_oper = args[num_params_per_year:2*num_params_per_year]
    ipem_per = args[2 * num_params_per_year:]
    rows = []

    for index, cargo in enumerate(cargos):
        rows += [{
            'Группа груза': cargo,
            'ЦЕНА_2025': ipem_prices[0][index],
            'ЦЕНА_2026': ipem_prices[1][index],
            'ЦЕНА_2027': ipem_prices[2][index],
            'ЦЕНА_2028': ipem_prices[3][index],
            'ЦЕНА_2029': ipem_prices[4][index],
            'ЦЕНА_2030': ipem_prices[5][index],
            'ОПЕРАТОРЫ_2025': ipem_oper[0][index],
            'ОПЕРАТОРЫ_2026': ipem_oper[1][index],
            'ОПЕРАТОРЫ_2027': ipem_oper[2][index],
            'ОПЕРАТОРЫ_2028': ipem_oper[3][index],
            'ОПЕРАТОРЫ_2029': ipem_oper[4][index],
            'ОПЕРАТОРЫ_2030': ipem_oper[5][index],
            'ПЕРЕВАЛКА_2025': ipem_per[0][index],
            'ПЕРЕВАЛКА_2026': ipem_per[1][index],
            'ПЕРЕВАЛКА_2027': ipem_per[2][index],
            'ПЕРЕВАЛКА_2028': ipem_per[3][index],
            'ПЕРЕВАЛКА_2029': ipem_per[4][index],
            'ПЕРЕВАЛКА_2030': ipem_per[5][index],
        }]
    df = pd.DataFrame(rows)
    df.to_excel('data/ipem_coeffs.xlsx',index=False)

@callback(
    Output('result_diff_ipem','children', allow_duplicate=True),
    *[Input({'type': f'ipem_price_csr_{year}', 'index': ALL}, 'value') for year in CON.YEARS],
    prevent_initial_call=True,
)
def update_csr_prices(*args):
    rows = []
    index=0

    for cr_index, cargo in enumerate(cargos):
        for dr_index, direction in enumerate(DIRECTIONS):
            rows += [{
                'Группа груза': cargo,
                'Вид сообщения': direction,
                'ЦЕНА_ЦСР_2025': args[0][index],
                'ЦЕНА_ЦСР_2026': args[1][index],
                'ЦЕНА_ЦСР_2027': args[2][index],
                'ЦЕНА_ЦСР_2028': args[3][index],
                'ЦЕНА_ЦСР_2029': args[4][index],
                'ЦЕНА_ЦСР_2030': args[5][index],
            }]
            index += 1
    df = pd.DataFrame(rows)
    df.to_excel('data/csr_coeffs.xlsx', index=False)


@callback(
    Output('result_diff_ipem2', 'children'),
    *[Input({'type': f'coal_price_{year}', 'index': ALL}, 'value') for year in [2024]+CON.YEARS],
    prevent_initial_call = True
)
def update_coal (*args):
    new_years = [2024] +  CON.YEARS
    num_params_per_year = len(new_years)
    coal_prices = args[:num_params_per_year]
    rows = []

    for index, direction in enumerate(DIRECTIONS):
        rows += [{
            'Группа груза': 'Уголь',
            'Вид сообщения': direction,
            'ЦЕНА_УГОЛЬ_2024': coal_prices[0][index],
            'ЦЕНА_УГОЛЬ_2025': coal_prices[1][index],
            'ЦЕНА_УГОЛЬ_2026': coal_prices[2][index],
            'ЦЕНА_УГОЛЬ_2027': coal_prices[3][index],
            'ЦЕНА_УГОЛЬ_2028': coal_prices[4][index],
            'ЦЕНА_УГОЛЬ_2029': coal_prices[5][index],
            'ЦЕНА_УГОЛЬ_2030': coal_prices[6][index],
        }]
    df = pd.DataFrame(rows)
    df.to_excel('data/ipem_coal.xlsx', index=False)

@callback(
    Output('result_diff_ipem3', 'children'),
    Input({'type': '$_price', 'index': ALL}, 'value'),
    prevent_initial_call = True
)
def update_dollar(prices):
    df = pd.DataFrame(prices, columns=['prices'])
    df.to_excel('data/prices$.xlsx',index=False)

@callback(
    Output('ipem_price_coeffs','style'),
    Input('index_sell_prices','value')
)
def switch_ipem_price_coeffs(value):
    if value == [True]:
        return {'display':'block'}
    return {'display': 'none'}

@callback(
    Output('ipem_price_coal','style'),
    Input('index_sell_coal','value')
)
def switch_ipem_price_coal(value):
    if value == [True]:
        return {'display':'block'}
    return {'display': 'none'}


@callback(
    Output('ipem_oper_coeffs','style'),
    Input('index_oper','value')
)
def switch_ipem_oper_coeffs(value):
    if value == [True]:
        return {'display':'block'}
    return {'display': 'none'}

@callback(
    Output('ipem_per_coeffs','style'),
    Input('index_per','value')
)
def switch_ipem_per_coeffs(value):
    if value == [True]:
        return {'display':'block'}
    return {'display': 'none'}


@callback(
    Output('prices_table','style'),
    Output('prices_table_csr','style'),
    Input('price_variant','value')
)
def switch_price_variant(variant):
    if variant == 'Минэк':
        return ({'display':'block'},{'display':'none'})
    return ({'display': 'none'}, {'display': 'block'})