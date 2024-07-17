from dash import Input, State

class Constants:
    SO_PM = 'Помаршрутная СО, тыс. руб.'
    SO_3Z = 'Вариант по 3м зонам СО, тыс. руб.'
    SO_SS = 'Среднесетевая СО, тыс. руб.'
    SO_KB = 'Комбинированная СО, тыс. руб.'
    SO_PM_DIFF = 'Помаршрутная СО с дифференциацией, тыс. руб.'
    SO_3Z_DIFF = 'Вариант по 3м зонам СО с дифференциацией, тыс. руб.'
    SO_SS_DIFF = 'Среднесетевая СО с дифференциацией, тыс. руб.'
    SO_KB_DIFF = 'Комбинированная СО с дифференциацией, тыс. руб.'
    PER = 'Условно-переменные расходы, тыс. руб'
    PER_DOL = 'Доля условно-переменных расходов'

    POST = 'Условно-постоянные расходы, тыс. руб'
    POST_DOL = 'Доля условно-постоянных расходов'
    POL = 'Расходы полные, тыс. руб'
    CAP = 'Инвест ремонт, тыс. руб'
    POL_CAP = 'Расходы полные + инвест ремонт, тыс. руб'


    PR_P = 'Доходы 2024, тыс.руб'
    EPL = '2024 ЦЭКР груззоборот, тыс ткм'
    P = '2023 Объем перевозок, т.'
    CARGO = 'Группа груза'


    VAG = 'Перевезено вагонов'
    EPL_B = 'Грузооборот брутто(2019), тыс. ткм'
    EPL_N = 'Грузооборот нетто(2019), тыс. ткм'
    INVEST_REMONT = 'Капитальные вложения(инвест),тыс. руб.'
    INVEST_NETWORK = 'Расходы на общесетевые инвестпроекты, тыс. руб.'
    INVEST_DIRECTION = 'Расходы на инвестпроекты по направлениям, тыс. руб.'
    NETWORK_PART = 'Доля от расходов на общесетевые проекты'
    DIRECTION_PART = 'Доля от расходов на проекты по направлениям'

    MESSAGE = 'Вид сообщения'
    SIDE = 'Направление'
    HOLDING = 'Холдинг'

    PRICE_RUB = 'Стоимость 1 тонны на рынке_2024, руб./т.'
    OPER_RUB = 'Расходы по оплате услуг операторов_2024, руб. за тонну'
    PER_RUB = 'Расходы на перевалку_2024, руб. за тонну'
    RZD_TOTAL = 'РЖД_ИТОГО'
    RZD_GR = 'Расходы по оплате услуг ОАО "РЖД", руб. за тонну (груженый пробег)'
    RZD_POR = 'Расходы по оплате услуг ОАО "РЖД", руб. за тонну (порожний пробег)'


    # выборки в параметрах
    COSTS_BASE_VARIANTS = [
        {'label': 'Тариф по себестоимости (помаршрутный принцип)','value': 'option1'},
        {'label': 'Тариф по уровню расходов', 'value': 'option2'},
    ]
    DIRECTION_VARIANTS = [
        {'label': 'Среднесетевой', 'value': 'option1'},
        {'label': 'По 3 зонам', 'value': 'option2'},
        {'label': 'Комбинированный', 'value': 'option3'},
        {'label': 'Помаршрутный', 'value': 'option4'}
    ]

    APPROACH_VARIANTS = [
        {'label': 'Без дифференциации', 'value': 'option1'},
        {'label': 'С дифференциацией', 'value': 'option2'},
    ]

    COSTS_VARIANTS = [
        {'label': 'Не ниже переменных', 'value': 'option1'},
        {'label': 'Не ниже полных', 'value': 'option2'},
    ]

    INVEST_VARIANTS = [
        {'label': 'Затраты на ремонт инфраструктуры, переквалифицированные в кап. вложения', 'value': 'option1'},
        {'label': 'Инвестиционная программа ОАО "РЖД"', 'value': 'option2'},
    ]

    YEAR_VARIANTS = [
        {'label': year, 'value': str(year)} for year in range(2026, 2031)
    ]
    YEARS = [2025,  2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033, 2034, 2035]
    LITTLE_YEARS = [2025,  2026, 2027, 2028, 2029, 2030]
    # YEARS = LITTLE_YEARS


    INPUTS = [
        Input('calculate-button', 'n_clicks'),
        State('epl_change', 'value'),
        State('market_loss', 'value'),
        State('cif_fob', 'value'),
        State('index_sell_prices', 'value'),
        State('price_variant', 'value'),
        State('index_sell_coal', 'value'),
        State('index_oper', 'value'),
        State('index_per', 'value'),
        [State(str(year) + '_year_total_index', 'children') for year in YEARS],
    ]

    TURNOVER_VARIANTS = [
        {'label': 'Не учитывать','value': 'option1'},
        {'label': 'ЦЭКР', 'value': 'cekr'},
        {'label': 'ИПЭМ', 'value': 'ipem'},
       # {'label': 'Фин. план (май)', 'value': 'option3'},
    ]

    CARGOS = [
        "Грузы на своих осях",
        "Кокс каменноугольный",
        "Лесные грузы",
        "Минерально - строит.",
        "Нефтяные грузы",
        "Остальные грузы",
        "Руды  всякие",
        "Уголь каменный",
        "Удобрения",
        "Хлебные грузы",
        "Черные металлы",
    ]

    IPEM_CARGOS = [
        "Уголь каменный",
        "Кокс каменноугольный",
        "Нефтяные грузы",
        "Черные металлы",
        "Руды всякие",
        "Минерально-строительные грузы",
        "Удобрения",
        "Зерно",
        "Лесные грузы"
    ]

    AGG_PARAMS = {
        P: 'sum',
        VAG: 'sum',
        EPL_B: 'sum',
        EPL_N: 'sum',
        PR_P: 'sum',
        SO_PM: 'sum',
        SO_SS: 'sum',
        SO_3Z: 'sum',
        SO_KB: 'sum',
        SO_PM_DIFF: 'sum',
        SO_3Z_DIFF: 'sum',
        SO_SS_DIFF: 'sum',
        SO_KB_DIFF: 'sum',
        PER: 'sum',
        POST: 'sum',
        POL: 'sum',
        INVEST_REMONT: 'sum',
        INVEST_NETWORK: 'sum',
        INVEST_DIRECTION: 'sum',
        'so_start': 'sum',
        'so_column': 'sum',
        'delta_start': 'sum',
        'Код группы по ЦО-12': 'min'
    }


    def __init__(self, start_year):
        self.START_YEAR = start_year

    @classmethod
    def from_default(cls):
        return cls(2025)