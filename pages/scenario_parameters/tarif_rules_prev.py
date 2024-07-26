import json
import random
import sqlite3
import string

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, callback, Input, Output, State, ALL, MATCH

from pages.constants import Constants as CON
from pages.data import get_small_data


def generate_random_string(length):
    """Генерирует случайную строку заданной длины"""
    letters_and_digits = string.ascii_letters + string.digits
    return ''.join(random.choices(letters_and_digits, k=length))

PARAMETERS = [
    'Группа груза',
    'Код груза',
    'Код груза(изпод)',
    'Дор отпр',
    'Дор наз',
    'Род вагона',
    'Вид перевозки',
    'Категория отпр.',
    'Тип парка',
    'Вид спец. контейнера',
    'Холдинг',
    'Направления'
]

years = CON.YEARS



new_rule_states = [
    State('rule_name_prev', 'value'),
    State({'type': 'parameter_dropdown_prev', 'index': ALL}, 'value'),
    State({'type': 'include_dropdown_prev', 'index': ALL}, 'value'),
    State({'type': 'values_dropdown_prev', 'index': ALL}, 'value'),
    State('rule_indexation_variant_prev', 'value'),
    State({'type': 'rule_indexation_input_prev', 'index': ALL}, 'value'),
    State('base_percent_prev','value')
]

def rules_layout():
    modal = html.Div(
            [
                html.Div([
                    html.Button("",id="create_modal_button_prev",n_clicks=0, className='my-button my-button_margin_left my-button__type_create'),
                    html.Span('Добавить новое тарифное рещение', className='my-button_margin_left'),
                ], className='my-button__menu'),
                html.Hr(),
                html.Div([
                    dbc.Modal([
                        dbc.ModalHeader(
                            dbc.ModalTitle("Ранее принятое решение")),
                        dbc.ModalBody([create_modal_body()], id='rule_modal_body_prev', className='m-2'),
                        dbc.ModalFooter([modal_footer('create')],id='rule_modal_footer_prev'),
                    ],id='rule_modal_prev', is_open=False, size='xl')
                ], id='modal_div_prev'),
                html.Div([], id='edit_modal_div_prev'),
                dbc.Table([
                    html.Thead([
                        html.Tr([
                            html.Th('Правило'),
                            # html.Th('Условия'),
                            # html.Th('Индексы')
                        ])
                    ]),
                    html.Tbody(print_rules(),id='rules_prev'),
                ], className='table table-sm')
            ]
        )
    return html.Div([
        modal,
    ], className='m-2')


def add_condition_row(param_name,num):
    tariff_data = get_small_data()
    index = PARAMETERS.index(param_name)
    value_options = tariff_data[PARAMETERS[index]].unique()
    result = dbc.Row([
        dbc.Col([
            html.Label('Параметр'),
            dcc.Dropdown(
                id={'type': 'parameter_dropdown_prev', 'index': num},
                options=PARAMETERS,
                clearable=False,
                value=PARAMETERS[0]
            ),
        ],width=4),
        dbc.Col([
            html.Label(''),
            dcc.Dropdown(
                id={'type': 'include_dropdown_prev', 'index': num},
                options=['включает', 'не включает'],
                clearable=False,
                value='включает',
            ),
        ],width=2),
        dbc.Col([
            html.Label('Значения'),
            dcc.Dropdown(
                id={'type': 'values_dropdown_prev', 'index': num},
                options=value_options,
                clearable=False,
                multi=True
            ),
        ], width=5),
        dbc.Col([
            dbc.Button( id={'type': 'delete_button_prev', 'index': num},  n_clicks=0, className='my-button my-button__type_delete my-button_margin_left'),
        ], width=1)
        # if num != '0' else None
    ], id={'type': 'rule_row', 'index': num}, style={'display': 'flex', 'align-items': 'flex-end', 'margin-bottom': '10px'})
    return result

