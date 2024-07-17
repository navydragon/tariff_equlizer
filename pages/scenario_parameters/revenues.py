from dash import html, dcc, callback, MATCH, ALL
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from pages.constants import Constants as CON
import pandas as pd
import numpy as np
from pages.data import get_revenue_parameters, process_revenue_parameters
import pages.scenario_parameters.tarif_rules as tr
import pages.scenario_parameters.tarif_rules_prev as tr_prev

revenue_parameters = get_revenue_parameters()
#revenue_parameters = pd.read_excel('data/revenues_parameters.xlsx')

indexation_variant = revenue_parameters[revenue_parameters['year'] == 0]['param'].values[0]

disp = ["", "none"] if indexation_variant == 'Индексация по расп.N2991-р' else ["none", ""]
index_param = {"id": 'indexation' , "name": 'Индексация базовая', "base_value": 1.076}
params = [
    {"id": 'cap_rem' , "name": 'Капитальный ремонт', "base_value": 1},
    {"id": 'taxes' , "name": 'Налоговая надбавка', "base_value": 1},
    {"id": 'tb', "name": 'Транспортная безопасность', "base_value": 1},
    {"id": 'invest', "name": 'Инвестиционный тариф', "base_value": 1},
]
icd_param = {"id": 'icd' , "name": 'Индекс Затраты+', "base_value": 1}


def revenues_layout(last_params):
    return html.Div([
        html.Div([
            html.Div([
                html.H2('Изменения', className='my-section__title'),
            ], className="my-section__header"),
            html.Div('',className='my-separate my-separate_width_300 my-separate_vector_left'),
            html.Div([
                html.Div([
                    dbc.Checklist(
                        id='epl_change',
                        options=[
                            {'label': 'Учитывать изменение грузооборота',
                             'value': True}
                        ],
                        value=last_params.get("epl_change",[]),
                        inline=True,
                        switch=True,
                        label_class_name='form-check-label'
                    )
                ], className='my-section__item'),
                html.Div([
                    dbc.Checklist(
                        id='market_loss',
                        options=[
                            {'label': 'Учитывать выпадение объемов',
                             'value': True}
                        ],
                        value=last_params.get("market_loss", []),
                        inline=True,
                        switch=True,
                        label_class_name='form-check-label'
                    )
                ], className='my-section__item'),
            ],className='my-section__item'),

        ], className="my-section my-section_margin_top"),
        html.Div([
            html.Div([
                html.H2('Базовые тарифные решения', className='my-section__title'),
                # html.Span('Варьируемые параметры', className='my-section__badge')
            ], className="my-section__header"),
            html.Div('',className='my-separate my-separate_width_300 my-separate_vector_left'),
            html.Div([
                html.Div([
                    html.H4('Варианты индексации', className='my-section__subtitle'),
                    dbc.Select(
                        id='indexation_variant',
                        options=['Индексация по расп.N2991-р', 'Индекс Затраты+'],
                        value=indexation_variant,
                        # disabled=True,
                        className='form-select'
                    ),
                ], className='my-section__item')
            ],className='my-section__item'),

        ], className="my-section my-section_margin_top"),
        html.Div([
            html.Div([
                html.H2('Коэффициенты', className='my-section__title'),
                # html.Span('Варьируемые параметры', className='my-section__badge')
            ], className="my-section__header"),
            html.Div(className='my-separate my-separate_width_300 my-separate_vector_left'),
            html.Div([
                # html.H4('Период', className='my-section__subtitle'),
                html.Table([
                    html.Thead([
                        html.Tr([
                            html.Th('Наименование', style={'fontSize':'12px','color':'#797D8C', 'width':'20%'}, scope='col'),
                            html.Th('2024', className='revenue_th', scope='col'),
                            *[html.Th(year, className='revenue_th', scope='col') for year in CON.YEARS]
                        ])
                    ]),
                    html.Tbody([
                        html.Tr(print_row_coefs(index_param),  id='indexes_div', style={"display":disp[0]}),
                        html.Tr(print_row_coefs(icd_param),  id='indexes_icd_div', style={"display":disp[1]}),
                        *[html.Tr(print_other_coefs(param), style={"display":""}) for param in params],
                        html.Tr([
                            html.Td('Итоговый коэффициент', className='revenue_totals'),
                            html.Td('1.107',id='2024_year_total_index'),
                            *[html.Td(0, id=str(year)+'_year_total_index') for year in CON.YEARS]
                        ], className='text-center', id='total_index_row'),
                    ])
                ], className='table table-sm')
            ], className='my-section__item table-responsive'),


        ], className="my-section my-section_margin_top"),
        html.Div([
            html.Div([
                html.H2('Отдельные тарифные решения', className='my-section__title'),
                # html.Span('Варьируемые параметры',  className='my-section__badge')
            ], className="my-section__header"),
            html.Div(
                className='my-separate my-separate_width_300 my-separate_vector_left'),
            html.Div(
               tr.rules_layout(),
            ),
            html.Div([
                html.H2('Принятые ранее тарифные решения', className='my-section__title'),
            ], className="my-section__header"),
            html.Div(
                className='my-separate my-separate_width_300 my-separate_vector_left'),
            html.Div(
                tr_prev.rules_layout(),
            )


        ], className="my-section my-section_margin_top"),
], id='pill-tab-revenues', className='tab-pane fade show active', role='tabpanel')



