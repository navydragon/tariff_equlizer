import dash
from dash import html
from pages.navbar import navbar
from dash_auth import BasicAuth


import webbrowser


external_stylesheets = [

]
meta_tag = html.Meta(name='google', content='notranslate')

USER_PWD = {"admin": "password123"}
app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=external_stylesheets, meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],   use_pages=True)
app.head = [meta_tag]

# auth = BasicAuth(app, USER_PWD, public_routes=["/"])


app.layout = html.Div([
    html.Main(
        children=[
            html.Div(
                className='my-container',
                **{'data-layout': 'container'},
                children=[
                    navbar(),
                    html.Div([
                        dash.page_container,
                    ], className='content my-content'),
                    html.Footer([
                        html.Span([
                            '© ОАО «РЖД» все права защищены, 2025'
                        ], className="my-footer__copy")
                    ], className="my-footer")
                ]
            )
        ],
        id='top',
        className='main'
    ),

])





debug = False


if not debug:
    webbrowser.open_new("http://127.0.0.1:8050/")

if __name__ == '__main__':
    app.run_server(debug=debug)