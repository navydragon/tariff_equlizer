
import dash
from dash import Dash, html, dcc, callback, Input, Output, ALL
import dash_bootstrap_components as dbc


# отрисовка верхнего меню
def navbar():
    return html.Nav(
    className='my-navbar',
    children=[
        dcc.Location(id='location'),
        html.Img(className='my-navbar__logo', src='assets/img/logo.png'),
        html.Ul(
            className='my-navbar__list',
            children=[
                html.Li(
                    className='my-navbar__item',
                    id={'type': 'navitem', 'index': page['name']},
                    children=[
                        html.Div([
                            html.Div(className='my-navbar__icon ' + str(
                                page['my_class']))
                        ], className='my-navbar__icon-container'),
                        html.A(page['name'], href=page['path'],
                               className='my-navbar__text'),
                    ]
                )
                for index, page in enumerate(dash.page_registry.values()) if
                page['path'] != '/'
            ]
        ),
    ]
)

@callback (
    Output({'type': 'navitem', 'index': ALL}, 'className'),
    Input('location','pathname')
)

def set_active(path):
    res = []
    for index, page in enumerate(dash.page_registry.values()):
        if page['path'] == '/':
            continue
        if page['path'] == path:
            res.append("my-navbar__item my-navbar__item_type_active")
        else:
            res.append("my-navbar__item")

    return res


# def registered_pages():
#     return [dbc.NavItem(dbc.NavLink(page["name"], href=page["path"],
#                                     active="exact"))
#             for page in dash.page_registry.values()
#             ]
