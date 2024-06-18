from dash import html, dash_table, dcc, callback, ALL
import pandas as pd
from dash.dependencies import Input, Output, State

def costs_layout():
    excel_file = 'data/costs.xlsx'
    df = pd.read_excel(excel_file).round(3)
    res = html.Div([
        html.H3('Параметры'),
        make_datatable_from_df(df),
    ], className="p-2")
    return res


def make_datatable_from_df(df):
    return dash_table.DataTable(
            id='datatable',
            data=df.to_dict('records'),
            columns=[{"name": str(i), "id": str(i)} for i in df.columns],
            style_table={'height': '350px', 'overflowY': 'auto', 'width': '99%'},
            page_size=50,
            editable=True,
            style_cell_conditional=[
                {'if': {'column_id': c}, 'textAlign': 'left'} for c in ['Вид груза']
            ],
        )


@callback(
    Output('datatable', 'data'),
    Input('datatable', 'data_previous'),
    State('datatable', 'data'),
)
def update_dataframe(data_previous, data):
    # Когда таблица была отредактирована, data_previous будет содержать предыдущие значения
    if data_previous is not None and data_previous != data:
        # Обновляем DataFrame значениями из data
        updated_df = pd.DataFrame(data)
        column_order = ['Показатель', '2019', '2020','2021','2022','2023','2024','2025','2026','2027','2028','2029','2030']
        updated_df = updated_df[column_order]
        updated_df.to_excel('data/references/costs.xlsx', index=False)
        melted_df = updated_df.melt(id_vars='Показатель', var_name='Год', value_name='Значение')
        melted_df.to_excel('data/references/indexes.xlsx', index=False)
        # Здесь вы можете выполнить дополнительные действия с обновленным DataFrame
        # Например, сохранить его в файл или выполнить другие вычисления
        return updated_df.to_dict('records')

    # Если данные не были изменены, просто возвращаем текущие данные DataFrame
    return data