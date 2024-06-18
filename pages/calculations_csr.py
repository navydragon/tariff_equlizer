import pandas as pd
import logging

from pages.constants import Constants
from pages.data import get_main_data, get_ipem_data, get_ipem_csr_data
import numpy as np
import pages.scenario_parameters.tarif_rules as tr
import pages.scenario_parameters.tarif_rules_prev as tr_prev

CON = Constants(2025)


def calculate_data_ipem(df, index_df, params):

    related_df = pd.read_excel('data/ipem_csr_related_routes.xlsx')
    related_df = calculate_related (related_df,params)

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

    related_df['Доходы 2024, тыс.руб'] = related_df['2024 Доходы,тыс.руб']
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

    df = get_ipem_csr_data()

    print('Старт обработки данных МПЕМ')

    df.fillna(0, inplace=True)



    df = calculate_base_revenues_ipem(df, related_df, CON.YEARS, params['revenue_index_values'],params['ipem'])



    print('calc ipem ok')

    return df



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


def calculate_base_revenues_ipem(df, related_df, YEARS, INDEXES, IPEM):


    df = df.merge(related_df, left_on='ipem_gr', right_on='Ключ ИПЕМ',how='left')
    df = df.merge(related_df, left_on='ipem_pr', right_on='Ключ ИПЕМ',how='left')

    # print(related_df.columns)


    coeffs = pd.read_excel('data/ipem_coeffs.xlsx')
    prices_dollar = pd.read_excel('data/prices$.xlsx')

    df = df.merge(coeffs,on='Группа груза')

    df['Стоимость 1 тонны на рынке_2024, руб./т.'] = df['Стоимость 1 тонны на рынке, руб./т.']

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
        if IPEM["index_oper"] == [True]:
            df[f'oper_coeff'] *= df[f'ОПЕРАТОРЫ_{year}']
        if IPEM["index_per"] == [True]:
            df[f'per_coeff'] *= df[f'ПЕРЕВАЛКА_{year}']

        df = df.copy()
        df[f'Стоимость 1 тонны на рынке_{year}, руб./т.'] = df['Стоимость 1 тонны на рынке, руб./т.'] * df[f'price_coeff_{year}']
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