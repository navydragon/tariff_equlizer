from dash import  Input, State, ALL
from pages.constants import Constants as CON
from pages.data import calculate_total_index

input_states = [
    Input('calculate-button', 'n_clicks'),
    State('epl_change', 'value'),
    State('market_loss', 'value'),
    State('cif_fob', 'value'),
    State('index_sell_prices', 'value'),
    State('price_variant', 'value'),
    State('index_sell_coal', 'value'),
    State('index_oper', 'value'),
    State('index_per', 'value'),
    [State(str(year) + '_year_total_index', 'children') for year in CON.YEARS],
]

def check_and_prepare_params(
    epl_change,
    market_loss,
    cif_fob,
    index_sell_prices,
    price_variant,
    index_sell_coal,
    index_oper,
    index_per,
    revenue_index_values
):
    if all(value == 0 for value in revenue_index_values):
        revenue_index_values = calculate_total_index()

    return {
        "label": 'Признак',
        "revenue_index_values": revenue_index_values,
        "epl_change": epl_change,
        "market_loss": market_loss,
        "ipem": {
            "index_sell_prices": index_sell_prices,
            "price_variant": price_variant,
            "index_sell_coal": index_sell_coal,
            "index_oper": index_oper,
            "index_per": index_per,
            "cif_fob": cif_fob,
        }
    }