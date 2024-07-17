import pandas as pd
import logging

from pages.constants import Constants
from pages.data import get_main_data, get_small_data, get_ipem_data, get_ipem_related_routes
import numpy as np
import pages.scenario_parameters.tarif_rules as tr
import pages.scenario_parameters.tarif_rules_prev as tr_prev



CON = Constants(2025)


# функция, рассчитывающая параметры на уровне маршрутов
def calculate_data(data_type='main', params={}):
    if data_type == 'main':
        df = get_main_data()
    else:
        df = get_small_data()



    diff = pd.read_excel('data/diff.xlsx')
    df = pd.merge(df,diff,how='inner',left_on=CON.CARGO,right_on=CON.CARGO)

    logging.info('Старт обработки данных на строках')

    df = calculate_base_revenues(df, CON.YEARS, params['revenue_index_values'],params['epl_change'])


    print('calc ok')

    return df


# функция, грппирующая данные маршрутов
def group_data(df, param1, param2):
    logging.info('Начало группировки данных')
    # group1_variant = params['group1_variant']
    # group2_variant = params['group2_variant']
    group1_variant = param1
    group2_variant = param2
    # рассчитываем параметры
    agg_params = {
        CON.P: 'sum',
        CON.EPL: 'sum',
        CON.PR_P: 'sum',
        'Доходы 2023, тыс.руб': 'sum',
        '2024_lost': 'sum',
        'rules_total': 'sum',
    }

    rules = tr.load_rules(active_only=True)
    for year in CON.YEARS:
        revenue = f'Доходы {year}, тыс.руб'
        agg_params[revenue] = 'sum'
        agg_params[f'Доходы {year}_0, тыс.руб'] = 'sum'


        rule_index = 0
        for rule_obj in rules:
            if rule_obj["active"]:
                rule_index += 1
                revenue_rule = f'Доходы {year}_{rule_index}, тыс.руб'
                agg_params[revenue_rule] = 'sum'



    sorting_param = group1_variant if group1_variant !='Группа груза' else 'Код группы'
    sorting_asc = True

    group_parameter = [group1_variant] if group2_variant == 'Нет' else [group1_variant, group2_variant]

    df_grouped = df.groupby(group_parameter).agg(agg_params)
    df_grouped = df_grouped.reset_index()
    if group1_variant=='Группа груза':
        df_grouped.loc[df_grouped['Группа груза'] == 'Уголь каменный', 'Код группы'] = 1
        df_grouped.loc[df_grouped['Группа груза'] == 'Кокс каменноугольный', 'Код группы'] = 2
        df_grouped.loc[df_grouped['Группа груза'] == 'Нефть и нефтепродукты', 'Код группы'] = 3
        df_grouped.loc[df_grouped['Группа груза'] == 'Руды металлические', 'Код группы'] = 4
        df_grouped.loc[df_grouped['Группа груза'] == 'Черные металлы', 'Код группы'] = 5
        df_grouped.loc[df_grouped['Группа груза'] == 'Лесные грузы', 'Код группы'] = 6
        df_grouped.loc[df_grouped['Группа груза'] == 'Минерально-строит.', 'Код группы'] = 7
        df_grouped.loc[df_grouped['Группа груза'] == 'Удобрения', 'Код группы'] = 8
        df_grouped.loc[df_grouped['Группа груза'] == 'Хлебные грузы', 'Код группы'] = 9
        df_grouped.loc[df_grouped['Группа груза'] == 'Остальные грузы', 'Код группы'] = 10

    df_grouped = df_grouped.sort_values(by=sorting_param, ascending=sorting_asc)

    if group2_variant != 'Нет':
        df_high = df_grouped.groupby(group1_variant).agg(agg_params).reset_index()
        df_high[group2_variant] = 'ИТОГО'
        df_grouped = pd.concat([df_grouped, df_high], ignore_index=True)
        # df_grouped = df_grouped.sort_values(by=[group1_variant, CON.PR_P],ascending=[False,False])
        df_grouped = df_grouped.sort_values(by=[sorting_param, CON.PR_P], ascending=[sorting_asc, False])

    logging.info('Конец группировки данных')
    print('group ok')

    return df_grouped


