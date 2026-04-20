import pandas as pd
import time
import inspect
from pages.constants import Constants as CON


def get_invest_data():
    invest_df = pd.read_excel('data/invest.xlsx')
    return invest_df


def get_revenue_parameters():
    # revenue_parameters = pd.read_feather('data/revenues_parameters.feather',)
    revenue_parameters = pd.read_csv('data/revenue_parameters.csv')
    # revenue_parameters.to_csv('data/revenue_parameters.csv')
    return revenue_parameters


def process_revenue_parameters(df, key):
    df['year'] = df['year'].astype(int)
    df['checkbox'] = df['checkbox'].astype(bool)
    df['param'] = df['param'].str.strip()
    # df.to_feather('data/' + key+ '.feather')
    df.to_csv('data/' + key + '.csv', index=False)
    # df.to_excel('data/' + key+ '.xlsx')
    # df.to_hdf('data/' + key+ '.h5', key=key,index=False)
    return df


def process_revenue_parameters_excel(df, key):
    df['year'] = df['year'].astype(int)
    df['checkbox'] = df['checkbox'].astype(bool)
    df['param'] = df['param'].str.strip()
    df.to_excel('data/' + key + '.xlsx', index=False)
    return df


main_data = None

def get_main_data():
    global main_data

    caller_frame = inspect.stack()[1]
    caller_filename = caller_frame.filename
    caller_lineno = caller_frame.lineno

    # Print the caller information
    # print(f"Function called from file: {caller_filename}, line: {caller_lineno}")

    # Вывод времени начала работы
    start_time = time.time()
    print(f"Начало работы: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Проверка, были ли данные уже загружены
    if main_data is None:
        # df = pd.read_hdf('data/tariff_data_grouped.h5', key='tariff_data')
        df = pd.read_feather('data/fp/tariff_data_grouped.feather')

        # Кэширование данных
        main_data = df
    # Вывод времени окончания работы
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Окончание работы: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Время выполнения: {elapsed_time:.2f} секунд")

    return main_data


small_data = None


def get_key_routes_data():
    df = pd.read_excel('data/fp/key_routes_db.xlsx')

    return df


def get_small_data():
    global small_data

    if small_data is None:
        df = pd.read_feather('data/fp/tariff_data_grouped_small.feather')
        small_data = df

    return small_data


ipem_data = None


def get_ipem_data():
    global ipem_data

    if ipem_data is None:
        df = pd.read_excel('data/te/total_ipem.xlsx')
        df = df.loc[df['ipem_gr'] != 'не участвует']
        df['route'] = df['Станция отправления'] + "-" + df['Станция назначения']
        ipem_data = df
    # make_ipem_related_routes(ipem_data)
    return ipem_data


ipem_csr_data = None


def get_ipem_csr_data():
    global ipem_csr_data

    if ipem_csr_data is None:
        df = pd.read_excel('data/te/total_ipem_csr.xlsx')
        df['route'] = df['Станция отправления'] + "-" + df['Станция назначения']
        ipem_data = df

    return ipem_data


def make_ipem_related_routes(ipem_calculated):
    combined_values = pd.concat(
        [ipem_calculated['ipem_gr'], ipem_calculated['ipem_pr']])
    unique_values_list = combined_values.unique().tolist()
    data = get_main_data()
    condition = data["Ключ ИПЕМ"].isin(unique_values_list)
    res = data.loc[condition]
    columns = ['Ключ ИПЕМ', 'Группа груза', 'Код груза', 'Код станц отпр РФ',
               'Код станц назн РФ', 'Дор отпр', 'Дор наз', 'Род вагона',
               'Вид перевозки', 'Категория отпр.', 'Тип парка', 'Вид спец. контейнера',
               'Холдинг', 'Направления', 'Код груза(изпод)']
    res = res.groupby(columns).sum(numeric_only=True).reset_index()
    res.to_feather('data/te/ipem_related_routes.feather')


def get_ipem_related_routes():
    return pd.read_feather('data/te/ipem_related_routes.feather')


def calculate_total_index(indexation_variant: str = 'Индексация по расп.N2991-р'):
    result = []
    index_df = get_revenue_parameters()
    index_param = 'indexation' if indexation_variant == 'Индексация по расп.N2991-р' else 'icd'

    params_values = {}
    params_checkboxes = {}
    for param in index_df['param'].unique():
        params_values[param] = index_df[index_df['param'] == param].sort_values('year')['value'].tolist()
        params_checkboxes[param] = index_df[index_df['param'] == param].sort_values('year')['checkbox'].tolist()

    for index, year in enumerate(CON.YEARS):
        total_index = 1
        if params_checkboxes.get(index_param)[index + 1]:
            total_index *= params_values.get(index_param)[index + 1]
        if params_checkboxes.get('cap_rem')[index + 1]:
            total_index *= params_values.get('cap_rem')[index + 1] / params_values.get('cap_rem')[index]
        if params_checkboxes.get('taxes')[index + 1]:
            total_index *= params_values.get('taxes')[index + 1] / params_values.get('taxes')[index]
        if params_checkboxes.get('tb')[index + 1]:
            total_index *= params_values.get('tb')[index + 1] / params_values.get('tb')[index]
        if params_checkboxes.get('invest')[index + 1]:
            total_index *= params_values.get('invest')[index + 1] / params_values.get('invest')[index]
        result.append(total_index)
    return result


def get_te_variants():
    #df = pd.read_excel('data/te/variants/te_variants.xlsx')
    #df.to_json('data/te/variants/te_variants.json', index=False)
    return pd.read_json('data/te/variants/te_variants.json')


def set_te_variants(df):
    df.to_json('data/te/variants/te_variants.json', index=False)
    pass


def get_plan_df():
    return pd.read_excel('data/fp/plan.xlsx', index_col='index')


def get_ipem_csr_related_routes():
    return pd.read_excel('data/te/ipem_csr_related_routes.xlsx')


def get_dollar_rate():
    return pd.read_excel('data/prices$.xlsx')
