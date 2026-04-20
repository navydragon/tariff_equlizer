import pandas as pd
import json
import dash_bootstrap_components as dbc
from dash import html, dcc, callback, Output, Input, State, ALL

def percentage_change(old_value, new_value):
    try:
        percentage_change = ((new_value - old_value) / old_value) * 100
        return round(percentage_change, 2)
    except ZeroDivisionError:
        return 0.0


def save_last_params (params):
    with open('data/params.json', 'w') as json_file:
        json.dump(params, json_file, ensure_ascii=False)



def get_last_params():
    with open('data/params.json', 'r') as json_file:
        return json.load(json_file)

def fund_row(percent):
    return dbc.Row([
                dbc.Col([
                    dcc.Slider(
                        id='fund_slider',
                        max=30,
                        min=0.1,
                        step=0.1,
                        marks=None,
                        value=3.5
                    )
                ], id='fund_slider_col', className='col-md-10'),
                dbc.Col([
                    dbc.Input(
                        id='fund_input',
                        type='number',
                        step=0.1,
                        value=percent,
                        size='md'
                    )
                ], className='col-md-2'),
            ])

def get_print_class(value):
    if value > 0:
        item_class = 'text-success fw-bold text-end';
        item_print = '+' + str(round(value, 2)) + ''
    elif value < 0:
        item_class = 'text-danger fw-bold text-end';
        item_print = str(round(value, 2)) + ''
    else:
        item_class = 'text-dark fw-bold text-end';
        item_print = '0'
    return item_print, item_class


def print_little_value(value, treshold):
    if abs(value) <= treshold:
        return round(value, 0)
    return round(value, 2)

def billions(value):
    return round(value / 1000000,2)

def thousands(value):
    return round(value / 1000,2)
