
import dash

from dash import html
from dash import Dash, html, dcc, callback, Input, Output
from pages.reference.invest import invest_layout
from pages.reference.costs import costs_layout
from pages.reference.diff import diff_layout

# dash.register_page(__name__, name="Исходные данные", path='/reference', order=3, my_class='my-navbar__icon-3')


def layout():
    return html.Div([
        html.H2('Исходные данные', className="m-4"),
        dcc.Tabs(id="tabs", value='invest',
                 children=[
                     dcc.Tab(label='Инвест. проекты', value='invest'),
                     dcc.Tab(label='Темпы роста', value='costs'),
                     dcc.Tab(label='Дифференциация тарифоной нагрузки', value='diff'),
                 ]),
        html.Section([], id='tabs-content', className='my-section')
    ])


@callback(Output('tabs-content', 'children'),
          Input('tabs', 'value'))
def render_content(tab):
    if tab == 'invest':
        return html.Div([invest_layout()])
    elif tab == 'costs':
        return html.Div([costs_layout()])
    elif tab == 'diff':
        return html.Div([diff_layout()])