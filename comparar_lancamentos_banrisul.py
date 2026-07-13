import os
import re
import msal
import requests
import urllib.parse
import pandas as pd
import streamlit as st
import pypdf
import io
import calendar
import unicodedata
from datetime import datetime
from pathlib import Path

# Configuracao da pagina do Streamlit
st.set_page_config(
    page_title="Reconciliação Financeira",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilizacao CSS personalizada para tema escuro e visual premium
st.markdown("""
<style>
    .stButton>button {
        background-color: #38bdf8;
        color: #0f172a;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        border: none;
        font-weight: bold;
        transition: all 0.3s ease;
        width: 100%;
    }
    .stButton>button:hover {
        background-color: #7dd3fc;
        transform: translateY(-2px);
        box-shadow: 0 4px 6px -1px rgba(56, 189, 248, 0.2);
    }
    .card {
        background-color: #1e293b;
        color: #f8fafc;
        padding: 1.25rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1);
        margin-bottom: 1.25rem;
        border: 1px solid #334155;
    }
    .card h3, .card h4 {
        color: #f8fafc !important;
        margin-top: 0;
        margin-bottom: 0.5rem;
    }
    .card p {
        color: #cbd5e1 !important;
        margin-bottom: 0;
    }
    .header-title {
        color: #38bdf8;
        font-size: 2.25rem;
        font-weight: 800;
        margin-bottom: 0.5rem;
    }
    .header-subtitle {
        color: #94a3b8;
        font-size: 1.1rem;
        margin-bottom: 1.5rem;
    }
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

# Funcao para verificar credenciais no st.secrets ou fallback local
def verificar_login(usuario, senha):
    try:
        if "users" in st.secrets:
            users_dict = st.secrets["users"]
            if usuario in users_dict and users_dict[usuario] == senha:
                return True
    except Exception:
        # st.secrets nao esta configurado localmente
        pass
    # Fallback local de seguranca conforme solicitado
    if usuario == "conciliacao" and senha == "Mr130815@":
        return True
    return False

# Inicializacao do estado de login
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

# Tela de login se nao estiver logado
if not st.session_state["logged_in"]:
    col_log1, col_log2, col_log3 = st.columns([1, 2, 1])
    with col_log2:
        st.markdown('<div style="height: 100px;"></div>', unsafe_allow_html=True)
        st.markdown('<div class="card" style="text-align: center;">'
                    '<h3>🔑 Acesso ao Conciliador</h3>'
                    '<p>Digite suas credenciais para acessar o painel</p></div>', unsafe_allow_html=True)
        
        user_input = st.text_input("Usuário:", placeholder="Digite seu usuário")
        password_input = st.text_input("Senha:", type="password", placeholder="Digite sua senha")
        
        if st.button("Entrar"):
            if verificar_login(user_input, password_input):
                st.session_state["logged_in"] = True
                st.success("Login efetuado com sucesso!")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
            else:
                st.error("Usuário ou senha incorretos.")
        st.stop()

# Funcao para carregar variaveis do .env
def carregar_env():
    env_path = Path("c:/Users/wellp/Downloads/Extratores/.env")
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

carregar_env()

# Helper para obter configuracoes do st.secrets (Streamlit Cloud) com fallback para os.environ (.env local)
def obter_config(key, default=None):
    # Tenta st.secrets.get() — funciona para chaves de nivel raiz no Streamlit Cloud
    try:
        val = st.secrets.get(key)
        if val is not None:
            return str(val)
    except Exception:
        pass
    # Tenta acesso direto por atributo (e.g. st.secrets.TENANT_ID)
    try:
        val = getattr(st.secrets, key, None)
        if val is not None:
            return str(val)
    except Exception:
        pass
    # Fallback para variaveis de ambiente (.env local)
    return os.environ.get(key, default)

# Configuracoes do Microsoft Graph
TENANT_ID = obter_config("TENANT_ID") 
CLIENT_ID = obter_config("CLIENT_ID") 
CLIENT_SECRET = obter_config("CLIENT_SECRET")
DRIVE_ID = obter_config("ONEDRIVE_DRIVE_ID")
FOLDER_ID = obter_config("ONEDRIVE_FOLDER_ID")

API_URL = obter_config("API_URL")
API_KEY = obter_config("API_KEY")

# De-Para de Postos (Mapeamento Sistema MR -> Pastas OneDrive)
DE_PARA_POSTOS = {
    "ARARANGUÁ": "Ararangua",
    "BARRA DO TURVO": "São Paulo",
    "CANDIOTA": "Candiota",
    "CANOAS": "Canoas",
    "CRISTAL": "Cristal",
    "ELDORADO": "Eldorado",
    "GRAVATAI": "Gravataí",
    "JAGUARUNA": "Jaguaruna",
    "PARADOURO": "Paradouro",
    "PARADOURO RESTAURANTE": "Restaurante 86",
    "PINHEIRO MACHADO": "Pinheiro Machado",
    "POA IPIRANGA": "Ipiranga",
    "PORTO ALEGRE": "Porto Alegre",
    "PROTÁSIO": "Protásio",
    "ROTA DO SOL": "Caminho do sol",
    "SEBERI": "Seberi",
    "TERRA DE AREIA": "Terra de Areia",
    "TRANSPORTADORA": "Transportadora",
    "VIAMÃO": "Viamão",
    "PERIMETRAL": None  # Sem pasta mapeada no OneDrive
}

# Lista de empresas do Sistema MR (carregada obrigatoriamente do Streamlit Secrets)
EMPRESAS = []
try:
    if "EMPRESAS" in st.secrets:
        EMPRESAS = list(st.secrets["EMPRESAS"])
except Exception:
    pass

if not EMPRESAS:
    st.error("❌ A lista de EMPRESAS não foi configurada nos Secrets do Streamlit. Por favor, adicione os segredos nas configurações do app.")
    st.stop()

# Funcao de autenticacao MSAL
@st.cache_data(ttl=3000)
def obter_token_acesso():
    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        return None
    authority = f"https://login.microsoftonline.com/{TENANT_ID}"
    app = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=authority, client_credential=CLIENT_SECRET
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return result.get("access_token")

# Funcao para obter filhos do OneDrive
def obter_filhos(drive_id, item_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/children"
    children = []
    while url:
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            break
        data = res.json()
        children.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return children

# Funcao recursiva para buscar PDFs no OneDrive (excluindo 2024 e 2025)
def buscar_arquivos_pdf_recursivo(drive_id, item_id, token, relative_path=""):
    children = obter_filhos(drive_id, item_id, token)
    pdfs = []
    
    for child in children:
        name = child.get("name")
        if "folder" in child:
            if "2024" in name or "2025" in name:
                continue
            new_rel_path = f"{relative_path}/{name}" if relative_path else name
            pdfs.extend(buscar_arquivos_pdf_recursivo(drive_id, child.get("id"), token, new_rel_path))
        else:
            if name.lower().endswith(".pdf"):
                partes = relative_path.split("/")
                conta = partes[1] if len(partes) > 1 else "Padrão"
                
                p_info = child.copy()
                p_info["account"] = conta
                pdfs.append(p_info)
    return pdfs

# Funcao para deduplicar PDFs
def deduplicar_pdfs(arquivos_pdf):
    grupos = {}
    for p in arquivos_pdf:
        name = p.get("name")
        account = p.get("account", "Padrão")
        match = re.match(r"^(\d{2}-\d{4})", name)
        base_name = match.group(1) if match else Path(name).stem
        
        key = (account, base_name)
        if key not in grupos:
            grupos[key] = []
        grupos[key].append(p)
        
    deduplicados = []
    for key, files in grupos.items():
        if len(files) == 1:
            deduplicados.append(files[0])
        else:
            mais_recente = max(
                files, 
                key=lambda x: datetime.strptime(x.get("lastModifiedDateTime")[:19], "%Y-%m-%dT%H:%M:%S")
            )
            deduplicados.append(mais_recente)
            
    return sorted(deduplicados, key=lambda x: (x.get("account"), x.get("name")))

# Helper de sobreposicao de data do arquivo
def arquivo_sobrepoe_datas(nome_arquivo, start_date, end_date):
    match = re.search(r"(\d{2})-(\d{4})", nome_arquivo)
    if not match:
        return True
    m = int(match.group(1))
    y = int(match.group(2))
    
    file_start = datetime(y, m, 1).date()
    ultimo_dia = calendar.monthrange(y, m)[1]
    file_end = datetime(y, m, ultimo_dia).date()
    
    return file_start <= end_date and start_date <= file_end

# Parser de extrato PDF
def parsear_extrato_pdf(conteudo_pdf, nome_arquivo):
    match = re.search(r"(\d{2})-(\d{4})", nome_arquivo)
    if not match:
        return []
    mes = match.group(1)
    ano = match.group(2)
    
    pdf_file = io.BytesIO(conteudo_pdf)
    reader = pypdf.PdfReader(pdf_file)
    
    registros = []
    dia_atual = None
    
    for page in reader.pages:
        text = page.extract_text()
        if not text:
            continue
        linhas = text.split("\n")
        for idx, linha in enumerate(linhas):
            dia_match = re.match(r"^(\d{2})(?:\s{2,}|\s*$)", linha)
            if dia_match:
                dia_atual = dia_match.group(1)
                conteudo_linha = linha[dia_match.end():].strip()
            else:
                conteudo_linha = linha.strip()
                
            if "PIX RECEBIDO" in conteudo_linha:
                valor_match = re.search(r"([\d\.,]+)$", conteudo_linha)
                if valor_match:
                    valor_str = valor_match.group(1)
                    valor_float = float(valor_str.replace(".", "").replace(",", "."))
                else:
                    valor_float = 0.0
                
                nome_pagador = ""
                if idx + 1 < len(linhas):
                    linha_seguinte = linhas[idx+1].strip()
                    if linha_seguinte.startswith("NOME:"):
                        nome_pagador = f" {linha_seguinte}"
                        
                descricao = f"PIX RECEBIDO{nome_pagador}"
                data_completa = f"{dia_atual}/{mes}/{ano}" if dia_atual else f"Unknown/{mes}/{ano}"
                
                registros.append({
                    "Data": data_completa,
                    "Descrição": descricao,
                    "Valor": valor_float
                })
    return registros

# Funcao para buscar lancamentos da API financeira
def obter_lancamentos_api(posto_id, ultimos_dias):
    headers = {
        "Content-Type": "application/json",
        "mr-key": API_KEY
    }
    url = f"{API_URL}/v1/api/export/lancamentos/{posto_id}?ultimosDias={ultimos_dias}"
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return res.json().get("result", [])
    except Exception:
        pass
    return []

# --- INTERFACE STREAMLIT ---

st.markdown('<div class="header-title">🔄 Reconciliação Financeira (Sistema MR vs PDF OneDrive)</div>', unsafe_allow_html=True)
st.markdown('<div class="header-subtitle">Compare e cruze lançamentos do sistema MR com os extratos em PDF do Banrisul</div>', unsafe_allow_html=True)

# 1. Carrega dados inicias
nomes_empresas = [emp.get("nome") for emp in EMPRESAS]

# 2. Configurações na sidebar
with st.sidebar:
    st.markdown("### Configurações")
    empresa_nome = st.selectbox("Selecione o Cliente / Empresa:", nomes_empresas)
    
    # Datas do periodo
    hoje = datetime.today().date()
    # default de 1 mes atras
    inicio_padrao = datetime(hoje.year, hoje.month, 1).date()
    periodo_input = st.date_input(
        "Selecione o período de análise:",
        value=(inicio_padrao, hoje),
        help="Escolha o intervalo de datas para buscar os lançamentos e extratos."
    )
    
    # Processa o periodo
    start_date, end_date = hoje, hoje
    if isinstance(periodo_input, (tuple, list)) and len(periodo_input) == 2:
        start_date, end_date = periodo_input
    elif isinstance(periodo_input, (tuple, list)) and len(periodo_input) == 1:
        start_date, end_date = periodo_input[0], periodo_input[0]
    else:
        start_date = end_date = periodo_input

    # Carrega pastas de Clientes do OneDrive
    token = obter_token_acesso()
    pastas_onedrive = []
    if token and DRIVE_ID and FOLDER_ID:
        filhos = obter_filhos(DRIVE_ID, FOLDER_ID, token)
        pastas_onedrive = [f for f in filhos if "folder" in f]
    
    # Mapeamento do Cliente selecionado para a pasta OneDrive
    # Normaliza unicode para evitar diferenças de encoding (NFC vs NFD) vindas do st.secrets
    def norm(s):
        return unicodedata.normalize("NFC", str(s)).strip() if s else ""
    
    empresa_nome_norm = norm(empresa_nome)
    folder_onedrive_name = next(
        (v for k, v in DE_PARA_POSTOS.items() if norm(k) == empresa_nome_norm),
        None
    )
    pasta_cliente = None
    if folder_onedrive_name and pastas_onedrive:
        pasta_cliente = next((p for p in pastas_onedrive if norm(p.get("name")) == norm(folder_onedrive_name)), None)
    
    # Debug temporário — exibe diagnóstico de conexão na sidebar
    with st.sidebar:
        st.markdown("---")
        with st.expander("🔍 Debug de Conexão", expanded=False):
            st.write(f"**Empresa selecionada:** `{empresa_nome_norm}`")
            st.write(f"**Pasta mapeada:** `{folder_onedrive_name}`")
            st.write(f"**DRIVE_ID:** `{DRIVE_ID[:30] if DRIVE_ID else 'None'}...`")
            st.write(f"**FOLDER_ID:** `{FOLDER_ID[:20] if FOLDER_ID else 'None'}...`")
            st.write(f"**Pastas OneDrive encontradas:** {len(pastas_onedrive)}")
            if pastas_onedrive:
                st.write("Nomes:", [p.get('name') for p in pastas_onedrive[:5]])
            st.write(f"**Pasta cliente:** `{pasta_cliente.get('name') if pasta_cliente else 'None'}`")

    # Identificacao de subpastas/contas para o cliente no OneDrive
    contas_disponiveis = ["Padrão"]
    pdfs_cliente = []
    if pasta_cliente and token:
        pdfs_cliente = buscar_arquivos_pdf_recursivo(DRIVE_ID, pasta_cliente.get("id"), token)
        if pdfs_cliente:
            contas_disponiveis = sorted(list(set(p.get("account") for p in pdfs_cliente)))

    # Filtro de Conta Bancaria
    conta_selecionada = "Todos"
    # O filtro de conta so deve de fato ser exibido se houver mais de uma conta no OneDrive
    if len(contas_disponiveis) > 1 or (len(contas_disponiveis) == 1 and contas_disponiveis[0] != "Padrão"):
        opcoes_contas = ["Todos"] + contas_disponiveis
        conta_selecionada = st.selectbox(
            "Selecione a Conta / Subpasta:",
            options=opcoes_contas,
            help="Filtrar por uma conta Banrisul específica"
        )
    st.markdown("---")
    st.markdown("**Status da Conexão:**")
    if token:
        st.success("🔑 Autenticação OneDrive: OK")
    else:
        st.error("🔑 Autenticação OneDrive: FALHA")
        
    st.markdown("---")
    if st.button("🚪 Sair / Logout"):
        st.session_state["logged_in"] = False
        if hasattr(st, "rerun"):
            st.rerun()
        else:
            st.experimental_rerun()

# Layout de abas principais
tab_rec, tab_depara = st.tabs(["🔄 Conciliação", "📋 De-Para de Postos"])

with tab_depara:
    st.markdown("### De-Para (Mapeamento de Nomes)")
    st.write("A tabela abaixo apresenta a correspondência dos nomes cadastrados no Sistema MR e o nome de suas respectivas pastas de extratos no OneDrive:")
    
    dados_depara = []
    for emp_sys in EMPRESAS:
        sys_nome = emp_sys.get("nome")
        sys_id = emp_sys.get("postoId")
        od_folder = DE_PARA_POSTOS.get(sys_nome, "Não mapeado")
        dados_depara.append({
            "Nome no Sistema MR": sys_nome,
            "ID no Sistema": sys_id,
            "Pasta no OneDrive": od_folder if od_folder else "⚠️ Sem Pasta Mapeada"
        })
    df_depara_table = pd.DataFrame(dados_depara)
    st.dataframe(df_depara_table, use_container_width=True)

with tab_rec:
    # Obter os dados da empresa selecionada
    empresa = next(emp for emp in EMPRESAS if emp.get("nome") == empresa_nome)
    posto_id = empresa.get("postoId")
    
    # Linha única horizontal e minimalista com informações do cliente e botão
    col_btn, col_meta = st.columns([1, 4])
    with col_btn:
        analisar_button = st.button("🔄 Executar Conciliação")
    with col_meta:
        st.markdown(
            f"<div style='padding-top: 8px; font-size: 0.9rem; color: #94a3b8;'>"
            f"🏢 <b>Empresa:</b> {empresa.get('nome')} &nbsp;|&nbsp; "
            f"<b>CNPJ:</b> {empresa.get('cnpj')} &nbsp;|&nbsp; "
            f"<b>ID:</b> <code style='font-size:0.8rem;'>{posto_id}</code>"
            f"</div>", 
            unsafe_allow_html=True
        )

    # Detalhe discreto dos arquivos PDF identificados no OneDrive
    if pasta_cliente:
        if conta_selecionada != "Todos":
            pdfs_filtrados_conta = [p for p in pdfs_cliente if p.get("account") == conta_selecionada]
        else:
            pdfs_filtrados_conta = pdfs_cliente
            
        pdfs_periodo = [p for p in deduplicar_pdfs(pdfs_filtrados_conta) if arquivo_sobrepoe_datas(p.get("name"), start_date, end_date)]
        if pdfs_periodo:
            qtd_pdfs = len(pdfs_periodo)
            nomes_pdf = ", ".join(f"{p.get('name')}" + (f" ({p.get('account')})" if p.get('account') != "Padrão" else "") for p in pdfs_periodo)
            st.markdown(
                f"<div style='font-size: 0.85rem; color: #64748b; margin-top: -0.5rem; margin-bottom: 0.75rem;'>"
                f"📂 <b>Arquivos identificados no OneDrive ({qtd_pdfs}):</b> {nomes_pdf}"
                f"</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"<div style='font-size: 0.85rem; color: #f43f5e; margin-top: -0.5rem; margin-bottom: 0.75rem;'>"
                f"⚠️ Nenhum arquivo PDF encontrado no período selecionado."
                f"</div>",
                unsafe_allow_html=True
            )
    else:
        st.markdown(
            f"<div style='font-size: 0.85rem; color: #f43f5e; margin-top: -0.5rem; margin-bottom: 0.75rem;'>"
            f"⚠️ Nenhuma pasta mapeada para o posto '{empresa_nome}' no OneDrive."
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("<hr style='margin: 0.5rem 0;'/>", unsafe_allow_html=True)

    if analisar_button:
        # Se nao houver pasta ou token
        if not token:
            st.error("Erro de autenticação no OneDrive.")
            st.stop()
            
        with st.spinner("Realizando consulta ao Sistema MR e lendo extratos em PDF..."):
            # 1. Carrega dados do sistema MR
            ultimos_dias = (hoje - start_date).days
            # Garante que puxa pelo menos o periodo necessario
            if ultimos_dias < 30:
                ultimos_dias = 30
            
            lancamentos_brutos = obter_lancamentos_api(posto_id, ultimos_dias)
            
            # Filtra lançamentos do sistema pelas regras
            # Regras:
            # - Descrição contém "PIX RECEBIDO"
            # - Categoria é "1.9 - TED/DOC/PIX"
            # - Banco contém "BANRISUL"
            # - Data está no intervalo selecionado
            lancamentos_sistema = []
            for item in lancamentos_brutos:
                descricao = str(item.get("descricao", ""))
                categoria = str(item.get("categoria", ""))
                banco = str(item.get("conta", ""))
                data_original = item.get("data", "") # YYYY-MM-DD
                
                try:
                    dt = datetime.strptime(data_original, "%Y-%m-%d").date()
                except Exception:
                    continue
                
                if (
                    start_date <= dt <= end_date and
                    "PIX RECEBIDO" in descricao.upper() and
                    categoria == "1.9 - TED/DOC/PIX" and
                    "BANRISUL" in banco.upper()
                ):
                    # Formata data para DD/MM/YYYY
                    data_formatada = dt.strftime("%d/%m/%Y")
                    
                    lancamentos_sistema.append({
                        "Posto": empresa_nome,
                        "dataSistema": data_formatada,
                        "dateObj": dt,
                        "CategoriaSistema": categoria,
                        "ValorSistema": float(item.get("valor", 0)),
                        "ContaBancariaSistema": banco,
                        "DescriçõesPDF": ""
                    })

            # 2. Carrega e parseia arquivos PDF do OneDrive
            pdf_transacoes = []
            if pasta_cliente and pdfs_periodo:
                for p in pdfs_periodo:
                    download_url = p.get("@microsoft.graph.downloadUrl")
                    if download_url:
                        res = requests.get(download_url)
                        if res.status_code == 200:
                            registros = parsear_extrato_pdf(res.content, p.get("name"))
                            for r in registros:
                                r["Conta"] = p.get("account") # subpasta da conta
                                pdf_transacoes.append(r)

            # 3. Conciliação / Cruzamento
            tabela_conciliada = []
            matched_count = 0
            unmatched_count = 0
            
            # Identifica se vamos forçar correspondência de conta (se houver mais de 1 conta no PDF)
            enforce_account = len(contas_disponiveis) > 1 or (len(contas_disponiveis) == 1 and contas_disponiveis[0] != "Padrão")
            
            for s_tx in lancamentos_sistema:
                s_date_str = s_tx["dataSistema"]
                s_val = s_tx["ValorSistema"]
                s_banco = s_tx["ContaBancariaSistema"].upper()
                
                # Procura correspondentes no PDF
                matching_pdfs = []
                for p_tx in pdf_transacoes:
                    p_date_str = p_tx["Data"]
                    p_val = p_tx["Valor"]
                    p_acc = p_tx["Conta"].upper()
                    
                    # Checa data e valor
                    date_match = (p_date_str == s_date_str)
                    value_match = (abs(p_val - s_val) < 0.01)
                    
                    # Checa conta bancaria (se houver mais de uma)
                    acc_match = True
                    if enforce_account:
                        # O numero da conta no PDF (ex: '0609154107') deve estar contido na string de banco do sistema (ex: 'BANRISUL 0609154107')
                        acc_match = (p_acc in s_banco)
                        
                    if date_match and value_match and acc_match:
                        matching_pdfs.append(p_tx)
                
                # Se houver match
                if matching_pdfs:
                    # Concatena todas as descrições dos registros PDF correspondentes separando por |
                    descriptions = [x["Descrição"] for x in matching_pdfs]
                    s_tx["DescriçõesPDF"] = " | ".join(sorted(list(set(descriptions))))
                    matched_count += 1
                else:
                    s_tx["DescriçõesPDF"] = "❌ NÃO ENCONTRADO NO EXTRATO PDF"
                    unmatched_count += 1
                    
                tabela_conciliada.append({
                    "Posto": s_tx["Posto"],
                    "dataSistema": s_tx["dataSistema"],
                    "CategoriaSistema": s_tx["CategoriaSistema"],
                    "ValorSistema": s_tx["ValorSistema"],
                    "ContaBancariaSistema": s_tx["ContaBancariaSistema"],
                    "DescriçõesPDF": s_tx["DescriçõesPDF"]
                })

            # Exibe os resultados
            if not tabela_conciliada:
                st.warning("Nenhum lançamento no Sistema MR corresponde às regras de filtro para o período selecionado.")
            else:
                df_resultado = pd.DataFrame(tabela_conciliada)
                
                # Métricas de Conciliação (Inline e Minimalista)
                total_tx = len(df_resultado)
                pct_match = (matched_count / total_tx * 100) if total_tx > 0 else 0.0
                pct_unmatch = (unmatched_count / total_tx * 100) if total_tx > 0 else 0.0
                
                st.markdown(
                    f"<div style='background-color: #1e293b; padding: 0.5rem 1rem; border-radius: 8px; border: 1px solid #334155; font-size: 0.95rem; margin-bottom: 0.75rem; display: flex; justify-content: space-around; flex-wrap: wrap; gap: 10px;'>"
                    f"<span style='color: #f8fafc;'>📊 <b>Lançamentos Sistema:</b> {total_tx}</span>"
                    f"<span style='color: #4ade80;'>✅ <b>Conciliados (Match PDF):</b> {matched_count} ({pct_match:.1f}%)</span>"
                    f"<span style='color: #f43f5e;'>❌ <b>Não Conciliados:</b> {unmatched_count} ({pct_unmatch:.1f}%)</span>"
                    f"</div>", 
                    unsafe_allow_html=True
                )
                st.markdown("<div style='font-size: 1.1rem; font-weight: bold; color: #f8fafc; margin-top: 0.5rem; margin-bottom: 0.5rem;'>Tabela Comparativa de Conciliação</div>", unsafe_allow_html=True)
                
                # Formata exibição da tabela
                df_exibicao = df_resultado.copy()
                df_exibicao["ValorSistema"] = df_exibicao["ValorSistema"].map(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                st.dataframe(df_exibicao, use_container_width=True)
                
                # Exportação
                csv = df_resultado.to_csv(index=False).encode('utf-8')
                
                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    st.download_button(
                        label="Exportar para CSV",
                        data=csv,
                        file_name=f"CONCILIACAO_{empresa_nome}_{start_date.strftime('%d-%m-%Y')}_a_{end_date.strftime('%d-%m-%Y')}.csv",
                        mime="text/csv",
                    )
                with col_dl2:
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_resultado.to_excel(writer, index=False, sheet_name='Conciliação')
                    excel_data = output.getvalue()
                    
                    st.download_button(
                        label="Exportar para Excel",
                        data=excel_data,
                        file_name=f"CONCILIACAO_{empresa_nome}_{start_date.strftime('%d-%m-%Y')}_a_{end_date.strftime('%d-%m-%Y')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