def group_data_cube(df):
    agg_params = {
        CON.P: 'sum',
        CON.EPL: 'sum',
        CON.PR_P: 'sum',
        'Доходы 2023, тыс.руб': 'sum',
        '2024_lost': 'sum',
        'rules_total': 'sum',
    }

    rules = tr.load_rules(active_only=True)
    for year in CON.YEARS:
        revenue = f'Доходы {year}, тыс.руб'
        agg_params[revenue] = 'sum'
        agg_params[f'Доходы {year}_0, тыс.руб'] = 'sum'

        rule_index = 0
        for rule_obj in rules:
            if rule_obj["active"]:
                rule_index += 1
                revenue_rule = f'Доходы {year}_{rule_index}, тыс.руб'
                agg_params[revenue_rule] = 'sum'



    group_parameter =  ['Группа груза', 'Код груза', 'Направления', 'Род вагона', 'Вид перевозки', 'Тип парка', 'Холдинг']

    df_grouped = df.groupby(group_parameter).agg(agg_params)
    df_grouped = df_grouped.reset_index()
    return df_grouped


def  calculate_base_revenues(df, YEARS, INDEXES, EPL_CHANGE):
    base_revenue_col = 'Доходы 2024, тыс.руб'
    revenue_base = CON.PR_P
    epl_base = f'2024 ЦЭКР груззоборот, тыс ткм'
    rules = tr.load_rules(active_only=True)
    df = create_new_columns(df, YEARS, base_revenue_col,rules)

    prev_rules = tr_prev.load_rules(active_only=True)

    # df['2024_lost'] = df[base_revenue_col]
    for rule_obj in prev_rules:
        filters = []
        for condition in rule_obj["conditions"]:
            parameter = condition["parameter"]
            include = condition["include"]
            values = condition["values"].split(';') if condition["values"] else []
            if values == ['Все']:
                values = df[parameter].unique()
            if include == 'включает':
                filters.append(df[parameter].isin(values))
            else:
                filters.append(~df[parameter].isin(values))
        if rule_obj['variant'] == 'млрд': # миллиарды
            total = df.loc[np.logical_and.reduce(filters), base_revenue_col].sum()
            df.loc[np.logical_and.reduce(filters), 'part'] = df.loc[np.logical_and.reduce(filters), base_revenue_col] / total
            df.loc[np.logical_and.reduce(filters), base_revenue_col] = df.loc[np.logical_and.reduce(filters), base_revenue_col] + (float(rule_obj['index_2024']) * 1000000 * df.loc[np.logical_and.reduce(filters), 'part'])
        else:  # индексы
            if rule_obj['variant'] == '*':
                df.loc[np.logical_and.reduce(filters), base_revenue_col] = df.loc[np.logical_and.reduce(filters), base_revenue_col] * float(rule_obj['index_2024'])

    df['2024_lost'] = df[base_revenue_col] - df['2024_lost']
    year_index = 1

    rule_indexation = {}
    for rule_obj in rules:
        rule_indexation[rule_obj["id"]] = []

    # объем перевозок 2024
    df['2024 Объем перевозок, т.'] = df['2023 Объем перевозок, т.'] * df['2024 ЦЭКР груззоборот, тыс ткм'] * 1000 / df['2023 Грузооборот, т_км']

    df['epl_tarif_base'] = df[revenue_base] / df[epl_base]

    df['rules_total'] = 0
    for i, year in enumerate(YEARS):
        year_index *= INDEXES[i]
        revenue = f'Доходы {year}, тыс.руб'
        revenue_prev = f'Доходы {year-1}, тыс.руб'
        revenue_base = f'Доходы {year}_0, тыс.руб'
        revenue_noindex = f'Доходы {year}_без учета индексации, тыс.руб'

        epl = f'{year} ЦЭКР груззоборот, тыс ткм'
        epl_prev = f'{year-1} ЦЭКР груззоборот, тыс ткм'

        if EPL_CHANGE == [True]:
        # учитываем рост грузооборота
            df.loc[df['epl_tarif_base'].notna(), revenue_noindex] = df[revenue_prev]  * (df[epl] / df[epl_prev])
            df.loc[df['epl_tarif_base'].isna(), revenue_noindex] = df[revenue_prev]
            df.loc[df[epl_prev].notna(), f'{year} Объем перевозок, т.'] = df[f'{year - 1} Объем перевозок, т.'] * (df[epl] / df[epl_prev])
            df.loc[df[epl_prev].isna(), f'{year} Объем перевозок, т.'] = df[f'{year - 1} Объем перевозок, т.']

        else:
            df[revenue_noindex] = df[revenue_prev]
            df[epl] = df[epl_prev]
            df[f'{year} Объем перевозок, т.'] = df[f'{year-1} Объем перевозок, т.']
        # базовая индексация
        df[revenue_base] = df[revenue_noindex] * (INDEXES[i]-1) * df['base_diff']

        df[revenue] = df[revenue_noindex] + df[revenue_base]
        rule_index = 0

        for rule_obj in rules:
            rule_index += 1
            revenue_rule = f'Доходы {year}_{rule_index}, тыс.руб'
            revenue_rule_prev = f'Доходы {int(year)-1}_{rule_index}, тыс.руб'
            filters = []
            for condition in rule_obj["conditions"]:
                parameter = condition["parameter"]
                include = condition["include"]
                values = condition["values"].split(';') if condition["values"] else []
                if values == ['Все']:
                    values = df[parameter].unique()
                if include == 'включает':
                    filters.append(df[parameter].isin(values))
                else:
                    filters.append(~df[parameter].isin(values))

            rule_coef = float(rule_obj['index_'+str(year)]) - 1
            df.loc[np.logical_and.reduce(filters), revenue_rule] = df[revenue_noindex] * rule_coef * df['rules_diff'] * int(rule_obj['base_percent'])/100
            df.loc[np.logical_and.reduce(filters), f'rules%_{year}'] *=  float(rule_obj['index_'+str(year)]) * df['rules_diff']
            df.loc[np.logical_and.reduce(filters), f'rules%_{year}_{rule_index}'] =  float(rule_obj['index_'+str(year)])

            df[revenue] += df[revenue_rule]

    return df


