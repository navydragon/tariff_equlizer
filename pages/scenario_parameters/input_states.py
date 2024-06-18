from dash import  Input, State, ALL
from pages.constants import Constants as CON

input_states = [
    Input('calculate-button','n_clicks'),
    [State(str(year) + '_year_total_index', 'children') for year in CON.YEARS],
]