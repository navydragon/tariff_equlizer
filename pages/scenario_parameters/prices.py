from dash import html, dcc, callback, MATCH
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from pages.constants import Constants as CON


def prices_layout(params):
    return html.Div([
        html.Div([
            html.Div([
                html.H2('Конъюнктура', className='my-section__title'),
                # html.Span('Варьируемые параметры', className='my-section__badge')
            ], className="my-section__header"),
            html.Div('',className='my-separate my-separate_width_300 my-separate_vector_left'),
            html.Div([
               #  html.H4('Индикаторы', className='my-section__subtitle'),
                html.Div([
                    dbc.Checklist(
                        id='use_market',
                        options=[
                            {'label': 'Учитывать конъюнктуру', 'value': 'Yes'}
                        ],
                        value=params.get('market',{}).get('use_market',[]),
                        inline=True,
                        switch=True,
                        label_class_name='form-check-label'
                    )
                ], className='form-check form-switch'),
                html.Div([
                    dbc.Checklist(
                        id='compare_base',
                        options=[
                            {'label': 'Сравнивать тарифные решения с базовыми условиями', 'value': 'Yes'}
                        ],
                        value=params.get('market',{}).get('compare_base',[]),
                        inline=True,
                        switch=True,
                        label_class_name='form-check-label'
                    )
                ], className='form-check form-switch'),
                html.Div([
                    dbc.Checklist(
                        id='prices_business',
                        options=[
                            {
                                'label': 'Учитывать изменение цен на товарных рынках',
                                'value': 'Yes'}
                        ],
                        value=params.get('market',{}).get('prices_business',[]),
                        inline=True,
                        switch=True,
                        label_class_name='form-check-label'
                    )
                ], className='form-check form-switch')
            ],className='my-section__item'),

        ], className="my-section my-section_margin_top"),
        # html.Div([
        #     html.Div([
        #         html.H2('Экспортные цены', className='my-section__title'),
        #         # html.Span('Варьируемые параметры',
        #         #           className='my-section__badge')
        #     ], className="my-section__header"),
        #     html.Div(
        #         className='my-separate my-separate_width_300 my-separate_vector_left'),
        #     html.Div([
        #         html.H4('Вид груза', className='my-section__subtitle'),
        #         dbc.Select(
        #             id='cargo_proces',
        #             options=['Уголь каменный'],
        #             value='Уголь каменный',
        #             # disabled=True,
        #             className='form-select'
        #         ),
        #     ], className='my-section__item'),
        #     html.Div([
        #         html.Div([
        #             html.Div([
        #                 html.H4('Восток', className='my-section__subtitle'),
        #                 dbc.Select(
        #                     id='market_coal_east',
        #                     options=[
        #                                 {'label': '50', 'value': 50},
        #                                 {'label': '100', 'value': 100},
        #                                 {'label': '138', 'value': 'Текущие'},
        #                                 {'label': '150', 'value': 150},
        #                                 {'label': '200', 'value': 200}
        #                             ],
        #                     value='Текущие',
        #                     className='form-select'
        #                 ),
        #             ], className="d-flex flex-column w-100 mr-3"),
        #             html.Div([
        #                 html.H4('Юг', className='my-section__subtitle'),
        #                 dbc.Select(
        #                     id='market_coal_south',
        #                     options=[
        #                         {'label': '50', 'value': 50},
        #                         {'label': '100', 'value': 100},
        #                         {'label': '103', 'value': 'Текущие'},
        #                         {'label': '150', 'value': 150},
        #                         {'label': '200', 'value': 200}
        #                     ],
        #                     value='Текущие',
        #                     className='form-select'
        #                 ),
        #             ], className="d-flex flex-column w-100 mr-3"),
        #             html.Div([
        #                 html.H4('Северо-Запад', className='my-section__subtitle'),
        #                 dbc.Select(
        #                     id='market_coal_west',
        #                     options=[
        #                         {'label': '50', 'value': 50},
        #                         {'label': '100', 'value': 100},
        #                         {'label': '106', 'value': 'Текущие'},
        #                         {'label': '150', 'value': 150},
        #                         {'label': '200', 'value': 200}
        #                     ],
        #                     value='Текущие',
        #                     className='form-select'
        #                 ),
        #             ], className="d-flex flex-column w-100 mr-3")
        #         ],className='d-flex mt-3')
        #
        #     ], className='my-section__item'),
        #
        # ], className="my-section my-section_margin_top"),
        html.Div([
            html.Div([
                html.H2('Коэффициенты выпадения', className='my-section__title'),
                # html.Span('Варьируемые параметры', className='my-section__badge')
            ], className="my-section__header"),
            html.Div(
                className='my-separate my-separate_width_300 my-separate_vector_left'),
            html.Div(
              html.Em('Установите флажок для ввода значения коэффициента вручную')
            ),
            html.Div([
                html.Div([
                    dbc.Checkbox(
                        id={'type': 'coefficient_method', 'index': cargo},
                        value=False,
                    ),
                    html.Span(cargo, className='my-coefficient__text'),
                    dbc.Input(
                        type='text', value='прогноз', id={'type': 'coefficient_input', 'index': cargo}, disabled=True,
                        className='form-control my-coefficient__number'
                    )
                ], className='my-coefficient__item') for cargo in CON.CARGOS
            ], className='my-section__item my-coefficient__container'),

        ], className="my-section my-section_margin_top"),
], id='pill-tab-prices', className='tab-pane fade show', role='tabpanel')


@callback(
    Output({'type': 'coefficient_input', 'index': MATCH}, 'disabled'),
    Output({'type': 'coefficient_input', 'index': MATCH}, 'type'),
    Output({'type': 'coefficient_input', 'index': MATCH}, 'value'),
    Output({'type': 'coefficient_input', 'index': MATCH}, 'min'),
    Output({'type': 'coefficient_input', 'index': MATCH}, 'step'),
    Input({'type': 'coefficient_method', 'index': MATCH}, 'value'),
    prevent_initial_call = True
)
def coefficient_method (value):
    if value == False:
        return True,'text','прогноз','1','0.1'
    return False,'number',1,0,0.1