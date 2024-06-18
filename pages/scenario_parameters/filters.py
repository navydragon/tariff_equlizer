from dash import html
import dash_bootstrap_components as dbc

def filters(items):

    return html.Section(className='my-section', children=[
    html.Div(className='my-section__header', children=[
        html.H2(className='my-section__title', children='Сегментация и фильтрация'),
        # html.Span(className='my-section__badge', children='Варьируемые параметры')
    ]),
    html.Div(className='my-separate my-separate_width_600 my-separate_vector_left'),
    html.Ul(className='my-filter__list', children=[
        html.Li(className='my-filter__item', children=[
            html.H4(className='my-section__subtitle', children='Группировка верхнего уровня'),
            dbc.Select(options=[
                {'label': 'Наименование груза',
                 'value': 'Наименование груза ЦО-12'},
                {'label': 'Холдинг отправителя',
                 'value': 'Холдинг отправителя'},
                {'label': 'Направление',
                 'value': 'Направление'},
                {'label': 'Вид сообщения',
                 'value': 'Вид сообщения'}],
                 value = 'Наименование груза ЦО-12', id='group1_variant')
        ]),
        html.Li(className='my-filter__item', children=[
            html.H4(className='my-section__subtitle', children='Фильтр по грузу'),
            dbc.Select(className='form-select',
                         options=[{'label': 'Нет', 'value': 'no'}] + [{'label': cargo, 'value': cargo} for cargo in items['CARGOS']],
                         id='cargo_filter', value='no')
        ]),
        html.Li(className='my-filter__item', children=[
            html.H4(className='my-section__subtitle', children='Фильтр по направлению'),
            dbc.Select(className='form-select', id='side_filter', value='no',
                       options=[{'label': 'Нет', 'value': 'no'}] + [{'label': side, 'value': side} for side in items['SIDES']])
        ]),
        html.Li(className='my-filter__item', children=[
            html.H4(className='my-section__subtitle',
                    children='Группировка внутри уровня'),
            dbc.Select(className='form-select', options=[
                {'label': 'Нет', 'value': 'no'},
                {'label': 'Наименование груза',
                 'value': 'Наименование груза ЦО-12'},
                {'label': 'Холдинг отправителя',
                 'value': 'Холдинг отправителя'},
                {'label': 'Направление', 'value': 'Направление'},
                {'label': 'Вид сообщения', 'value': 'Вид сообщения'},
            ], value='no', id='group2_variant')
        ]),
        html.Li(className='my-filter__item', children=[
            html.H4(className='my-section__subtitle', children='Фильтр по виду сообщения'),
            dbc.Select(className='form-select', value='no',
                         options=[{'label': 'Нет', 'value': 'no'}] + [{'label': message, 'value': message} for message in items['MESSAGES']],
                         id='message_filter')
        ]),
        html.Li(className='my-filter__item', children=[
            html.H4(className='my-section__subtitle',
                    children='Фильтр по холдингу'),
            dbc.Select(className='form-select', value='no',
                       options=[{'label': 'Нет', 'value': 'no'}] + [
                           {'label': holding, 'value': holding} for holding in
                           items['HOLDINGS']], id='holding_filter')
        ]),
    ])
])