def print_row_coefs(param):
    return [
        html.Td([
            html.P(param['name'], style={'fontSize': '12px', 'color': '#2D3748'})
        ]),
        html.Td([
            html.Div([
                dbc.Checkbox(id={'type': param['id'] + '_checkbox', 'index': 2024}, value=True, disabled=True),
                dbc.Input(id={'type': param['id'] + '_input', 'index': 2024}, value=1.076,
                          type='number', step=0.001, min=0.01, className="form-control", disabled=True)
            ], className='input-group'),
        ]),
        *[html.Td([
            html.Div([
                dbc.Checkbox(
                    id={'type': param['id'] + '_checkbox', 'index': year},
                    value=get_revenues_parameter(revenue_parameters, param, 'checkbox', year),
                    # value=revenue_parameters[(revenue_parameters['year'] == year) & (revenue_parameters['param'] == param['id'])]['checkbox'].values[0]
                ),
                dbc.Input(
                    id={'type': param['id'] + '_input', 'index': year},
                    type='number', step=0.001, min=0.01, className="form-control",
                    value=get_revenues_parameter(revenue_parameters, param, 'value', year),
                    #value=revenue_parameters[(revenue_parameters['year'] == year) & (revenue_parameters['param'] == param['id'])]['value'].values[0]
                )
            ], className='d-flex align-items-center')
        ]) for idx, year in enumerate(CON.YEARS)]
    ]


def print_other_coefs(param):
    res = [
        html.Td([
            html.P(param['name'], style={'fontSize': '12px', 'color': '#2D3748'})
        ]),
        html.Td([
            html.Div([
                dbc.Checkbox(id={'type': param['id'] + '_checkbox', 'index': 2024}, value=True, disabled=True),
                dbc.Input(id={'type': param['id'] + '_input', 'index': 2024}, value=revenue_parameters[(revenue_parameters['year'] == 2024) & (revenue_parameters['param'] == param['id'])]['value'].values[0],
                          type='number', step=0.001, min=0.01, className="form-control", disabled=True)
            ], className='input-group', style={'width':'80px'}),
        ]),
        *[html.Td([
            html.Div([
                dbc.Checkbox(
                    id={'type': param['id'] + '_checkbox', 'index': year},
                    value=get_revenues_parameter(revenue_parameters, param, 'checkbox', year),
                ),
                dbc.Input(
                    id={'type': param['id'] + '_input', 'index': year},
                    type='number', step=0.001, min=0.01, className="form-control",
                    value=get_revenues_parameter(revenue_parameters, param, 'value', year),
                )
            ], className='d-flex align-items-center', style={'width':'80px'})
        ]) for idx, year in enumerate(CON.YEARS)]
    ]
    return res


