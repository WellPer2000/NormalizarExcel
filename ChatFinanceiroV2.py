import os
import streamlit as st
from groq import Groq
import pandas as pd

# Set the API key as an environment variable
os.environ["GROQ_API_KEY"] = "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"  # Replace with your Groq API key

# Inicializar o cliente da API
client = Groq()  # O cliente pegará automaticamente a chave de API

# Função para carregar o plano de contas a partir do Google Sheets
def carregar_plano_de_contas_google(link_csv):
    # Ler a planilha diretamente do Google Sheets
    df = pd.read_csv(link_csv)

    # Criar um dicionário estruturado a partir das colunas Categoria, Descrição e DRE
    plano_de_contas = {}
    for _, row in df.iterrows():
        categoria = row['Categoria']
        descricao = row['Descrição']
        dre = row['DRE']

        # Montar a estrutura hierárquica com a categoria e descrição
        if categoria not in plano_de_contas:
            plano_de_contas[categoria] = []
        
        # Adicionar a descrição e o DRE correspondente
        plano_de_contas[categoria].append((descricao, dre))

    return plano_de_contas

#Função para formatar o plano de contas para o conteúdo de preferências com limitação
def formatar_plano_de_contas(plano, max_contas=10):
    conteudo = ""
    contas_processadas = 0
    
    # Iterar pelas categorias no plano de contas
    for categoria, contas in plano.items():
        conteudo += f"**Categoria: {categoria}**\n"
        
        # Iterar pelas contas dentro de uma categoria
        for descricao, dre in contas:
            # Cada conta é formatada com o código DRE e descrição, com base na categoria
            conteudo += f"  - **{dre}**: {descricao} (Aceita lançamento)\n"
            contas_processadas += 1
            
            # Limitar o número de contas processadas
            if contas_processadas >= max_contas:
                break
        
        # Parar de processar mais categorias após o limite
        if contas_processadas >= max_contas:
            break
            
    return conteudo

# URL para exportação CSV do Google Sheets
link_google_sheet_csv = 'https://docs.google.com/spreadsheets/d/1S0DMufjJo-4rEOpdCmoDrTuAIl3THcz6iiWPpro3ySc/export?format=csv'
plano_de_contas = carregar_plano_de_contas_google(link_google_sheet_csv)

# Geração das preferências de conteúdo usando o plano de contas formatado
preferencias_conteudo = f"""
Função: Você atuará como especialista financeiro com foco na conciliação de contas bancárias, auxiliando na categorização de transações.

Regras e Diretrizes:
Identificação e Sugestão de Categoria:

Sempre analise a coluna "Descrição" para identificar o contexto da transação.
Retorne a categoria que melhor representa o contexto identificado.
Em situações onde a categoria exata não seja clara, escolha a que mais se aproxima e informe que se trata de uma sugestão aproximada.
Especificidade:

Priorize sempre a categoria mais específica disponível no plano de contas.
Caso tenha dúvidas sobre a especificidade da categoria, pergunte ao usuário por mais detalhes sobre o contexto da transação antes de sugerir uma categoria.

Sempre informar uam conta na coluna categoria, a que mais se assemelhar com a despesa pegando o contexto da coluna descrição, mesmo quando perguntar contexto quero q fale uma categoria possivel, sempre falar categoria mas perguntando se esta certo e pedindo o contexto

Validação e Confirmação:

Oriente o usuário a utilizar sempre uma categoria existente. Se a categoria ideal não estiver clara, explique o motivo da escolha e reafirme que a sugestão é a mais adequada conforme o contexto fornecido.

Plano de Contas:
{formatar_plano_de_contas(plano_de_contas)}
"""

# Inicializar o histórico e outros estados de sessão, se necessário
if "historico" not in st.session_state:
    st.session_state.historico = []
if 'input' not in st.session_state:
    st.session_state.input = ''
if 'ultima_resposta' not in st.session_state:
    st.session_state.ultima_resposta = ''

# Função para enviar a pergunta e receber a resposta
def send_question(question):
    usuario_nome = "Nome do Usuário"  # Defina o nome do usuário ou passe dinamicamente, se preferir
    
    # Adicionar a pergunta do usuário ao histórico
    st.session_state.historico.append({"role": "user", "content": question})
    
    # Criar uma mensagem de contexto com as preferências e o nome do usuário
    mensagens = [{"role": "system", "content": f"Você está atendendo o usuário {usuario_nome}. Considere as seguintes preferências: {preferencias_conteudo}."}]
    mensagens.extend(st.session_state.historico)  # Adiciona o histórico de mensagens anterior

    # Chamar a API da IA com o histórico e contexto personalizado
    chat_completion = client.chat.completions.create(
        messages=mensagens,
        model="llama3-groq-70b-8192-tool-use-preview",
    )

    # Obter a resposta da IA e armazenar no histórico e em `ultima_resposta`
    resposta = chat_completion.choices[0].message.content
    st.session_state.historico.append({"role": "assistant", "content": resposta})
    st.session_state.ultima_resposta = resposta  # Armazena a última resposta para exibição direta

# Configuração da interface do Streamlit
st.set_page_config(page_title="Chat com IA", layout="wide")
st.title("Chat Financeiro LocalRental - Conciliação Bancaria")

# Campo de entrada e botão de envio
col1, col2 = st.columns([4, 1])  # Criar duas colunas: uma para o campo e outra para o botão

# Campo de entrada
with col1:
    pergunta = st.text_input("Digite sua pergunta:", 
                             value=st.session_state.input,
                             placeholder="Escreva sua mensagem aqui...", 
                             label_visibility="collapsed")

# Botão de envio
with col2:
    if st.button("Enviar"):
        if pergunta:  # Verificar se a pergunta não está vazia
            send_question(pergunta)  # Obter a resposta da IA
            st.session_state.input = ""  # Limpa o campo de entrada após enviar

# Exibir a última resposta abaixo da área de entrada
if 'ultima_resposta' in st.session_state and st.session_state.ultima_resposta:
    st.write("### Resposta da IA")
    st.markdown(f"<div style='text-align: left; background-color: #d4d4d4; padding: 5px; border-radius: 10px; margin: 2px 0; display: inline-block; max-width: 70%; color: black;'><b>IA:</b> {st.session_state.ultima_resposta}</div>", unsafe_allow_html=True)

# Exibir o histórico de conversas completo abaixo da última resposta
st.write("### Histórico Completo de Conversas")
for mensagem in st.session_state.historico:
    if mensagem["role"] == "user":
        st.markdown(f"<div style='text-align: right; background-color: #e1ffc7; padding: 5px; border-radius: 10px; margin: 2px 0; display: inline-block; max-width: 70%; color: black;'><b>Você:</b> {mensagem['content']}</div>", unsafe_allow_html=True)
    elif mensagem["role"] == "assistant":
        st.markdown(f"<div style='text-align: left; background-color: #d4d4d4; padding: 5px; border-radius: 10px; margin: 2px 0; display: inline-block; max-width: 70%; color: black;'><b>IA:</b> {mensagem['content']}</div>", unsafe_allow_html=True)

# Adiciona estilo opcional para melhorar a interface
st.markdown("""
<style>
body {
    background-color: #f0f0f0;  /* Fundo claro para dar um aspecto moderno */
}
div {
    padding: 5px;  /* Reduz o espaço entre as mensagens */
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)
