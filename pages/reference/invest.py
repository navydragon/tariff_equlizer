from dash import html, dcc, Dash, dash_table, callback
from dash.dependencies import Input, Output, State
import pandas as pd
from dash.dash_table.Format import Format, Scheme
import dash_bootstrap_components as dbc
from pages.data import get_invest_data
import json

DIRECTIONS = ['Все','Сеть', 'Восток', 'Северо-Запад','Юг']
SUM_COL = 'Сумма расходов на проекты, млрд руб'

def get_data():
    df = get_invest_data()
    df['Index'] = df.index
    # df[SUM_COL] = df[SUM_COL].round(0)
    return df


def invest_layout():
    global df
    df = get_data()
    with open('data/fund_lack.json', 'r') as json_file:
        fund_lack = json.load(json_file).get("fund_lack")

    return html.Div([
        dbc.Row([
            dbc.Col([html.H3('Инвестиционные проекты')]),
            dbc.Col([
                html.Label('Дефицит средств (млн. руб.)'),
                dbc.Input(type='number', min=0,id='fund_lack', value=fund_lack)
            ]),
            dbc.Col([],id='output-json')
        ], className='mb-4'),
        html.Div([],id='output_div'),
        html.Div([draw_table(df)], id='invest_datatable_div', className='m-2 '),
    ], className='m-2')




def draw_table(df_part):
    columns_to_display = ['Направление', 'Наименование проектов', SUM_COL, 'Участие в расчете']
    table = dash_table.DataTable(
        id='datatable_invest',
        data=df_part.to_dict('records'),
        columns=[
            {'id': 'Index', 'name': 'Index'},
            {'id': 'Направление', 'name': 'Направление'},
            {'id': 'Наименование проектов', 'name': 'Наименование проектов'},
            {'id': SUM_COL, 'name': SUM_COL, 'type':'numeric'},
            {'id': 'Участие в расчете', 'name': 'Участие в расчете'},
        ],
        dropdown={
            'Участие в расчете': {
                'options': [{'label': 'Да', 'value': 'Да'}, {'label': 'Нет', 'value': 'Нет'}]
            }
        },
        sort_action='native',
        page_size=20,
        row_selectable='multi',
        selected_rows=df_part[df_part['Участие в расчете'] == 'Да'].index,
        style_cell_conditional=[
            {'if': {'column_id': 'Направление'}, 'textAlign': 'left'},
            {'if': {'column_id': 'Наименование проектов'}, 'textAlign': 'left'},
            {'if': {'column_id': 'Index'}, 'display': 'none'},
            {'if': {'column_id': 'Участие в расчете'}, 'display': 'none'},
        ],
        style_data_conditional=[
            {'if': {'column_editable': False}, 'backgroundColor': 'lightgray'},
        ],
        style_header={'fontWeight': 'bold'},
        style_cell={'maxWidth': '300px', 'whiteSpace': 'normal'},
        editable=True,

    )

    return table


@callback(
    Output('output_div', 'children'),
    Input('datatable_invest', 'selected_rows'),
    State('datatable_invest', 'data'),
    prevent_initial_call=True
)
def update_selected_rows(selected_rows,data):
    global df
    for index, elem in enumerate(data):
        if index in selected_rows:
            df.loc[elem['Index'], 'Участие в расчете'] = 'Да'
        else:
            df.loc[elem['Index'], 'Участие в расчете'] = 'Нет'

    df.to_excel('data/invest.xlsx', index=False)
    pass

@callback(
    Output('datatable_invest', 'data'),
    Input('datatable_invest', 'data'),
    State('datatable_invest', 'data_previous'),
    State('datatable_invest', 'start_cell'),
    State('datatable_invest', 'page_current'),
    State('datatable_invest', 'page_size'),
    prevent_initial_call=True
)
def save_row(data, data_previous,start_cell,page_current,page_size):
    global df
    if page_current is None : page_current = 0
    changed_index = int(start_cell['row']) + int(page_current) * int(page_size) - 1
    updated_row = data[changed_index]
    row_index = updated_row['Index']
    df = pd.DataFrame.from_records(data)
    df.to_excel('data/invest.xlsx', index=False)
    return data




@callback(
    Output('invest_datatable_div', 'children'),
    Input('direction_dropdown', 'value'),
)
def filter(direction):

    if direction is not None and direction != 'Все':
        df_part = df.query('`Направление` == @direction')
    else:
        df_part = df

    return draw_table(df_part)


def selectors():
    return dbc.Container(
    [
        html.Div(
        [
            html.Label('Вид сообщения'),
            dcc.Dropdown(
                id='direction_dropdown',
                options=[
                    {'label': str(direction), 'value': direction}
                    for direction in DIRECTIONS
                ],
                value='Все',
                placeholder='Фильтр по направлению',
            )
        ],className='col-md-3'),
    ],className='mx-2')

@callback(
    Output('output-json', 'children'),
    Input('fund_lack', 'value'),
    prevent_initial_call=True
)
def save_to_json(fund_lack_value):
    if fund_lack_value is not None:
        data = {'fund_lack': fund_lack_value}
        with open('data/fund_lack.json', 'w') as f:
            json.dump(data, f)
        return f'Значение сохранено: {fund_lack_value} млрд.'
    else:
        return 'Введите значение в поле'