def create_new_columns (df, years, base_revenue_col, rules):
    new_columns = {}
    new_columns['2024_lost'] = df[base_revenue_col]
    for year in years:
        rule_index = 0
        new_columns[f'rules%_{year}'] = 1.0
        for rule_obj in rules:
            rule_index += 1
            revenue_rule = f'Доходы {year}_{rule_index}, тыс.руб'
            new_columns[f'rules%_{year}_{rule_index}'] = 1.0
            new_columns[revenue_rule] = 0.0
            new_columns[f'rules%_{year}_{rule_index}'] = 1.0

    new_df = pd.DataFrame(new_columns)
    df = pd.concat([df, new_df], axis=1)
    return df
def calculate_data_ipem(df, index_df, params):

    related_df = get_ipem_related_routes()
    related_df = calculate_related(related_df, params)

    prev_rules = tr_prev.load_rules(active_only=True)
    related_df['2024_coeff'] = 1.0
    main_df = get_main_data()
    main_df['lost_2024'] = 0.0
    main_df['part'] = 0.0
    for rule_obj in prev_rules:
        filters = get_filters(related_df,rule_obj)
        filters_main = get_filters(main_df, rule_obj)
        if rule_obj['variant'] == 'млрд': # миллиарды

            total = main_df.loc[np.logical_and.reduce(filters_main), '2024 ЦЭКР груззоборот, тыс ткм'].sum()
            main_df.loc[np.logical_and.reduce(filters_main), 'part'] = main_df.loc[np.logical_and.reduce(filters_main),  '2024 ЦЭКР груззоборот, тыс ткм'] / total
            main_df.loc[np.logical_and.reduce(filters_main), 'lost_2024'] += (rule_obj['index_2024'] * 1000000 * main_df.loc[np.logical_and.reduce(filters_main), 'part'])
            # df.loc[np.logical_and.reduce(filters), base_revenue_col] = df.loc[np.logical_and.reduce(filters), base_revenue_col] + (float(rule_obj['index_2024']) * 1000000 * df.loc[np.logical_and.reduce(filters), 'part'])
        else:  # индексы
            if rule_obj['variant'] == '*':
                related_df.loc[np.logical_and.reduce(filters), '2024_coeff'] *= float(rule_obj['index_2024'])



    related_df = related_df.merge(main_df[['Ключ ИПЕМ', 'lost_2024','part']], on='Ключ ИПЕМ', how='left')


    related_df['money_lost_coeff'] = 1 - abs(related_df['lost_2024'] / related_df['Доходы 2024, тыс.руб'])

    related_df['money_lost_coeff'] = related_df['money_lost_coeff'].fillna(1)

    related_df['2024_coeff'] *= related_df['money_lost_coeff']

    columns = ['Ключ ИПЕМ','2024_coeff']
    rules = tr.load_rules(active_only=True)
    for i, year in enumerate(CON.YEARS):
        columns.append(f'rules%_{year}')
        for index,rule in enumerate(rules,start=1):
            columns.append(f'rules%_{year}_{index}')

    related_df = related_df[columns]

    df = get_ipem_data()

    print('Старт обработки данных МПЕМ')

    df.fillna(0, inplace=True)


    df = calculate_base_revenues_ipem(df, related_df, CON.YEARS, params['revenue_index_values'],params['ipem'])


    print('calc ipem ok')

    return df

