import pandas as pd
from dash import html, dcc, callback, MATCH, ALL
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from pages.constants import Constants as CON

#cargo_df = pd.read_hdf('data/cargos.h5', key='cargos')
#cargos = cargo_df[CON.CARGO].unique()

coeffs = pd.read_excel('data/diff.xlsx')
cargos = coeffs[CON.CARGO].unique()
def diff_layout(params):

    return html.Div([
        html.Div([
            html.Div([
                html.H2('Дифференциация', className='my-section__title'),
                # html.Span('Варьируемые параметры', className='my-section__badge')
            ], className="my-section__header"),
            html.Div('',className='my-separate my-separate_width_300 my-separate_vector_left'),
            html.Div([
                dbc.Row([
                    dbc.Col([html.Span('Группа груза', className='my-coefficient__text')],width=6),
                    dbc.Col([html.Span('Коэффициент для базовой индексации', className='my-coefficient__text')],width=3),
                    dbc.Col([html.Span('Коэффициент для тарифных решений', className='my-coefficient__text')],width=3),
                ]),
                *[dbc.Row([
                    dbc.Col([html.Span(cargo, className='my-coefficient__text')],id={'type': 'cargo_name', 'index': cargo},width=6),
                    dbc.Col([dbc.Input(
                        value=coeffs.loc[coeffs['Группа груза'] == cargo, 'base_diff'].iloc[0],
                        type='number', step=0.001, min=0.01,
                        id={'type': 'base_diff', 'index': cargo},
                        className='form-control my-coefficient__number'
                    )], width=3),
                    dbc.Col([dbc.Input(
                        value=coeffs.loc[coeffs['Группа груза'] == cargo, 'rules_diff'].iloc[0],
                        type='number', step=0.001, min=0.01,
                        id={'type': 'rules_diff', 'index': cargo},
                        className='form-control my-coefficient__number'
                    )], width=3),
                ], className='my-coefficient__item') for cargo in cargos]
            ], className='my-section__item my-coefficient__container'),
            html.Div([],id='result_diff')
        ], className="my-section my-section_margin_top"),

], id='pill-tab-diff', className='tab-pane fade show', role='tabpanel')


@callback(
    Output('result_diff', 'children'),
    Input({'type': 'base_diff', 'index': ALL}, 'value'),
    Input({'type': 'rules_diff', 'index': ALL}, 'value'),
    prevent_initial_call = True
)
def update_coefs (base_diff_values,rules_diff_values):
    rows = []

    for index, cargo in enumerate(cargos):
        rows += [
                {'Группа груза': cargo,'base_diff': base_diff_values[index],'rules_diff': rules_diff_values[index]},
            ]
    df = pd.DataFrame(rows)
    df.to_excel('data/diff.xlsx',index=False)