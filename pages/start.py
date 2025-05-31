import dash
from dash import html

dash.register_page(__name__, name="", path='/', order=0, my_class='my-navbar__icon-1')


def layout():
    return html.Div(className='center', children=[
        html.Div(className='bg-white w-50 h-25 rounded', children=[
            html.H2('Тарифный эквалайзер', className='text-center mt-2'),
            html.P('Версия от 30.05.2025', className='text-center')
        ])
    ])
