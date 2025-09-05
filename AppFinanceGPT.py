import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json
import pandas as pd
import hashlib
import os
import plotly.express as px
from streamlit_option_menu import option_menu

# --- CONFIGURAÇÃO DA PÁGINA E TÍTULO ---
st.set_page_config(page_title="Assistente Financeiro com Gemini", layout="wide")

# --- GERENCIAMENTO DE USUÁRIOS ---
USERS_FILE = "users.json"

def load_users():
    """Carrega os dados dos usuários do arquivo JSON."""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users_data):
    """Salva os dados dos usuários no arquivo JSON."""
    with open(USERS_FILE, 'w') as f:
        json.dump(users_data, f, indent=4)

def hash_password(password):
    """Cria um hash seguro para a senha."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_hash, provided_password):
    """Verifica se a senha fornecida corresponde ao hash armazenado."""
    return stored_hash == hash_password(provided_password)

# --- FUNÇÕES AUXILIARES DA APLICAÇÃO ---
def get_worksheet(worksheet_name):
    """Acessa uma aba específica da planilha."""
    try:
        if 'gspread_client' not in st.session_state or 'sheet_name' not in st.session_state:
            st.error("As configurações da planilha não foram carregadas. Salve-as na barra lateral.")
            return None
        spreadsheet = st.session_state.gspread_client.open(st.session_state.sheet_name)
        worksheet = spreadsheet.worksheet(worksheet_name)
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Planilha '{st.session_state.sheet_name}' não encontrada. Verifique o nome na barra lateral.")
        return None
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Aba '{worksheet_name}' não encontrada na planilha!")
        return None
    except Exception as e:
        st.error(f"Erro ao acessar a planilha: {e}")
        return None

@st.cache_data(ttl=600)
def get_all_records(_gspread_client, sheet_name, worksheet_name, expected_cols=None):
    """Pega todos os registros de uma aba, exceto o cabeçalho, garantindo o número correto de colunas."""
    try:
        spreadsheet = _gspread_client.open(sheet_name)
        worksheet = spreadsheet.worksheet(worksheet_name)
        records = worksheet.get_all_values()

        # Garante que pegamos apenas o número esperado de colunas para evitar erros
        if expected_cols:
            processed_rows = [row[:expected_cols] for row in records[1:]]
        else:
            processed_rows = records[1:]

        # Adiciona um ID único para cada linha para facilitar a edição/exclusão
        records_with_id = [[i + 1] + row for i, row in enumerate(processed_rows)]
        return records_with_id if len(records) > 1 else []
    except Exception as e:
        st.toast(f"Não foi possível carregar dados da aba '{worksheet_name}'. Erro: {e}")
        return []

# --- FERRAMENTAS PARA O MODELO GEMINI ---
def add_transaction(value: float, category: str, bank: str, description: str, transaction_type: str, date: str = None):
    """Registra uma transação (receita ou despesa). transaction_type deve ser 'receita' ou 'despesa'."""
    if not date:
        return "A data não foi fornecida. Pergunte ao usuário se a transação foi hoje ou em qual data específica."
    try:
        formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return "O formato da data parece inválido. Peça ao usuário a data no formato AAAA-MM-DD."
    
    saldos_records = get_all_records(st.session_state.gspread_client, st.session_state.sheet_name, "Saldos", expected_cols=3)
    all_categories = get_all_records(st.session_state.gspread_client, st.session_state.sheet_name, "Categorias", expected_cols=1)

    banks = [record[2].lower() for record in saldos_records if len(record) > 2]
    pretty_banks = [record[2] for record in saldos_records if len(record) > 2]
    if bank.lower() not in banks:
        return f"O banco '{bank}' não foi encontrado. Os bancos disponíveis são: {', '.join(pretty_banks)}. Pergunte ao usuário se ele quis dizer um desses ou se deseja cadastrar um novo saldo."

    categories = [item[1].lower() for item in all_categories if len(item) > 1]
    pretty_categories = [item[1] for item in all_categories if len(item) > 1]
    if category.lower() not in categories:
        return f"A categoria '{category}' não está cadastrada. As categorias existentes são: {', '.join(pretty_categories)}. Pergunte ao usuário se ele quis dizer uma dessas ou se deseja cadastrar uma nova."
    
    final_value = -abs(value) if transaction_type.lower() == 'despesa' else abs(value)

    try:
        worksheet = get_worksheet("Lançamentos")
        if worksheet:
            original_bank_name = next((rec[2] for rec in saldos_records if len(rec) > 2 and rec[2].lower() == bank.lower()), bank)
            original_category_name = next((cat[1] for cat in all_categories if len(cat) > 1 and cat[1].lower() == category.lower()), category)
            worksheet.append_row([formatted_date, original_bank_name, final_value, original_category_name, description])
            st.cache_data.clear()
            return f"Sucesso! Transação registrada: Data: {formatted_date}, Valor: R${final_value:.2f}, Categoria: {original_category_name}, Banco: {original_bank_name}, Descrição: {description}."
    except Exception as e:
        return f"Falha ao registrar transação: {e}"
    return "Erro: Não foi possível acessar a planilha de Lançamentos."

def add_transfer(value: float, source_bank: str, destination_bank: str, date: str = None):
    """Registra uma transferência entre dois bancos."""
    if not date:
        return "A data não foi fornecida. Pergunte ao usuário se a transação foi hoje ou em qual data específica."
    try:
        formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return "O formato da data parece inválido. Peça ao usuário a data no formato AAAA-MM-DD."

    saldos_records = get_all_records(st.session_state.gspread_client, st.session_state.sheet_name, "Saldos", expected_cols=3)
    banks = [record[2].lower() for record in saldos_records if len(record) > 2]
    pretty_banks = [record[2] for record in saldos_records if len(record) > 2]

    if source_bank.lower() not in banks:
        return f"O banco de origem '{source_bank}' não foi encontrado. Os bancos disponíveis são: {', '.join(pretty_banks)}."
    if destination_bank.lower() not in banks:
        return f"O banco de destino '{destination_bank}' não foi encontrado. Os bancos disponíveis são: {', '.join(pretty_banks)}."

    all_categories = get_all_records(st.session_state.gspread_client, st.session_state.sheet_name, "Categorias", expected_cols=1)
    categories = [item[1].lower() for item in all_categories if len(item) > 1]
    transfer_category_name = "Transferencia entre contas"
    
    if transfer_category_name.lower() not in categories:
        return f"A categoria '{transfer_category_name}' é necessária para transferências e não foi encontrada. Pergunte ao usuário se ele deseja criá-la."
    
    try:
        worksheet = get_worksheet("Lançamentos")
        if worksheet:
            original_source_bank = next((rec[2] for rec in saldos_records if len(rec) > 2 and rec[2].lower() == source_bank.lower()), source_bank)
            original_destination_bank = next((rec[2] for rec in saldos_records if len(rec) > 2 and rec[2].lower() == destination_bank.lower()), destination_bank)
            
            worksheet.append_row([formatted_date, original_source_bank, -abs(value), transfer_category_name, f"Transferência para {original_destination_bank}"])
            worksheet.append_row([formatted_date, original_destination_bank, abs(value), transfer_category_name, f"Transferência de {original_source_bank}"])
            
            st.cache_data.clear()
            return f"Sucesso! Transferência de R${abs(value):.2f} de {original_source_bank} para {original_destination_bank} registrada."
    except Exception as e:
        return f"Falha ao registrar transferência: {e}"
    return "Erro: Não foi possível acessar a planilha de Lançamentos."

def delete_transaction(description: str, date: str):
    """Exclui uma transação com base na descrição e data."""
    try:
        worksheet = get_worksheet("Lançamentos")
        if not worksheet: return "Não foi possível acessar a planilha de lançamentos."
        
        records = worksheet.get_all_values()
        rows = records[1:]
        
        try:
            search_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return "O formato da data é inválido. Peça ao usuário a data no formato AAAA-MM-DD."

        found_rows = []
        for i, row in enumerate(rows):
            if len(row) > 4 and row[0] == search_date and description.lower() in row[4].lower():
                found_rows.append((i + 2, row)) # +2 para a linha correta na planilha (1-based e header)
        
        if len(found_rows) == 0:
            return f"Nenhuma transação encontrada com a descrição '{description}' na data {search_date}."
        if len(found_rows) > 1:
            return "Múltiplas transações encontradas. Peça ao usuário para ser mais específico, talvez adicionando o valor."
            
        row_to_delete_index, row_data = found_rows[0]
        worksheet.delete_rows(row_to_delete_index)
        st.cache_data.clear()
        return f"Transação '{row_data[4]}' no valor de R${row_data[2]} do dia {row_data[0]} foi excluída com sucesso."

    except Exception as e:
        return f"Ocorreu um erro ao tentar excluir a transação: {e}"

def add_category(category_name: str):
    try:
        worksheet = get_worksheet("Categorias")
        if worksheet:
            worksheet.append_row([category_name.capitalize()])
            st.cache_data.clear()
            return f"Sucesso! Nova categoria '{category_name.capitalize()}' foi adicionada."
    except Exception as e:
        return f"Falha ao adicionar categoria: {e}"

def add_initial_balance(bank: str, value: float, start_date: str):
    try:
        worksheet = get_worksheet("Saldos")
        if worksheet:
            formatted_date = datetime.strptime(start_date, "%Y-%m-%d").strftime("%d/%m/%Y")
            worksheet.append_row([formatted_date, bank, value])
            st.cache_data.clear()
            return f"Sucesso! Saldo inicial de R${value} para o novo banco '{bank}' registrado com data de {formatted_date}."
    except Exception as e:
        return f"Falha ao registrar saldo inicial: {e}"

@st.cache_data(ttl=900)
def generate_financial_summary(_df_lancamentos):
    """Gera um resumo financeiro usando a IA do Gemini."""
    if _df_lancamentos.empty:
        return "Não há dados de lançamentos suficientes para gerar uma análise."
    df_json = _df_lancamentos.to_json(orient='records', date_format='iso')
    try:
        model = genai.GenerativeModel(model_name="gemini-2.5-flash-preview-05-20")
        prompt = f"""
        Você é um consultor financeiro sênior. Baseado nos seguintes dados de transações (JSON), gere uma análise detalhada da situação financeira do usuário para este período.

        **Formato da Resposta (Obrigatório em Markdown):**
        
        ### 📊 Panorama Geral
        - **Balanço do Período:** (Ex: "Superávit de R$ XXX,XX" ou "Déficit de R$ XXX,XX").
        - **Receitas Totais:** R$ XXX,XX.
        - **Despesas Totais:** R$ XXX,XX.
        - **Comentário:** Uma breve frase sobre o resultado (ex: "Você terminou o período com um resultado positivo, parabéns!").

        ### 💸 Análise de Despesas
        Identifique as 3 principais categorias de despesas em uma lista com marcadores, mencionando o valor gasto em cada uma e um breve comentário.
        - **Nome da Categoria 1:** R$ XXX,XX - (breve comentário).
        - **Nome da Categoria 2:** R$ XXX,XX - (breve comentário).
        - **Nome da Categoria 3:** R$ XXX,XX - (breve comentário).

        ### 💡 Recomendação Estratégica
        Ofereça uma dica prática e acionável com base na análise. Se o balanço for negativo, sugira uma área para economizar. Se for positivo, sugira como otimizar o excedente (investir, reserva de emergência, etc.).

        **Instruções Adicionais:**
        - Fale diretamente com o usuário ("Você", "Seus gastos...").
        - Use negrito (`**texto**`) para destacar os termos mais importantes.
        - A resposta deve ser em português.

        Dados: {df_json}
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Não foi possível gerar a análise: {e}"