def print_condition_rows(conditions):
    result = []
    tariff_data = get_small_data()
    for i, condition in enumerate(conditions):
        index = PARAMETERS.index(condition['parameter'])
        value_options = tariff_data[PARAMETERS[index]].unique()
        parameter = condition["parameter"]
        include = condition["include"]
        values = condition["values"].split(';') if condition["values"] else []
        num = i + 1
        result.append(
            dbc.Row([
                dbc.Col([
                    html.Label('Параметр'),
                    dcc.Dropdown(
                        id={'type': 'parameter_dropdown_prev', 'index': num},
                        options=PARAMETERS,
                        clearable=False,
                        value=PARAMETERS[index]
                    ),
                ], width=4),
                dbc.Col([
                    html.Label(''),
                    dcc.Dropdown(
                        id={'type': 'include_dropdown_prev', 'index': num},
                        options=['включает', 'не включает'],
                        clearable=False,
                        value=include,
                    ),
                ], width=2),
                dbc.Col([
                    html.Label('Значения'),
                    dcc.Dropdown(
                        id={'type': 'values_dropdown_prev', 'index': num},
                        options=value_options,
                        clearable=False,
                        multi=True,
                        value=values
                    ),
                ], width=5),
                dbc.Col([
                    dbc.Button('Удалить',
                               id={'type': 'delete_button_prev', 'index': num},
                               n_clicks=0, size='sm', color='danger'),
                ], width=1)
                # if num != '0' else None
            ], id={'type': 'rule_row', 'index': num},
                style={'display': 'flex', 'align-items': 'flex-end',
                       'margin-bottom': '10px'})

        )
    return result

@callback(
    Output('rule_conditions_prev', 'children'),
    Input('add_condition_button_prev', 'n_clicks'),
    Input({'type': 'delete_button_prev', 'index': ALL}, 'n_clicks'),
    State('rule_conditions_prev', 'children'),
    prevent_initial_call=True
)
def update_conditions(add_clicks, delete_clicks, conditions):
    ctx = dash.callback_context
    if ctx.triggered:
        if 'add_condition_button_prev' in ctx.triggered[0]['prop_id']:
            new_row = add_condition_row('Группа груза', str(add_clicks))
            conditions.append(new_row)
        else:
            button_id = ctx.triggered[0]['prop_id'].split('.')[0]
            button_id = json.loads(button_id)
            button_index = button_id['index']
            conditions = [condition for condition in conditions if condition['props']['id']['index'] != button_index]

    return conditions

@callback(
    Output({'type': 'values_dropdown_prev', 'index': MATCH}, 'options'),
    Output({'type': 'values_dropdown_prev', 'index': MATCH}, 'value'),
    Input({'type': 'parameter_dropdown_prev', 'index': MATCH}, 'value'),
    State({'type': 'values_dropdown_prev', 'index': MATCH}, 'value'),
)
def update_values_dropdown_options(selected_param, curr_value):
    tariff_data = get_small_data()
    if curr_value == None:
        curr_value = ['Все']
    value_options = ['Все'] + list(tariff_data[selected_param].unique())
    return value_options, curr_value




@callback(
    Output('rule_stat_prev','children'),
    Output('base_percent_input_prev','value'),
    Input({'type': 'values_dropdown_prev', 'index': ALL}, 'value'),
    Input({'type': 'include_dropdown_prev', 'index': ALL}, 'value'),
    State({'type': 'parameter_dropdown_prev', 'index': ALL}, 'value'),
    Input('base_percent_prev','value'),
)
def calculate_stat(values_list, includes_list, parameters_list,base_percent):
    filtered_data = get_small_data()
    total_epl = filtered_data[CON.EPL].sum()
    total_revenue = filtered_data[CON.PR_P].sum()
    for index, (values, parameter, include) in enumerate(zip(values_list, parameters_list, includes_list)):
        if values == ['Все']:
            values = filtered_data[parameter].unique()
        if include == 'включает':
            filtered_data = filtered_data[
                filtered_data[parameter].isin(values)]
        else:
            filtered_data = filtered_data[~filtered_data[parameter].isin(values)]
    epl_percent = round((filtered_data[CON.EPL].sum() / total_epl * 100)*int(base_percent)/100,2)
    revenue_percent = round((filtered_data[CON.PR_P].sum() / total_revenue * 100)*int(base_percent)/100,2)
    return html.P(f'Правило затронет {len(filtered_data)} строк, {epl_percent}% грузооборота, {revenue_percent}% доходов'), base_percent


