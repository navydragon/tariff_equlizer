import dash
from dash import Input, Output, callback, html

from pages.data import get_main_data, get_small_data
import dash_pivottable
import pandas, os

dash.register_page(__name__, name="Сводные", path='/pivot', order=7, my_class='my-navbar__icon-2')

def layout ():
    df = get_small_data()
    select_columns = ["Группа груза", "Направления", "Дор отпр", "Дор наз", "Вид перевозки"]
    columns_for_del = list(set(list(df.select_dtypes(exclude=['floating']))) - set(select_columns))
    df = df.drop(columns=columns_for_del)
    df = df.groupby(list(df.select_dtypes(exclude=['floating']))).sum()
    df = df.reset_index()
    head_data_values = list(df.select_dtypes(include=['floating']))
    head_data_filters = list(df.select_dtypes(exclude=['floating']))
    data_data = [df.columns.values.tolist()] + df.values.tolist()
    print(data_data)
    res = html.Div([
        dash_pivottable.PivotTable(
            id='table',
            data = data_data,
            rows=['Группа груза'],
            cols=['Направления'],
            colOrder="key_a_to_z",
            rowOrder="key_a_to_z",
            rendererName="Table",
            aggregatorName="Count",
        ),
        html.Div(
            id='output'
        )
    ])
    return res


@callback(
    Output('output', 'children'),
    [Input('table', 'cols'),
    Input('table', 'rows'),
    Input('table', 'rowOrder'),
    Input('table', 'colOrder'),
    Input('table', 'aggregatorName'),
    Input('table', 'rendererName')],
    prevent_initial_call=True
)
def display_props(cols, rows, row_order, col_order, aggregator, renderer):
    return [
        html.P(str(cols), id='columns'),
        html.P(str(rows), id='rows'),
        html.P(str(row_order), id='row_order'),
        html.P(str(col_order), id='col_order'),
        html.P(str(aggregator), id='aggregator'),
        html.P(str(renderer), id='renderer'),
    ]