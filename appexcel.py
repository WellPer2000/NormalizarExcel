import streamlit as st
import pandas as pd
from io import BytesIO
import os

# Função para normalizar o Excel (remover colunas em branco)
def normalizar_excel(arquivo):
    # Carregar o arquivo Excel para um DataFrame
    df = pd.read_excel(arquivo)

    # Remover colunas que possuem apenas valores NaN (vazios)
    df_normalizado = df.dropna(axis=1, how='all')

    return df_normalizado

# Função para converter DataFrame em arquivo Excel para download
def gerar_excel_para_download(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados Normalizados')
    return output.getvalue()

# Interface Streamlit
st.title("Normalizador de Arquivos Excel")

# Upload do arquivo Excel
arquivo_carregado = st.file_uploader("Envie o arquivo Excel", type=["xlsx"])

if arquivo_carregado:
    # Exibir o arquivo carregado como DataFrame
    #st.write("Arquivo carregado:")
    #df_carregado = pd.read_excel(arquivo_carregado)
    #st.write(df_carregado)

    # Normalizar o Excel (remover colunas vazias)
    df_normalizado = normalizar_excel(arquivo_carregado)

    # Gerar o nome do arquivo convertido
    nome_arquivo_original = arquivo_carregado.name
    nome_arquivo_convertido = os.path.splitext(nome_arquivo_original)[0] + "_convertido.xlsx"

    #Titlo
    st.write("Arquivo após a normalização (remover colunas vazias):")

    # Botão para baixar o arquivo processado
    arquivo_excel_normalizado = gerar_excel_para_download(df_normalizado)
    st.download_button(label="Baixar Excel Normalizado",
                       data=arquivo_excel_normalizado,
                       #file_name="arquivo_normalizado.xlsx",
                       file_name=nome_arquivo_convertido,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # Exibir o DataFrame normalizado
    st.write(df_normalizado)