@callback(
    Output("base_percent_col_prev", "children"),
    Input("base_percent_input_prev", "value"),
    allow_duplicate=True
)
def base_percent_input(value):
    return dcc.Slider(
        id='base_percent_prev',
        max=200,
        min=0,
        step=0.01,
        marks=None,
        value=value
    )

@callback(
    Output('indexation_label_prev', 'children'),
    Input('rule_indexation_variant_prev','value'),
    prevent_initial_call=True
)
def change_indexation_label(variant):
    if variant == 'млрд':
        return 'Значение'
    return 'Индексация'


@callback(
    Output('rules_prev','children'),
    Input('process_rule_button_prev','n_clicks'),
    Input({'type': 'delete_rule_prev', 'index': ALL}, 'n_clicks'),
    *new_rule_states,
    prevent_initial_call=True
)
def update_rules(clicks, delete_clicks, *rule_states):
    ctx = dash.callback_context
    # if update_clicks == [None]: update_clicks=[0]

    if ctx.triggered:
        if 'process_rule_button_prev' in ctx.triggered[0]['prop_id'] and clicks>0:
            if RULE_ID_MEM != None:
                delete_rule_from_db(RULE_ID_MEM)
            store_rule_to_db(rule_states)
        elif 'delete_rule_prev' in ctx.triggered[0]['prop_id']:
            button_id = ctx.triggered[0]['prop_id'].split('.')[0]
            button_id = json.loads(button_id)
            button_index = button_id['index']
            delete_rule_from_db(button_index)

    return print_rules()

RULE_ID_MEM = None
@callback(
    Output('rule_modal_body_prev','children'),
    Output('rule_modal_footer_prev','children'),
    Output('rule_modal_prev','is_open'),
    Output({'type': 'edit_modal_button_prev', 'index': ALL},'n_clicks'),
    Input('create_modal_button_prev','n_clicks'),
    Input({'type': 'edit_modal_button_prev', 'index': ALL},'n_clicks'),
    prevent_initial_call=True,
)


def draw_modal(create,edit):
    global RULE_ID_MEM
    ctx = dash.callback_context
    if ctx.triggered:
        if 'create_modal_button_prev' in ctx.triggered[0]['prop_id']:
            body = create_modal_body()
            footer =  modal_footer('create')
            show_modal = True
            RULE_ID_MEM = None
        elif 'edit_modal_button_prev'in ctx.triggered[0]['prop_id'] and 1 in edit:
            button_id = ctx.triggered[0]['prop_id'].split('.')[0]
            button_id = json.loads(button_id)
            rule_id = button_id['index']
            rule = load_rules(rule_id)[0]
            body = edit_modal_body(rule)
            footer = modal_footer('update',rule_id)
            show_modal = True
            RULE_ID_MEM = rule_id
        else:
            body = create_modal_body()
            footer = modal_footer('create')
            show_modal = False
    return body, footer, show_modal, [0]*len(edit)