def calculate_base_revenues_ipem(df, related_df, YEARS, INDEXES, IPEM):


    df = df.merge(related_df, left_on='ipem_gr', right_on='Ключ ИПЕМ',how='left')
    df = df.merge(related_df, left_on='ipem_pr', right_on='Ключ ИПЕМ',how='left')

    # condition = df['index']==234
    # print(df[condition]['Ключ ИПЕМ_x'])
    # print(related_df.columns)


    coeffs = pd.read_excel('data/ipem_coeffs.xlsx')
    prices_dollar = pd.read_excel('data/prices$.xlsx')

    df = df.merge(coeffs,on='Группа груза')

    df['Стоимость 1 тонны на рынке_2024, руб./т.'] = df['Стоимость 1 тонны на рынке, руб./т.']
    if IPEM["index_sell_coal"] == [True]:
        coal = pd.read_excel('data/ipem_coal.xlsx')
        df = df.merge(coal, on=['Группа груза','Вид сообщения'], how='left')
        df.loc[df['Группа груза'] == 'Уголь', 'Стоимость 1 тонны на рынке_2024, руб./т.'] = df['Стоимость 1 тонны на рынке, руб./т.'] * df[f'ЦЕНА_УГОЛЬ_2024']
    if IPEM["price_variant"] == 'ЦСР':
        csr = pd.read_excel('data/csr_coeffs.xlsx')
        df = df.merge(csr, on=['Группа груза', 'Вид сообщения'], how='left')
    year_index = 1
    df[f'{CON.RZD_TOTAL}_2024'] = df[f'{CON.RZD_GR}'] + df[f'{CON.RZD_POR}']
    df[f'{CON.RZD_GR}_2024'] = df[f'{CON.RZD_GR}']
    df[f'{CON.RZD_POR}_2024'] = df[f'{CON.RZD_POR}']


    df[f'price_coeff'] = 1
    df[f'oper_coeff'] = 1
    df[f'per_coeff'] = 1
    df[CON.PER_RUB] = df[CON.PER_RUB].fillna(0)
    df[CON.OPER_RUB] = df[CON.OPER_RUB].fillna(0)
    df[f'rules_2024'] = 0
    df[f'base_2024'] = 0
    df[f'base%_2024'] = 0
    df[f'rules%_2024'] = 0
    df[f'rules%_2024_gr'] = 0
    df[f'Стоимость 1 тонны на рынке_2024_$, руб./т.'] = df[f'Стоимость 1 тонны на рынке_2024, руб./т.'] / prices_dollar.loc[0,'prices']

    df[f'{CON.RZD_GR}_2024_loss'] = df[f'{CON.RZD_GR}_2024'] * (1 - df[f'2024_coeff_x'])
    df[f'{CON.RZD_POR}_2024_loss'] = df[f'{CON.RZD_POR}_2024'] * (1 - df[f'2024_coeff_y'])
    df[f'{CON.RZD_TOTAL}_2024_loss'] = df[f'{CON.RZD_POR}_2024_loss'] + df[f'{CON.RZD_GR}_2024_loss']
    df[f'2024_coeff'] = (df[f'{CON.RZD_TOTAL}_2024']-df[f'{CON.RZD_TOTAL}_2024_loss']) / df[f'{CON.RZD_TOTAL}_2024']
    df[f'{CON.RZD_POR}_2024'] -= df[f'{CON.RZD_POR}_2024_loss']
    df[f'{CON.RZD_GR}_2024'] -= df[f'{CON.RZD_GR}_2024_loss']
    df[f'{CON.RZD_TOTAL}_2024'] -= df[f'{CON.RZD_TOTAL}_2024_loss']

    for i, year in enumerate(YEARS):
        if IPEM["index_sell_prices"] == [True]:
            if IPEM["price_variant"] == 'Минэк':
                price_col = f'ЦЕНА_{year}'
            else:
                price_col = f'ЦЕНА_ЦСР_{year}'
            df[f'price_coeff'] *= df[price_col]
            if IPEM["index_sell_coal"] == [True]:
                dollar_index = prices_dollar.loc[i+1,'prices'] / prices_dollar.loc[i,'prices']
                df.loc[df['Группа груза'] == 'Уголь', 'price_coeff'] /= df[price_col]
                df.loc[df['Группа груза']=='Уголь','price_coeff'] *= df[f'ЦЕНА_УГОЛЬ_{year}'] * dollar_index
        if IPEM["index_oper"] == [True]:
            df[f'oper_coeff'] *= df[f'ОПЕРАТОРЫ_{year}']
        if IPEM["index_per"] == [True]:
            df[f'per_coeff'] *= df[f'ПЕРЕВАЛКА_{year}']

        df = df.copy()
        df[f'Стоимость 1 тонны на рынке_{year}, руб./т.'] = df['Стоимость 1 тонны на рынке, руб./т.'] * df[f'price_coeff']
        df[f'Стоимость 1 тонны на рынке_{year}_$, руб./т.'] = df[f'Стоимость 1 тонны на рынке_{year}, руб./т.'] / prices_dollar.loc[0,'prices']

        df[f'Расходы по оплате услуг операторов_{year}, руб. за тонну'] = df['Расходы по оплате услуг операторов_2024, руб. за тонну'] * df[f'oper_coeff']
        df[f'Расходы на перевалку_{year}, руб. за тонну'] = df['Расходы на перевалку_2024, руб. за тонну'] * df[f'per_coeff']

        year_index *= INDEXES[i]
        df[f'{CON.RZD_GR}_{year}'] =  df[f'{CON.RZD_GR}_{year-1}'] * INDEXES[i]
        df[f'{CON.RZD_POR}_{year}'] = df[f'{CON.RZD_POR}_{year-1}'] * INDEXES[i]

        df[f'base%_{year}'] = INDEXES[i]
        df[f'base_{year}'] = df[f'{CON.RZD_TOTAL}_{year-1}'] * (INDEXES[i] - 1)

        df[f'{CON.RZD_POR}_{year}'] += df[f'{CON.RZD_POR}_{year-1}'] * (df[f'rules%_{year}_y'] - 1) * (INDEXES[i])
        df[f'{CON.RZD_GR}_{year}'] += df[f'{CON.RZD_GR}_{year-1}'] * (df[f'rules%_{year}_x'] - 1) * (INDEXES[i])

        #дял отдельных правил
        rules = tr.load_rules(active_only=True)
        for index, rules in enumerate(rules,start=1):
            df[f'rules%_{year}_{index}'] = (df[f'{CON.RZD_GR}_{year-1}'] * (df[f'rules%_{year}_{index}_x'] - 1) * INDEXES[i] +
                                            df[f'{CON.RZD_POR}_{year - 1}'] * (df[f'rules%_{year}_{index}_y'] - 1) * INDEXES[i]) / \
                                           (df[f'{CON.RZD_GR}_{year-1}'] + df[f'{CON.RZD_POR}_{year-1}'])
            df[f'rules%_{year}_{index}_gr'] = df[f'{CON.RZD_GR}_{year-1}'] * (df[f'rules%_{year}_{index}_x'] - 1) * INDEXES[i] / \
                                              (df[f'{CON.RZD_GR}_{year-1}'])

        df[f'rules_{year}'] = df[f'{CON.RZD_POR}_{year-1}'] * (df[f'rules%_{year}_y'] - 1) * INDEXES[i] + \
                              df[f'{CON.RZD_GR}_{year-1}'] * (df[f'rules%_{year}_x'] - 1) * INDEXES[i]

        df[f'{CON.RZD_TOTAL}_{year}'] = df[f'{CON.RZD_GR}_{year}'] + df[f'{CON.RZD_POR}_{year}']
        df[f'rules%_{year}'] = 1 + df[f'rules_{year}'] / df[f'{CON.RZD_TOTAL}_{year-1}']
        df[f'rules%_{year}_gr'] = 1 + df[f'{CON.RZD_GR}_{year-1}'] * (df[f'rules%_{year}_x'] - 1) * INDEXES[i] / df[f'{CON.RZD_GR}_{year-1}']
        df[f'rules%_{year}_por'] = 1 + df[f'{CON.RZD_POR}_{year-1}'] * (df[f'rules%_{year}_y'] - 1) * INDEXES[i] / df[f'{CON.RZD_POR}_{year-1}']

    return df.copy()


