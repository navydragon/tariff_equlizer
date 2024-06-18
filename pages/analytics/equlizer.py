from dash import callback, MATCH, Input, Output, State, dcc
from dash import callback_context


def draw_slider (type,year,value, max=None, step=1,is_vertical=True, placement="right", classname='my-slider'):
    value = float(value)
    if max is None:
        max = value * 2
    res = dcc.Slider(
        min=0, max=max, marks=None, step=step, value=value, vertical=is_vertical, verticalHeight=200, className=classname,
        id={'type': type, 'index': year},
        tooltip={
            "placement": "right" if is_vertical==True else "bottom",
            "always_visible": True,
        }
    )
    return res



def draw_input (type, year,value):
    res = dcc.Input(
        type='number',value=value,
        className='form-control my-coefficient__number form-control text-center',
        id={'type': f'{type}_input', 'index': year}
    )
    return res


@callback(
    Output({'type': 'cost_input', 'index': MATCH}, 'value'),
    Input({'type': 'cost', 'index': MATCH}, 'value'),
    prevent_initial_call=True
)
def update_cost_input(value):
   return value

@callback(
    Output({'type': 'cost_container', 'index': MATCH}, 'children'),
    Input({'type': 'cost_input', 'index': MATCH}, 'value'),
    State({'type': 'cost', 'index': MATCH}, 'max'),
    prevent_initial_call=True,
)
def update_cost_slider(value,max):
   triggered_id = callback_context.triggered_id
   index = triggered_id['index']
   res = draw_slider (type='cost',year=index,max=max,value=value)
   return res


@callback(
    Output({'type': 'base_input', 'index': MATCH}, 'value'),
    Input({'type': 'base', 'index': MATCH}, 'value'),
    prevent_initial_call=True
)
def update_base_input(value):
   return value

@callback(
    Output({'type': 'base_container', 'index': MATCH}, 'children'),
    Input({'type': 'base_input', 'index': MATCH}, 'value'),
    State({'type': 'base', 'index': MATCH}, 'max'),
    State({'type': 'base', 'index': MATCH}, 'step'),
    prevent_initial_call=True,
)
def update_base_slider(value,max, step):
   triggered_id = callback_context.triggered_id
   index = triggered_id['index']
   res = draw_slider (type='base',year=index,max=max,value=value, step=step)
   return res


@callback(
    Output({'type': 'rules_input', 'index': MATCH}, 'value'),
    Input({'type': 'rules', 'index': MATCH}, 'value'),
    prevent_initial_call=True
)
def update_rules_input(value):
   return value

@callback(
    Output({'type': 'rules_container', 'index': MATCH}, 'children'),
    Input({'type': 'rules_input', 'index': MATCH}, 'value'),
    State({'type': 'rules', 'index': MATCH}, 'max'),
    State({'type': 'base', 'index': MATCH}, 'step'),
    prevent_initial_call=True,
)
def update_rules_slider(value,max, step):
   triggered_id = callback_context.triggered_id
   index = triggered_id['index']
   res = draw_slider (type='rules',year=index,max=max,value=value, step=step)
   return res


@callback(
    Output({'type': 'per_input', 'index': MATCH}, 'value'),
    Input({'type': 'per', 'index': MATCH}, 'value'),
    prevent_initial_call=True
)
def update_per_input(value):
   return value

@callback(
    Output({'type': 'per_container', 'index': MATCH}, 'children'),
    Input({'type': 'per_input', 'index': MATCH}, 'value'),
    State({'type': 'per', 'index': MATCH}, 'max'),
    prevent_initial_call=True,
)
def update_per_slider(value,max):
   triggered_id = callback_context.triggered_id
   index = triggered_id['index']
   res = draw_slider (type='per',year=index,max=max,value=value)
   return res


@callback(
    Output({'type': 'oper_input', 'index': MATCH}, 'value'),
    Input({'type': 'oper', 'index': MATCH}, 'value'),
    prevent_initial_call=True
)
def update_oper_input(value):
   return value

@callback(
    Output({'type': 'oper_container', 'index': MATCH}, 'children'),
    Input({'type': 'oper_input', 'index': MATCH}, 'value'),
    State({'type': 'oper', 'index': MATCH}, 'max'),
    prevent_initial_call=True,
)
def update_oper_slider(value,max):
   triggered_id = callback_context.triggered_id
   index = triggered_id['index']
   res = draw_slider (type='oper',year=index,max=max,value=value)
   return res


@callback(
    Output({'type': 'price_input', 'index': MATCH}, 'value'),
    Input({'type': 'price', 'index': MATCH}, 'value'),
    prevent_initial_call=True
)
def update_price_input(value):
   return value

@callback(
    Output({'type': 'price_container', 'index': MATCH}, 'children'),
    Input({'type': 'price_input', 'index': MATCH}, 'value'),
    State({'type': 'price', 'index': MATCH}, 'max'),
    prevent_initial_call=True,
)
def update_price_slider(value,max):
   triggered_id = callback_context.triggered_id
   index = triggered_id['index']
   res = draw_slider (type='price',year=index,max=max,value=value)
   return res


@callback(
    Output({'type': 'price_rub_input', 'index': MATCH}, 'value'),
    Input({'type': 'price_rub', 'index': MATCH}, 'value'),
    prevent_initial_call=True
)
def update_price_rub_input(value):
   return value

@callback(
    Output({'type': 'price_rub_container', 'index': MATCH}, 'children'),
    Input({'type': 'price_rub_input', 'index': MATCH}, 'value'),
    State({'type': 'price_rub', 'index': MATCH}, 'max'),
    prevent_initial_call=True,
)
def update_price_rub_slider(value,max):
   triggered_id = callback_context.triggered_id
   index = triggered_id['index']
   res = draw_slider (type='price_rub',year=index,max=max,value=value)
   return res



@callback(
    Output({'type': 'dollar_price_input', 'index': MATCH}, 'value'),
    Input({'type': 'dollar_price', 'index': MATCH}, 'value'),
    prevent_initial_call=True
)
def update_dollar_price_input(value):
   return value

@callback(
    Output({'type': 'dollar_price_container', 'index': MATCH}, 'children'),
    Input({'type': 'dollar_price_input', 'index': MATCH}, 'value'),
    State({'type': 'dollar_price', 'index': MATCH}, 'max'),
    State({'type': 'dollar_price', 'index': MATCH}, 'vertical'),
    State({'type': 'dollar_price', 'index': MATCH}, 'className'),
    prevent_initial_call=True,
)
def update_dollar_price_slider(value, max, vertical, classname):
   index = callback_context.triggered_id['index']
   return draw_slider(type='dollar_price', value=value, year=index, max=max, step=0.1, is_vertical=vertical, classname=classname)


@callback(
    Output({'type': 'fraht_input', 'index': MATCH}, 'value'),
    Input({'type': 'fraht', 'index': MATCH}, 'value'),
    prevent_initial_call=True
)
def update_fraht_input(value):
   return value

@callback(
    Output({'type': 'fraht_container', 'index': MATCH}, 'children'),
    Input({'type': 'fraht_input', 'index': MATCH}, 'value'),
    State({'type': 'fraht', 'index': MATCH}, 'max'),
    prevent_initial_call=True,
)
def update_fraht_slider(value, max):
   index = callback_context.triggered_id['index']
   return draw_slider(type='fraht', value=value, year=index, max=max, step=1)