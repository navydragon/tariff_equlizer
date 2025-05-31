from dash import html, dcc, callback, Output, Input, State, clientside_callback
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import pandas as pd
import pages.calculations as calc
from pages.constants import Constants as CON

def layout():
    return html.Div([
        dbc.Button(
            "+", id="fade-button_turnover", className="mb-3", n_clicks=0
        ),
        dbc.Fade(
            dbc.Card(
                dbc.CardBody(
                    filters()
                )
            ),
            id="fade_turnover",
            is_in=False,
            appear=False,
        ),
    ])

def filters():
    return (
        html.Div([
            html.H2('Грузооборот', className='my-section__title'),
            dbc.Row([
                dbc.Col([
                    html.Label('млрд ткм'),
                    dcc.Dropdown(
                        id='group_parameter_turnover',
                        options=['Группа груза','Код груза','Направления','Род вагона','Вид перевозки','Категория отправки','Тип парка','Холдинг'],
                        searchable=True,
                        clearable=False,
                        value=''
                    ),
                ], width=3),
                dbc.Col([
                    html.Label('Группировка внутри'),
                    dcc.Dropdown(
                        id='group_parameter2_turnover',
                        options=['Группа груза', 'Код груза', 'Направления',
                                 'Род вагона', 'Вид перевозки',
                                 'Категория отправки', 'Тип парка', 'Холдинг'],
                        searchable=True,
                        value=None
                    ),
                ], width=3),
                dbc.Col(
                    html.Button(className='my-section__badge', id='btn-excel-export-turnover-ar', style={'margin-left': 'auto', 'margin-right':'10px'}, children='Экспорт'),
                width=2)
            ], className='mb-3'),
            dcc.Loading(
                id="loading",
                type="default",
                color="#e21a1a",
                fullscreen=False,
                children=[html.Div([], id='absolute_turnover_table_div')]
            ),
        ])
    )

def draw_grid(res_df):
    sum_row = {col: round(res_df[col].sum(),2) if pd.api.types.is_numeric_dtype(res_df[col]) else 'ИТОГО' for col in res_df.columns}

    grid = dag.AgGrid(
        id="main_grid",
        rowData=res_df.to_dict("records"),
        columnDefs=[{"headerName": col, "field": col} for col in res_df.columns],
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={
            'pinnedTopRowData': [sum_row],
        },
        enableEnterpriseModules=True,
    )
    return grid

def group_and_combine(df, loss_df, group1,group2, market_loss):
    df_gr = calc.group_data(df, group1, group2 if group2 is not None else 'Нет')

    if group2 is not None:
        loss_df_gr = loss_df.groupby([group1, group2]).sum(numeric_only=True)
    else:
        loss_df_gr = loss_df.groupby(group1).sum(numeric_only=True)

    res = []
    years = [2024] + CON.YEARS
    for index, row in df_gr.iterrows():
        res_row = {}
        res_row[group1] = row[group1]
        if group2 is not None: res_row[group2] = row[group2]

        group1_value = row[group1]

        if group2 is not None:
            group2_value = row[group2]
            # Для двух групп
            if group2_value == 'ИТОГО':
                loss_row = loss_df_gr.loc[(group1_value)].sum(numeric_only=True)
            else:
                loss_row = loss_df_gr.loc[(group1_value, group2_value)]
        else:
            # Для одной группы
            loss_row = loss_df_gr.loc[group1_value]

        total_sum = 0

        for year_index, year in enumerate([2024] + years):
            if market_loss:
                year_value = loss_row[f'turnover_after_loss_{year}'] / 1000000
            else:
                year_value = row[f'{year} ЦЭКР груззоборот, тыс ткм'] / 1000000

            res_row[str(year)] = round(year_value, 2)
            total_sum += year_value

        res_row[str(years[0])+'-'+str(years[-1])] = round(total_sum, 2)

        res.append(res_row)

    res_df = pd.DataFrame(res)
    res_df = res_df.drop_duplicates()
    return res_df
def get_callbacks():
    @callback(
        Output("fade_turnover", "is_in"),
        Output("fade-button_turnover", "children"),
        [Input("fade-button_turnover", "n_clicks")],
        [State("fade_turnover", "is_in")],
    )
    def toggle_fade(n, is_in):

        if not n:
            return (False, "+")
        return (not is_in, "+" if is_in == True else "-")

    @callback(
        Output("absolute_turnover_table_div", "children"),
        # Input('calculate-button', 'n_clicks'),
        Input("group_parameter_turnover", "value"),
        Input("group_parameter2_turnover", "value"),
        prevent_initial_call=True
    )
    def update_table(group_parameter, group_parameter2):
        from pages.dashboard_page import loss_df,df, PARAMS

        res_df = group_and_combine(df, loss_df, group_parameter, group_parameter2,PARAMS["market_loss"])

        if group_parameter2 is not None: res_df = res_df[res_df[group_parameter2] != 'ИТОГО']
        return draw_grid(res_df)

    clientside_callback(
        """function (n) {
            if (n) {
                dash_ag_grid.getApi("main_grid").exportDataAsExcel();
            }
            return dash_clientside.no_update
        }""",
        Output("btn-excel-export-turnover-ar", "n_clicks"),
        Input("btn-excel-export-turnover-ar", "n_clicks"),
        prevent_initial_call=True
    )