def cost_index_multiply(df, year, start_year):
    parameter = 'Темп роста себестоимости (грузовые перевозки)'
    parameter = 'Темп изменения расходов (грузовые перевозки)'
    total_index = df.loc[(df['Показатель'] == parameter) & (df['Год'] <= year) & (
                df['Год'] > start_year), 'Значение'].prod()
    return total_index


def tarif_index_multiply(df, year, start_year):
    parameter = 'Индексация тарифов'

    total_index = df.loc[(df['Показатель'] == parameter) & (df['Год'] <= year) & (
                df['Год'] > start_year), 'Значение'].prod()
    return total_index



def calculate_related(df, params):

    rules = tr.load_rules(active_only=True)
    for i, year in enumerate(CON.YEARS):
        rule_index = 0
        df[f'rules%_{year}'] = 1.0
        for rule_obj in rules:
            rule_index += 1
            df[f'rules%_{year}_{rule_index}'] = 1.0
            filters = []
            for condition in rule_obj["conditions"]:
                parameter = condition["parameter"]
                include = condition["include"]
                values = condition["values"].split(';') if condition[
                    "values"] else []
                if values == ['Все']:
                    values = df[parameter].unique()
                if include == 'включает':
                    filters.append(df[parameter].isin(values))
                else:
                    filters.append(~df[parameter].isin(values))

            df.loc[np.logical_and.reduce(filters), f'rules%_{year}'] += (float(rule_obj['index_' + str(year)])-1) * float(rule_obj['base_percent'])/100
            df.loc[np.logical_and.reduce(filters), f'rules%_{year}_{rule_index}'] =  float(rule_obj['index_'+str(year)]) * float(rule_obj['base_percent'])/100
    return df