@callback(
    [Output(str(year) + '_year_total_index', 'children') for year in CON.YEARS],
    Input('indexation_variant','value'),
    Input({'type': 'indexation_checkbox', 'index': ALL}, 'value'),
    Input({'type': 'indexation_input', 'index': ALL}, 'value'),
    Input({'type': 'cap_rem_checkbox', 'index': ALL}, 'value'),
    Input({'type': 'cap_rem_input', 'index': ALL}, 'value'),
    Input({'type': 'taxes_checkbox', 'index': ALL}, 'value'),
    Input({'type': 'taxes_input', 'index': ALL}, 'value'),
    Input({'type': 'tb_checkbox', 'index': ALL}, 'value'),
    Input({'type': 'tb_input', 'index': ALL}, 'value'),
    Input({'type': 'invest_checkbox', 'index': ALL}, 'value'),
    Input({'type': 'invest_input', 'index': ALL}, 'value'),
    Input({'type': 'icd_checkbox', 'index': ALL}, 'value'),
    Input({'type': 'icd_input', 'index': ALL}, 'value'),
)
def calculate_total_index(
    indexation_variant,
    indexation_checkboxes, indexation_values,
    cap_rem_checkboxes, cap_rem_values,
    taxes_checkboxes, taxes_values,
    tb_checkboxes, tb_values,
    invest_checkboxes, invest_values,
    icd_checkboxes, icd_values
):

    global revenue_parameters
    result = []

    rows = [
        {'year': 2024,'param': 'indexation','checkbox': bool(indexation_checkboxes[0]),'value': indexation_values[0]},
        {'year': 2024,'param': 'cap_rem','checkbox': bool(cap_rem_checkboxes[0]),'value': cap_rem_values[0]},
        {'year': 2024,'param': 'taxes','checkbox': bool(taxes_checkboxes[0]),'value': taxes_values[0]},
        {'year': 2024,'param': 'tb','checkbox': bool(tb_checkboxes[0]),'value': tb_values[0]},
        {'year': 2024,'param': 'invest','checkbox': bool(invest_checkboxes[0]),'value': invest_values[0]},
        {'year': 2024,'param': 'icd','checkbox': bool(icd_checkboxes[0]),'value': icd_values[0]}
    ]

    if indexation_variant != 'Индексация по расп.N2991-р':
        values = icd_values
        checkboxes = icd_checkboxes
    else:
        values = indexation_values
        checkboxes = indexation_checkboxes


    for index, year in enumerate(CON.YEARS):
        total_index = 1
        if checkboxes[index+1]:
            total_index *= values[index+1]
        if cap_rem_checkboxes[index + 1]:
            total_index *= cap_rem_values[index + 1] / cap_rem_values[index]
        if taxes_checkboxes[index + 1]:
            total_index *= taxes_values[index + 1] / taxes_values[index]
        if tb_checkboxes[index + 1]:
            total_index *= tb_values[index + 1] / tb_values[index]
        if invest_checkboxes[index + 1]:
            total_index *= invest_values[index + 1] / invest_values[index]
        # добавляем строки в df
        rows += [
            {'year': year,'param': 'indexation','checkbox': bool(indexation_checkboxes[index+1]),'value': indexation_values[index+1]},
            {'year': year,'param': 'cap_rem','checkbox': bool(cap_rem_checkboxes[index+1]),'value': cap_rem_values[index+1]},
            {'year': year,'param': 'taxes','checkbox': bool(taxes_checkboxes[index+1]),'value': taxes_values[index+1]},
            {'year': year,'param': 'tb','checkbox': bool(tb_checkboxes[index+1]),'value': tb_values[index+1]},
            {'year': year,'param': 'invest','checkbox': bool(invest_checkboxes[index+1]),'value': invest_values[index+1]},
            {'year': year,'param': 'icd','checkbox': bool(icd_checkboxes[index+1]),'value': icd_values[index+1]}
        ]

        result.append(round(total_index,3))
    # Добавляем вариант
    rows.append(({'year': 0,'param': indexation_variant,'checkbox': True,'value': 0}))
    df = pd.DataFrame(rows)
    df = process_revenue_parameters(df, 'revenue_parameters')

    revenue_parameters = df
    return result




@callback(
    Output('indexes_div', 'style'),
    Output('indexes_icd_div', 'style'),
    Input('indexation_variant', 'value'),
    prevent_initial_call=True
)
def change_indexation_variant(variant):
    a = {"display":""}
    b = {"display":"none"}
    if variant == 'Индексация по расп.N2991-р':
        return a,b
    return b,a


def get_revenues_parameter(df, param, type, year):
    while year >= df['year'].min():
        values = df[(df['year'] == year) & (df['param'] == param['id'])][type].values
        if len(values) > 0:
            return values[0]
        year -= 1
    return None