# --- PÁGINAS DA APLICAÇÃO ---

def chat_page():
    st.title("💬 Chat com Assistente Financeiro")
    st.caption("Faça perguntas ou peça para registrar/excluir transações ou transferências.")

    tools = {
        "add_transaction": add_transaction, "add_category": add_category,
        "add_initial_balance": add_initial_balance, "delete_transaction": delete_transaction,
        "add_transfer": add_transfer
    }
    SYSTEM_PROMPT = """
    Você é um assistente financeiro inteligente.
    **Regras Principais:**
    1.  **Tipo de Transação:** Ao usar `add_transaction`, você DEVE definir o `transaction_type`. Use 'despesa' para gastos, compras, saídas, etc. Use 'receita' para salários, entradas, recebimentos, etc.
    2.  **Descrição Automática:** Gere o parâmetro `description` a partir do pedido do usuário.
    3.  **Interpretação Flexível:** Corresponda nomes de bancos e categorias mesmo com erros de digitação.
    4.  **Fluxo de Correção:** Se uma ferramenta retornar erro de item não encontrado, apresente as opções válidas ao usuário e pergunte qual ele quis dizer. Se ele confirmar, chame a ferramenta de novo com o nome correto.
    5.  **Exclusão:** Para excluir, você precisa da descrição e da data. Se o usuário não fornecer a data, pergunte a ele.
    6.  **Transferências:** Se o usuário falar em "transferir", "enviar dinheiro de um banco para outro", etc., use a função `add_transfer`. Você precisa de um banco de origem (`source_bank`), um de destino (`destination_bank`), e o valor. Se a função `add_transfer` falhar porque a categoria 'Transferencia entre contas' não existe, pergunte ao usuário se ele deseja criar essa categoria. Se sim, use a função `add_category`.
    """
    model = genai.GenerativeModel(model_name="gemini-2.5-flash-preview-05-20", tools=tools.values(), system_instruction=SYSTEM_PROMPT)
    
    if "chat" not in st.session_state:
        today = datetime.now().strftime('%Y-%m-%d')
        st.session_state.chat = model.start_chat(history=[{"role": "user", "parts": [{"text": f"Hoje é {today}."}]}, {"role": "model", "parts": [{"text": f"Entendido! Hoje é {today}. Estou pronto."}]}])
    
    for message in st.session_state.chat.history:
        if message.role in ["user", "model"] and not (hasattr(message.parts[0], 'function_call') and message.parts[0].function_call):
             with st.chat_message("human" if message.role == "user" else "ai"): st.markdown(message.parts[0].text)
    
    if prompt := st.chat_input("Como posso ajudar?"):
        with st.chat_message("human"): st.markdown(prompt)
        response = st.session_state.chat.send_message(prompt)
        if response.parts and hasattr(response.parts[0], 'function_call'):
            fc = response.parts[0].function_call
            tool_function = tools.get(fc.name)
            if tool_function:
                args = {key: value for key, value in fc.args.items()}
                function_response = tool_function(**args)
                response = st.session_state.chat.send_message([{"function_response": {"name": fc.name, "response": {"content": function_response}}}])
        if response.parts:
            with st.chat_message("ai"): st.markdown(response.parts[0].text)
        else:
            with st.chat_message("ai"): st.markdown("Não consegui processar. Tente de novo.")