def create_modal_body():
    return [
                html.Label('Название'),
                dbc.Input(id='rule_name_prev', style={'z-index':9999}),
                html.P('Введите условия',className='mt-2'),
                dbc.Button('Добавить условие',size='sm',id='add_condition_button_prev'),
                html.Div([
                    add_condition_row('Группа груза','0')
                ],id='rule_conditions_prev'),
                html.Div([
                    dbc.Label('% покрытия базы'),
                    html.Div(base_percent_row(100))
                ]),
                html.Div([],id='rule_stat_prev', className='mt-2'),

                dbc.Row([
                    dbc.Col(width=4),
                    dbc.Col('2024', width=1)
                ], className="border-bottom mb-2 text-center"),
                dbc.Row([
                    dbc.Col('Индексация:', width=2,id='indexation_label_prev'),
                    dbc.Col(dcc.Dropdown(
                        id='rule_indexation_variant_prev',
                        options=['*','млрд'],
                        clearable=False,
                        value='млрд'
                    ),width=2),
                    dbc.Col([
                        dbc.Input(id={'type': 'rule_indexation_input_prev', 'index': str(2024)},
                            value=1,
                            type='number', step=0.01, className="form-control form-control-sm")
                    ],  width=1, className='d-flex align-items-center')
                ], className="border-bottom mb-2"),
                # print_alert()
            ]


def edit_modal_body(rule):
    return [
        html.Label('Название решения'),
        dbc.Input(id='rule_name_prev', value=rule['name']),
        html.P('Введите условия', className='mt-2'),
        dbc.Button('Добавить условие', size='sm',
                   id='add_condition_button_prev', n_clicks=len(rule["conditions"])),
        html.Div(print_condition_rows(rule['conditions']), id='rule_conditions_prev'),
        html.Div([
            dbc.Label('% покрытия базы'),
            html.Div(base_percent_row(rule["base_percent"]))
        ]),
        html.Div([], id='rule_stat_prev', className='mt-2'),
        dbc.Row([
            dbc.Col(width=4),
            dbc.Col('2024', width=1)
        ], className="border-bottom mb-2 text-center"),
        dbc.Row([
            dbc.Col('Индексация', width=1,id='indexation_label_prev'),
            dbc.Col(dcc.Dropdown(
                id='rule_indexation_variant_prev',
                options=['*','млрд'],
                clearable=False,
                value=rule["variant"],
            ), width=3),
            dbc.Col([
                dbc.Input(id={'type': 'rule_indexation_input_prev',
                              'index': str(2024)},
                          value=rule['index_'+str(2024)],
                          type='number', step=0.01,
                          className="form-control form-control-sm")
            ], width=1, className='d-flex align-items-center')
        ], className="border-bottom mb-2"),
        # print_alert()
    ]

def modal_footer(type,rule_id='new'):
    if type=='create':
        name='Добавить'
    else:
        name='Обновить'
    return [
        dbc.Button(name, color='success',
                   id='process_rule_button_prev',
                   className="ml-auto", n_clicks=0)
    ]

def print_alert():
    return dbc.Alert([
          html.P("Пояснение:"),
          html.Ul([
              html.Li([html.Strong(' * '), html.Span(' - Домножить коэффициент на указанное число')]),
              html.Li([html.Strong(' = '), html.Span(' - Установить коэффициент равным указанному числу')]),
              html.Li([html.Strong(' млрд '), html.Span(' - распределить указанную сумму')])
          ])
        ],
        className="alert-info p-2")

def print_rules():
    result = []
    rules = load_rules()
    for rule_obj in rules:
        result.append(html.Tr([
            html.Td([
                dbc.Checkbox(id={'type': 'rule_active_prev', 'index': rule_obj['id']}, value=rule_obj['active'], className=''),
                rule_obj['name']
            ], style={'display': 'flex', 'align-items': 'center'}),
            # html.Td([
            #     html.Div(
            #         condition["parameter"] + ' ' + condition[
            #             "include"] + ' ' + condition["values"]
            #     ) for condition in rule_obj["conditions"]
            # ]),
            # html.Td([
            #     html.Strong(f'{rule_obj["variant"]}* ', className=''),
            #     html.Span(', '.join(str(rule_obj[f"index_{year}"]) for year in CON.YEARS))
            #
            # ]),
            html.Td([
                html.Div([
                    html.Button(
                               id={'type': 'edit_modal_button_prev', 'index': rule_obj['id']},
                               n_clicks=0, className='my-button my-button__type_edit my-button_margin_left'),
                    html.Button( id={'type': 'delete_rule_prev', 'index': rule_obj['id']},
                        n_clicks=0,className='my-button my-button__type_delete my-button_margin_left'),

                ], className='my-button__menu')
            ])
        ],id=rule_obj["id"]))

    return result


