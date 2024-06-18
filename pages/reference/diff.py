import pandas
from dash import Dash, html, dcc, callback, Output, Input, dash_table
import base64

import dash_bootstrap_components as dbc
##вспомог формулы
# pandas.set_option("use_inf_as_na",True)
###
data_input = pandas.DataFrame()
Sum_model_T = 0
Sum_model_D = 0

def diff_layout():
    global data_input, Sum_model_T, Sum_model_D
    data_input = pandas.read_excel("data/diff.xlsx")
    old_data = pandas.read_excel("data/new_tariffs.xlsx")
    data_input = data_input.merge(
        old_data[['Наименование груза ЦО-12', 'Направление','Корректировки']],
        on=['Наименование груза ЦО-12', 'Направление'],
        how='left'
    )

    ###
    Sum_model_T = data_input["Новый тариф (после выпадения)"].sum()
    Sum_model_D = data_input["Доходный куб"].sum()

    data_input["percent"] = data_input["Новый тариф (после выпадения)"] / \
                            data_input["Доходный куб"]
    data_input["percent_show"] = data_input["percent"] * 100
    data_input["percent_show"] -= 100
    data_input["percent_show"] = data_input["percent_show"].round(1)
    # data_input["Новый тариф (после выпадения)_SHOW"] = data_input["Новый тариф (после выпадения)"].round(1)
    data_input["Новый тариф (R)"] = data_input["Новый тариф (после выпадения)"].apply(
        str) + " (" + data_input["percent_show"].apply(str) + "%)"
    data_input["нов_percent1"] = data_input["percent"]
    data_input["нов_percent1"] -= 100
    data_input["нов_percent_show"] = data_input["нов_percent1"].round(1)
    data_input["Дифференцированный тариф (R)"] = data_input["Новый тариф (после выпадения)"].apply(
        str) + " (" + data_input["нов_percent_show"].apply(str) + "%)"
    # data_input["Корректировки"] = 0
    data_input["Дельта"] = 0
    data_input["Индекс приведения"] = 1
    data_show = data_input[
        ["Наименование груза ЦО-12","Направление", "Новый тариф (R)", "Корректировки", ]]
    data_show_new = data_input[["Дифференцированный тариф (R)", "Дельта","Индекс приведения"]]
    computed_df = pandas.DataFrame()
    return html.Div([
        html.Div("Вносятся корректировочные значения в столбец Корректировки которые влияют на рентабельность.",style={'textAlign': 'left', 'color': 'black', 'fontSize': 16}),
        html.Div(dash_table.DataTable(id = "table",data= data_show.to_dict("records"),columns = [{"name":i, "id":i} for i in data_show.columns],editable=True),
                                    style={'display': 'flex', 'width': '800px','display': 'inline-block', 'vertical-align': 'top', }),
        html.Div(dash_table.DataTable(id = "table_out",data =data_show_new.to_dict("records"),columns = [{"name":i, "id":i} for i in data_show_new.columns],),
                                    style={'display': 'flex', 'width': '400px','display': 'inline-block', 'vertical-align': 'top', }),

    ])





@callback(Output(component_id = "table_out", component_property = "data"),
          Input(component_id = "table", component_property = "data"),
          Input(component_id = "table", component_property = "columns"),)
def update_output(data_in, columns_in):
    df = pandas.DataFrame(data_in, columns=[c['name'] for c in columns_in])
    data_input["Корректировки"] = df["Корректировки"]
    df = data_input
    # "Корректировки"
    df["Корректировки"] =df["Корректировки"].astype("float64")
    df["нов_percent1"] = df["percent"]+(df["Корректировки"]/100)
    s_new_pereraspr = sum(df["нов_percent1"]*df["Доходный куб"])
    razn = s_new_pereraspr-Sum_model_T
    #count_zero=len(df[(df["Корректировки"]==0)])
    #part_end = (razn/count_zero)*(-1)
    # print(Sum_model_T)
    # print(s_new_pereraspr)
    # print(razn)
    df["Новый тариф (после выпадения)_d"]=df["нов_percent1"]*df["Доходный куб"]
    #df["part_end"] = [part_end if x == 0 else 0 for x in df["Корректировки"]]
    part_sum = df.loc[df["Корректировки"]==0,"Новый тариф (после выпадения)"].sum()
    df.loc[df["Корректировки"] == 0, "part_end_percent"] = df["Новый тариф (после выпадения)"] / part_sum
    # df.loc[df["Корректировки"] == 0, "part_end_percent"] = 0
    df.fillna(0,inplace=True)
    df["part_end"] = df["part_end_percent"]*(razn*(-1))
    # df.to_excel("data/test.xlsx")
    df["Новый тариф (после выпадения)_d"] = df["Новый тариф (после выпадения)_d"]+df["part_end"]
    df["нов_percent1_show_1"] = df["Новый тариф (после выпадения)_d"]/df["Доходный куб"]
    #
    df["Индекс приведения"] = df["Новый тариф (после выпадения)_d"] / df["Новый тариф (после выпадения)"]
    df["Новый тариф (после выпадения)_d"] = df["Новый тариф (после выпадения)_d"].round(1)
    df["нов_percent1_show"] = df["нов_percent1_show_1"]*100
    df["нов_percent1_show"]-=100
    df["нов_percent1_show"] = df["нов_percent1_show"].round(1)
    df["Дифференцированный тариф (R)"] = df["Новый тариф (после выпадения)_d"].apply(str)+" ("+df["нов_percent1_show"].apply(str)+"%)"
    #
    df["сумм_изм"] = df["Новый тариф (после выпадения)_d"]-df["Новый тариф (после выпадения)"]
    df["сумм_изм"] =df["сумм_изм"].round(1)
    df["perceent_изм"] = df["нов_percent1_show_1"]-df["percent"]
    #df["perceent_изм"]-=1
    df["perceent_изм"]*=100
    df["perceent_изм"] =df["perceent_изм"].round(1)
    df["Дельта"] = df["сумм_изм"].apply(str)+" ("+df["perceent_изм"].apply(str)+"%)"

    #
    global computed_df
    computed_df = df.copy()
    export_df = df[["Наименование груза ЦО-12","Направление","Корректировки", "Индекс приведения"]]
    export_df.to_excel("data/new_tariffs.xlsx")
    df = df[["Дифференцированный тариф (R)","Дельта","Индекс приведения"]]
    return df.to_dict("records")