def dashboard_page():
    st.title("📊 Dashboard Financeiro")
    st.caption("Um resumo visual da sua situação financeira.")
    
    lancamentos_data = get_all_records(st.session_state.gspread_client, st.session_state.sheet_name, "Lançamentos", expected_cols=5)
    saldos_data = get_all_records(st.session_state.gspread_client, st.session_state.sheet_name, "Saldos", expected_cols=3)
    
    if not lancamentos_data:
        st.info("Ainda não há lançamentos para exibir no dashboard.")
        return
        
    df_lancamentos = pd.DataFrame(lancamentos_data, columns=['ID', 'Data', 'Banco', 'Valor', 'Categoria', 'Descrição'])
    df_saldos = pd.DataFrame(saldos_data, columns=['ID', 'Data Inicial', 'Banco', 'Valor'])
    
    # --- Limpeza e Conversão ---
    df_lancamentos['Valor'] = pd.to_numeric(df_lancamentos['Valor'].astype(str).str.replace(',', '.', regex=False), errors='coerce')
    df_lancamentos['Data'] = pd.to_datetime(df_lancamentos['Data'], format='%d/%m/%Y', errors='coerce')
    df_lancamentos.dropna(subset=['Valor', 'Data'], inplace=True)
    df_saldos['Valor'] = pd.to_numeric(df_saldos['Valor'].astype(str).str.replace(',', '.', regex=False), errors='coerce')
    
    # --- Filtros de Ano e Mês ---
    df_lancamentos['Ano'] = df_lancamentos['Data'].dt.year
    df_lancamentos['Mês'] = df_lancamentos['Data'].dt.month
    
    anos_disponiveis = sorted(df_lancamentos['Ano'].unique(), reverse=True)
    meses_nomes = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
    
    col1_filter, col2_filter = st.columns(2)
    ano_selecionado = col1_filter.selectbox("Filtrar por Ano:", ["Todos"] + anos_disponiveis)
    
    meses_disponiveis_nomes = {}
    if ano_selecionado != "Todos":
        meses_no_ano = sorted(df_lancamentos[df_lancamentos['Ano'] == ano_selecionado]['Mês'].unique())
        meses_disponiveis_nomes = {m: meses_nomes[m] for m in meses_no_ano}
        mes_selecionado_nome = col2_filter.selectbox("Filtrar por Mês:", ["Todos"] + list(meses_disponiveis_nomes.values()))
    else:
        mes_selecionado_nome = col2_filter.selectbox("Filtrar por Mês:", ["Todos"], disabled=True)

    # --- Aplicação dos Filtros ---
    df_filtrado_com_transferencias = df_lancamentos.copy()
    if ano_selecionado != "Todos":
        df_filtrado_com_transferencias = df_filtrado_com_transferencias[df_filtrado_com_transferencias['Ano'] == ano_selecionado]
    if mes_selecionado_nome != "Todos":
        mes_num = [k for k, v in meses_disponiveis_nomes.items() if v == mes_selecionado_nome][0]
        df_filtrado_com_transferencias = df_filtrado_com_transferencias[df_filtrado_com_transferencias['Mês'] == mes_num]
    
    # --- Dataframe para Análise (excluindo transferências) ---
    df_analise = df_filtrado_com_transferencias[
        df_filtrado_com_transferencias['Categoria'].str.lower() != 'transferencia entre contas'
    ].copy()

    # --- Métricas (usando df_analise) ---
    total_receitas = df_analise[df_analise['Valor'] > 0]['Valor'].sum()
    total_despesas = df_analise[df_analise['Valor'] < 0]['Valor'].sum()
    balanco = total_receitas + total_despesas
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Receitas no Período", f"R$ {total_receitas:,.2f}")
    col2.metric("Despesas no Período", f"R$ {total_despesas:,.2f}")
    col3.metric("Balanço do Período", f"R$ {balanco:,.2f}", delta=f"{balanco:,.2f}")

    st.markdown("---")

    # --- Saldo por Banco em Tabela (usando df_filtrado_com_transferencias) ---
    st.subheader("Resumo por Banco no Período")
    if not df_saldos.empty:
        receitas_por_banco = df_filtrado_com_transferencias[df_filtrado_com_transferencias['Valor'] > 0].groupby('Banco')['Valor'].sum().reset_index().rename(columns={'Valor': 'Receitas'})
        despesas_por_banco = df_filtrado_com_transferencias[df_filtrado_com_transferencias['Valor'] < 0].groupby('Banco')['Valor'].sum().reset_index().rename(columns={'Valor': 'Despesas'})
        
        df_resumo_bancos = df_saldos[['Banco', 'Valor']].copy()
        df_resumo_bancos.rename(columns={'Valor': 'Saldo Anterior'}, inplace=True)
        
        df_resumo_bancos = pd.merge(df_resumo_bancos, receitas_por_banco, on='Banco', how='left')
        df_resumo_bancos = pd.merge(df_resumo_bancos, despesas_por_banco, on='Banco', how='left')
        
        df_resumo_bancos[['Receitas', 'Despesas']] = df_resumo_bancos[['Receitas', 'Despesas']].fillna(0)
        
        df_resumo_bancos['Saldo Atual'] = df_resumo_bancos['Saldo Anterior'] + df_resumo_bancos['Receitas'] + df_resumo_bancos['Despesas']
        
        # Adicionar linha de total
        total_row = pd.DataFrame({
            'Banco': ['**Total**'],
            'Saldo Anterior': [df_resumo_bancos['Saldo Anterior'].sum()],
            'Receitas': [df_resumo_bancos['Receitas'].sum()],
            'Despesas': [df_resumo_bancos['Despesas'].sum()],
            'Saldo Atual': [df_resumo_bancos['Saldo Atual'].sum()]
        })
        df_resumo_bancos = pd.concat([df_resumo_bancos, total_row], ignore_index=True)

        st.dataframe(
            df_resumo_bancos,
            column_config={
                "Banco": st.column_config.TextColumn("Banco"),
                "Saldo Anterior": st.column_config.NumberColumn("Saldo Anterior", format="R$ %.2f"),
                "Receitas": st.column_config.NumberColumn("Receitas", format="R$ %.2f"),
                "Despesas": st.column_config.NumberColumn("Despesas", format="R$ %.2f"),
                "Saldo Atual": st.column_config.NumberColumn("Saldo Atual", format="R$ %.2f"),
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.warning("Cadastre o saldo inicial dos seus bancos para ver o resumo aqui.")

    st.markdown("---")
    
    # --- Análise da IA (usando df_analise) ---
    st.subheader("Análise da IA para o período selecionado")
    if st.button("Gerar Análise com IA"):
        with st.spinner("Analisando seus dados..."):
            resumo = generate_financial_summary(df_analise)
            with st.container(border=True):
                st.markdown(resumo)
    
    # --- Gráficos (usando df_analise) ---
    if not df_analise.empty:
        df_despesas = df_analise[df_analise['Valor'] < 0].copy()
        if not df_despesas.empty:
            df_despesas['Valor'] = df_despesas['Valor'].abs()
            despesas_por_categoria = df_despesas.groupby('Categoria')['Valor'].sum().sort_values(ascending=False).reset_index()

            col1_graph, col2_graph = st.columns(2)
            with col1_graph:
                st.subheader("Despesas por Categoria")
                fig_bar = px.bar(despesas_por_categoria, x='Categoria', y='Valor', text_auto='.2s', height=400)
                st.plotly_chart(fig_bar, use_container_width=True)
            with col2_graph:
                st.subheader("Distribuição de Gastos")
                fig_pie = px.pie(despesas_por_categoria, names='Categoria', values='Valor', height=400)
                st.plotly_chart(fig_pie, use_container_width=True)
        
        st.subheader("Últimos Lançamentos no Período")
        st.dataframe(df_filtrado_com_transferencias[['Data', 'Banco', 'Valor', 'Categoria', 'Descrição']].tail(10), use_container_width=True, hide_index=True)

def lancamentos_page():
    st.title("✍️ Gerenciar Lançamentos")
    st.caption("Visualize, filtre e edite suas transações.")

    worksheet = get_worksheet("Lançamentos")
    if not worksheet:
        st.error("Não foi possível carregar a aba de Lançamentos.")
        return

    lancamentos_data = get_all_records(st.session_state.gspread_client, st.session_state.sheet_name, "Lançamentos", expected_cols=5)
    if not lancamentos_data:
        st.info("Você ainda não possui lançamentos.")
        return

    df_lancamentos = pd.DataFrame(lancamentos_data, columns=['ID', 'Data', 'Banco', 'Valor', 'Categoria', 'Descrição'])
    
    df_lancamentos['Valor'] = pd.to_numeric(df_lancamentos['Valor'].astype(str).str.replace(',', '.', regex=False), errors='coerce').fillna(0.0)

    # --- Filtros ---
    col1, col2, col3 = st.columns(3)
    bancos = ["Todos"] + sorted(list(df_lancamentos['Banco'].unique()))
    categorias = ["Todos"] + sorted(list(df_lancamentos['Categoria'].unique()))
    
    banco_filtro = col1.selectbox("Filtrar por Banco", bancos)
    categoria_filtro = col2.selectbox("Filtrar por Categoria", categorias)
    descricao_filtro = col3.text_input("Buscar por Descrição")
    
    df_filtrado = df_lancamentos.copy()
    if banco_filtro != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Banco'] == banco_filtro]
    if categoria_filtro != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Categoria'] == categoria_filtro]
    if descricao_filtro:
        df_filtrado = df_filtrado[df_filtrado['Descrição'].str.contains(descricao_filtro, case=False, na=False)]

    st.info(f"Exibindo {len(df_filtrado)} de {len(df_lancamentos)} lançamentos.")
    
    # --- Diálogo de Edição ---
    if 'edit_id' in st.session_state and st.session_state.edit_id is not None:
        edit_id = st.session_state.edit_id
        transaction_to_edit = df_lancamentos[df_lancamentos['ID'] == edit_id].iloc[0]

        @st.dialog("Editar Lançamento")
        def edit_form():
            saldos_records = get_all_records(st.session_state.gspread_client, st.session_state.sheet_name, "Saldos", expected_cols=3)
            all_categories = get_all_records(st.session_state.gspread_client, st.session_state.sheet_name, "Categorias", expected_cols=1)
            bank_list = sorted([rec[2] for rec in saldos_records if len(rec) > 2])
            category_list = sorted([cat[1] for cat in all_categories if len(cat) > 1])
            
            try: current_bank_index = bank_list.index(transaction_to_edit['Banco'])
            except ValueError: current_bank_index = 0
            try: current_category_index = category_list.index(transaction_to_edit['Categoria'])
            except ValueError: current_category_index = 0
            
            with st.form("edit_form_modal"):
                current_date = datetime.strptime(transaction_to_edit['Data'], '%d/%m/%Y')
                new_date = st.date_input("Data", value=current_date)
                new_bank = st.selectbox("Banco", bank_list, index=current_bank_index)
                new_value = st.number_input("Valor", value=float(transaction_to_edit['Valor']), format="%.2f")
                new_category = st.selectbox("Categoria", category_list, index=current_category_index)
                new_description = st.text_input("Descrição", value=transaction_to_edit['Descrição'])
                
                if st.form_submit_button("Salvar Alterações", type="primary"):
                    worksheet = get_worksheet("Lançamentos")
                    updated_row_data = [
                        new_date.strftime('%d/%m/%Y'), new_bank, new_value,
                        new_category, new_description
                    ]
                    worksheet.update(f'A{edit_id + 1}:E{edit_id + 1}', [updated_row_data])
                    st.cache_data.clear()
                    st.session_state.edit_id = None
                    st.rerun()
        
        edit_form()

    # --- Exibição dos Lançamentos com Botões ---
    header_cols = st.columns((2, 2, 1.5, 2, 4, 1.5))
    headers = ['Data', 'Banco', 'Valor', 'Categoria', 'Descrição', 'Ações']
    for col, header in zip(header_cols, headers):
        col.markdown(f"**{header}**")
    
    st.markdown("---")

    for index, row in df_filtrado.iterrows():
        col1, col2, col3, col4, col5, col6 = st.columns((2, 2, 1.5, 2, 4, 1.5))
        col1.text(row['Data'])
        col2.text(row['Banco'])
        col3.text(f"R$ {float(row['Valor']):.2f}")
        col4.text(row['Categoria'])
        col5.text(row['Descrição'])
        
        with col6:
            action_cols = st.columns(2)
            if action_cols[0].button("✏️", key=f"edit_{row['ID']}", help="Editar Lançamento"):
                st.session_state.edit_id = row['ID']
                st.rerun()

            popover = action_cols[1].popover("🗑️", help="Excluir Lançamento")
            if popover.button("Confirmar Exclusão", key=f"delete_{row['ID']}", type="primary"):
                worksheet = get_worksheet("Lançamentos")
                worksheet.delete_rows(row['ID'] + 1)
                st.cache_data.clear()
                st.rerun()

def cadastros_page():
    st.title("🗂️ Gerenciar Cadastros")
    st.caption("Edite ou exclua seus bancos (saldos) e categorias.")

    tab1, tab2 = st.tabs(["Gerenciar Saldos (Bancos)", "Gerenciar Categorias"])

    with tab1:
        st.subheader("Saldos Iniciais Cadastrados")
        saldos_data = get_all_records(st.session_state.gspread_client, st.session_state.sheet_name, "Saldos", expected_cols=3)
        if not saldos_data:
            st.info("Nenhum saldo inicial cadastrado. Você pode adicionar um pelo chat.")
        else:
            df_saldos = pd.DataFrame(saldos_data, columns=['ID', 'Data Inicial', 'Banco', 'Valor'])
            df_saldos['Valor'] = pd.to_numeric(df_saldos['Valor'].astype(str).str.replace(',', '.', regex=False), errors='coerce').fillna(0.0)

            # --- Diálogo de Edição de Saldo ---
            if 'edit_saldo_id' in st.session_state and st.session_state.edit_saldo_id is not None:
                edit_id = st.session_state.edit_saldo_id
                saldo_to_edit = df_saldos[df_saldos['ID'] == edit_id].iloc[0]
                
                @st.dialog("Editar Saldo Inicial")
                def edit_saldo_form():
                    with st.form("edit_saldo_form_modal"):
                        current_date = datetime.strptime(saldo_to_edit['Data Inicial'], '%d/%m/%Y')
                        new_date = st.date_input("Data Inicial", value=current_date)
                        new_bank = st.text_input("Nome do Banco", value=saldo_to_edit['Banco'])
                        new_value = st.number_input("Valor do Saldo", value=float(saldo_to_edit['Valor']), format="%.2f")
                        
                        if st.form_submit_button("Salvar Alterações", type="primary"):
                            worksheet = get_worksheet("Saldos")
                            updated_row_data = [new_date.strftime('%d/%m/%Y'), new_bank, new_value]
                            worksheet.update(f'A{edit_id + 1}:C{edit_id + 1}', [updated_row_data])
                            st.cache_data.clear()
                            st.session_state.edit_saldo_id = None
                            st.rerun()
                edit_saldo_form()

            # --- Exibição dos Saldos ---
            header_cols = st.columns((2, 3, 2, 1.5))
            headers = ['Data Inicial', 'Banco', 'Valor', 'Ações']
            for col, header in zip(header_cols, headers):
                col.markdown(f"**{header}**")
            st.markdown("---")
            for index, row in df_saldos.iterrows():
                col1, col2, col3, col4 = st.columns((2, 3, 2, 1.5))
                col1.text(row['Data Inicial'])
                col2.text(row['Banco'])
                col3.text(f"R$ {float(row['Valor']):.2f}")
                with col4:
                    action_cols = st.columns(2)
                    if action_cols[0].button("✏️", key=f"edit_saldo_{row['ID']}", help="Editar Saldo"):
                        st.session_state.edit_saldo_id = row['ID']
                        st.rerun()
                    popover = action_cols[1].popover("🗑️", help="Excluir Saldo")
                    if popover.button("Confirmar Exclusão", key=f"delete_saldo_{row['ID']}", type="primary"):
                        worksheet = get_worksheet("Saldos")
                        worksheet.delete_rows(row['ID'] + 1)
                        st.cache_data.clear()
                        st.rerun()

    with tab2:
        st.subheader("Categorias Cadastradas")
        categorias_data = get_all_records(st.session_state.gspread_client, st.session_state.sheet_name, "Categorias", expected_cols=1)
        if not categorias_data:
            st.info("Nenhuma categoria cadastrada. Você pode adicionar uma pelo chat.")
        else:
            df_categorias = pd.DataFrame(categorias_data, columns=['ID', 'Nome da Categoria'])
            
            # --- Diálogo de Edição de Categoria ---
            if 'edit_categoria_id' in st.session_state and st.session_state.edit_categoria_id is not None:
                edit_id = st.session_state.edit_categoria_id
                categoria_to_edit = df_categorias[df_categorias['ID'] == edit_id].iloc[0]

                @st.dialog("Editar Categoria")
                def edit_categoria_form():
                    with st.form("edit_categoria_form_modal"):
                        new_name = st.text_input("Nome da Categoria", value=categoria_to_edit['Nome da Categoria'])
                        if st.form_submit_button("Salvar Alterações", type="primary"):
                            worksheet = get_worksheet("Categorias")
                            worksheet.update_cell(edit_id + 1, 1, new_name)
                            st.cache_data.clear()
                            st.session_state.edit_categoria_id = None
                            st.rerun()
                edit_categoria_form()

            # --- Exibição das Categorias ---
            for index, row in df_categorias.iterrows():
                col1, col2 = st.columns([4, 1])
                col1.text(row['Nome da Categoria'])
                with col2:
                    action_cols = st.columns(2)
                    if action_cols[0].button("✏️", key=f"edit_cat_{row['ID']}", help="Editar Categoria"):
                        st.session_state.edit_categoria_id = row['ID']
                        st.rerun()
                    popover = action_cols[1].popover("🗑️", help="Excluir Categoria")
                    if popover.button("Confirmar Exclusão", key=f"delete_cat_{row['ID']}", type="primary"):
                        worksheet = get_worksheet("Categorias")
                        worksheet.delete_rows(row['ID'] + 1)
                        st.cache_data.clear()
                        st.rerun()

# --- LÓGICA DA APLICAÇÃO PRINCIPAL ---
def main_app():
    with st.sidebar:
        st.header(f"👋 Olá, {st.session_state.username}!")
        
        selected = option_menu(
            menu_title=None,
            options=["Dashboard", "Chat", "Lançamentos", "Cadastros"],
            icons=["house", "chat-dots", "pencil-square", "folder"],
            menu_icon="cast", default_index=0
        )
        
        with st.expander("🔑 Configurações", expanded=False):
            users_data = load_users()
            user_config = users_data.get(st.session_state.username, {})
            google_api_key = st.text_input("Sua Google API Key (Gemini)", value=user_config.get("google_api_key", ""), type="password")
            sheet_name_input = st.text_input("Nome da sua Planilha Google", value=user_config.get("sheet_name", ""))
            creds_json_input = st.text_area("Conteúdo do seu JSON de Credenciais", value=user_config.get("creds_json", ""), height=250)

            if st.button("Salvar Configurações"):
                user_config["google_api_key"] = google_api_key
                user_config["sheet_name"] = sheet_name_input
                user_config["creds_json"] = creds_json_input
                users_data[st.session_state.username] = user_config
                save_users(users_data)
                st.success("Configurações salvas com sucesso!")
                st.rerun()

        if st.button("Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    users_data = load_users()
    user_config = users_data.get(st.session_state.username, {})
    is_configured = user_config.get("google_api_key") and user_config.get("sheet_name") and user_config.get("creds_json")
    
    if is_configured:
        try:
            genai.configure(api_key=user_config["google_api_key"])
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(json.loads(user_config["creds_json"]), scopes=scope)
            st.session_state.gspread_client = gspread.authorize(creds)
            st.session_state.sheet_name = user_config["sheet_name"]
        except Exception as e:
            st.error(f"Erro ao carregar configurações: {e}. Verifique os dados na barra lateral.")
            return
    else:
        st.info("👋 Bem-vindo! Por favor, insira e salve suas configurações no expansor 'Configurações' na barra lateral para começar.")
        return

    if selected == "Dashboard":
        dashboard_page()
    elif selected == "Chat":
        chat_page()
    elif selected == "Lançamentos":
        lancamentos_page()
    elif selected == "Cadastros":
        cadastros_page()


def login_signup_page():
    st.header("Bem-vindo ao seu Assistente Financeiro Pessoal!")
    choice = st.radio("Escolha uma opção:", ('Login', 'Registrar'))
    users_data = load_users()
    with st.form(key=choice):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submit_button = st.form_submit_button(label=choice)
        if submit_button:
            if not username or not password:
                st.error("Por favor, preencha todos os campos.")
                return
            if choice == 'Registrar':
                if username in users_data:
                    st.error("Usuário já existe. Por favor, escolha outro nome ou faça login.")
                else:
                    users_data[username] = {"password_hash": hash_password(password)}
                    save_users(users_data)
                    st.success("Usuário registrado com sucesso! Agora você pode fazer login.")
            elif choice == 'Login':
                user_data = users_data.get(username)
                if user_data and verify_password(user_data.get("password_hash"), password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")

# --- Fluxo principal ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if st.session_state.logged_in:
    main_app()
else:
    login_signup_page()