def load_rules(id=None, active_only=False):
    with sqlite3.connect('data/database.db') as conn:
        cursor = conn.cursor()
        if id is None:
            if active_only:
                rules_sql = cursor.execute('SELECT * FROM rules_prev WHERE active = ?', (active_only,))
            else:
                rules_sql = cursor.execute('SELECT * FROM rules_prev')
        else:
            rules_sql = cursor.execute('SELECT * FROM rules_prev WHERE id = ?', (id,))
        rules = []
        for rule in rules_sql.fetchall():
            rule_obj = {
                "id": rule[0],
                "name": rule[1],
                "variant": rule[2],
                "index_2026": rule[3],
                "index_2027": rule[4],
                "index_2028": rule[5],
                "index_2029": rule[6],
                "index_2030": rule[7],
                "active": rule[8],
                "base_percent": rule[9],
                "index_2025": rule[10],
                "index_2024": rule[11],
                "conditions": []
            }
            conditions = cursor.execute(
                '''SELECT * FROM conditions_prev WHERE rule_id = ?''',
                (rule[0],))
            for condition in conditions.fetchall():
                condition_obj = {
                    "parameter": condition[1],
                    "include": condition[2],
                    "values": condition[3]
                }
                rule_obj["conditions"].append(condition_obj)
            rules.append(rule_obj)

    return rules

@callback(
    Output({'type': 'rule_active_prev', 'index': MATCH}, 'value'),
    Input({'type': 'rule_active_prev', 'index': MATCH}, 'value'),
    prevent_initial_call=True
)
def update_rule_active(selected_param):
    ctx = dash.callback_context
    if ctx.triggered:
        checkbox_id = ctx.triggered[0]['prop_id'].split('.')[0]
        checkbox_id = json.loads(checkbox_id)
        rule_id = checkbox_id['index']
        with sqlite3.connect('data/database.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''UPDATE rules_prev SET active = ? WHERE id = ?''', (selected_param, rule_id))
    return selected_param


def delete_rule_from_db(rule_id):
    with sqlite3.connect('data/database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''DELETE FROM conditions_prev WHERE rule_id = ?''', (rule_id,))
        cursor.execute('''DELETE FROM rules_prev WHERE id = ?''', (rule_id,))

def store_rule_to_db(rule_states):
    rule_id = generate_random_string(4)
    name = rule_states[0]
    parameters = rule_states[1]
    include = rule_states[2]
    values = rule_states[3]
    variant = rule_states[4]
    indexes = rule_states[5]
    base_percent = rule_states[6]
    with sqlite3.connect('data/database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
                            INSERT INTO rules_prev (id, name, variant,index_2024, index_2025, index_2026, index_2027, index_2028, index_2029, index_2030, base_percent)
                            VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0, ?)
                        ''', (
        rule_id, name, variant, indexes[0], base_percent))
        for index in range(len(parameters)):
            cursor.execute('''
                            INSERT INTO conditions_prev (rule_id, parameter, include, values_list)
                            VALUES (?, ?, ?, ?)
                        ''', (rule_id, parameters[index], include[index],
                              ';'.join(map(str, values[index]))))


def base_percent_row(percent):
    return dbc.Row([
                dbc.Col([
                    dcc.Slider(
                        id='base_percent_prev',
                        max=200,
                        min=0,
                        step=0.01,
                        marks=None,
                        value=percent
                    )
                ], id='base_percent_col_prev', className='col-md-10'),
                dbc.Col([
                    dbc.Input(
                        id='base_percent_input_prev',
                        type='number',
                        step=0.01,
                        value=percent,
                        size='md'
                    )
                ], className='col-md-2'),
            ]),