def get_filters(df,rule_obj):
    filters = []
    for condition in rule_obj["conditions"]:
        parameter = condition["parameter"]
        include = condition["include"]
        values = condition["values"].split(';') if condition["values"] else []
        if values == ['Все']:
            values = df[parameter].unique()
        if include == 'включает':
            filters.append(df[parameter].isin(values))
        else:
            filters.append(~df[parameter].isin(values))
    return filters


def market_coef (df):
    print('start market coef')
    agg_params = {}
    agg_params[f'Доходы 2024, тыс.руб'] = 'sum'
    agg_params[f'2024 Объем перевозок, т.'] = 'sum'
    for year in CON.YEARS:
        agg_params[f'Доходы {year}, тыс.руб'] = 'sum'
        agg_params[f'{year} Объем перевозок, т.'] = 'sum'

    df = df.groupby(['Группа груза','Вид перевозки','Направления','Холдинг']).agg(agg_params).reset_index()


    # Определите границы интервалов для growth_rate
    df[f'ds_2024'] = df[f'Доходы 2024, тыс.руб'] / df[f'2024 Объем перевозок, т.']
    df[f'money_loss_total'] = 0
    df[f'cargo_loss_total'] = 0
    bins_growth = [-float('inf'),0.01,0.02,0.03,0.04,0.05,0.06,0.07,0.08,0.09, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1, float('inf')]
    for year in CON.YEARS:
        df[f'market_coefficient_{year}'] = 1.0
        df[f'ds_{year}'] = df[f'Доходы {year}, тыс.руб'] / df[f'{year} Объем перевозок, т.']
        df[f'growth_rate_{year}'] = df[f'ds_{year}'] / df[f'ds_{year-1}'] - 1
        # Маска для growth_rate
        mask_growth = pd.cut(df[f'growth_rate_{year}'], bins=bins_growth, labels=False)

        interval_to_coefficient = {
            1: 'Увеличение на 1%',
            2: 'Увеличение на 2%',
            3: 'Увеличение на 3%',
            4: 'Увеличение на 4%',
            5: 'Увеличение на 5%',
            6: 'Увеличение на 6%',
            7: 'Увеличение на 7%',
            8: 'Увеличение на 8%',
            9: 'Увеличение на 9%',
            10: 'Увеличение на 10%',
            11: 'Увеличение на 20%',
            12: 'Увеличение на 30%',
            13: 'Увеличение на 40%',
            14: 'Увеличение на 50%',
            15: 'Увеличение на 60%',
            16: 'Увеличение на 70%',
            17: 'Увеличение на 80%',
            18: 'Увеличение на 90%',
            19: 'Увеличение на 100%'
        }

        market_df = pd.read_excel('data/market_total.xlsx')

        for index, row in market_df.iterrows():
            mask_cargo = df['Группа груза'] == row['Группа груза']
            mask_type = df['Вид перевозки'] == row['Вид перевозки']
            maek_direction = df['Направления'] == row['Направления']
            if row['Вид перевозки'] == 'все виды сообщения':
                mask_equal = mask_cargo
            elif row['Направления'] == 'Все направления':
                mask_equal = mask_cargo & mask_type
            else:
                mask_equal = mask_cargo & mask_type & maek_direction

            for interval, coefficient_column in interval_to_coefficient.items():
                mask = (mask_growth == interval) & mask_equal
                df.loc[mask, f'market_coefficient_{year}'] = float(row[coefficient_column])

        df[f'money_loss_{year}'] = df[f'Доходы {year}, тыс.руб'] * (1 - df[f'market_coefficient_{year}'])
        df[f'cargo_loss_{year}'] = df[f'{year} Объем перевозок, т.'] * (1 - df[f'market_coefficient_{year}'])
        df[f'money_loss_total'] += df[f'money_loss_{year}']
        df[f'cargo_loss_total'] += df[f'cargo_loss_{year}']

    # df.to_excel('data/market_kek.xlsx', index=False)
    print('end market coef')
    return df