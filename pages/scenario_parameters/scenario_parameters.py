import dash
import dash_bootstrap_components as dbc
from dash import html, callback
from dash.dependencies import Input, Output

import pages.scenario_parameters.diff as diff
import pages.scenario_parameters.ipem as ipem
import pages.scenario_parameters.revenues as revenues
from pages.helpers import get_last_params

tab_labels = html.Ul([
html.Li(html.A('Тарифы', href='#pill-tab-revenues', id='pill-contact-tab',role="tab", className='nav-link nav-pills-link active', **{'data-bs-toggle': 'tab'}), style={'margin-right':'12px'}),
        html.Li(html.A('Дифференциация', href='#pill-tab-diff', id='pill-profile-tab',role="tab", className='nav-link nav-pills-link', **{'data-bs-toggle': 'tab'}), style={'margin-right':'12px'}),
        html.Li(html.A('Экономика перевозки грузов', href='#pill-tab-transport', id='pill-transport-tab',role="tab", className='nav-link nav-pills-link', **{'data-bs-toggle': 'tab'}), style={'margin-right':'12px'}),
    ], className='nav nav-pills', id='pill-myTab', role='tablist')



# отрисовка верхнего меню
def scenario_parameters():
    PARAMS = get_last_params()
    # PARAMS = {}
    return dbc.Offcanvas(
    className='offcanvas offcanvas-end settings-panel border-0 settings-panel-design',
    id='settings-offcanvas',
    is_open=False,
    placement='end',
    title=html.H2('Параметры сценария', className='my-section__title'),
    #tabIndex='-1',
    # ariaLabelledby='settings-offcanvas',
    children=[
        html.Div([
            tab_labels,
            html.Div([
                revenues.revenues_layout(PARAMS),
                diff.diff_layout(PARAMS),
                ipem.ipem_layout(PARAMS),
            ], className="tab-content", id="pill-myTabContent"),
            html.Button('Рассчитать', id='calculate-button', className='btn btn-primary offcanvas__btn', style={'width': '300px'}, **{'data-bs-dismiss': 'offcanvas', 'aria-label': 'Close'})
        ], className="offcanvas-body"),
    ]
)


def toggle_button():
    return html.A(className="card setting-toggle", href="#settings-offcanvas", **{"data-bs-toggle": "offcanvas"}, children=[
        html.Div(className="card-body d-flex align-items-center py-md-2 px-2 py-1 card-body_type_color", children=[
            html.Div(className="bg-green-color position-relative rounded-start", style={"height": "34px", "width": "28px"}, children=[
                html.Div(className="settings-popover", children=[
                    html.Span(className="ripple", children=[
                        html.Span(className="fa-spin position-absolute all-0 d-flex flex-center", children=[
                            html.Span(className="icon-spin position-absolute all-0 d-flex flex-center", children=[
                                html.Div(className="my__toggle-icon")
                            ])
                        ])
                    ])
                ])
            ]),
            html.Small(className="text-uppercase text-white fw-bold bg-green-color py-2 pe-2 ps-1 rounded-end", children="параметры")
        ])
    ], id='toggle_sp')


@callback(
    Output('settings-offcanvas','is_open'),
    Input('toggle_sp','n_clicks'),
    Input('calculate-button','n_clicks'),
    prevent_initial_call=True
)
def open_sp(open,calculate):
    ctx = dash.callback_context
    if ctx.triggered:
        if 'toggle_sp' in ctx.triggered[0]['prop_id']:
            return True
        else:
            return False



@callback(
    Output('use_market','value'),
    Output('compare_base','value'),
    Output('prices_business','value'),
    # Output('market_coal_west','value'),
    # Output('market_coal_east','value'),
    # Output('market_coal_south','value'),
    Input('toggle_sp','n_clicks'),
    prevent_initial_call=True
)
def pass_parameter_values(open):
    params = get_last_params()
    return (
        params['market']['use_market'],
        params['market']['compare_base'],
        params['market']['prices_business'],
        # params['market']['coal']['west'],
        # params['market']['coal']['east'],
        # params['market']['coal']['south'],
    )