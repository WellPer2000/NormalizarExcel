import os
import streamlit as st
from groq import Groq

# Set the API key as an environment variable
os.environ["GROQ_API_KEY"] = "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"  # Replace with your Groq API key

# Inicializar o cliente da API
client = Groq()  # O cliente pegará automaticamente a chave de API

# Definição das preferências diretamente no código (sem exibir no front-end)
usuario_nome = "Wellington Pereira"  # Nome personalizado do usuário
preferencias_conteudo = [
    "Foque em responder sobre análise de dados e Business Intelligence",
    "Responda de forma detalhada e formal",
    "Evite jargões técnicos desnecessários",
    "Utilize exemplos práticos quando possível",
    "Nasci dia 18/05/2000",
    "Meu namorado se chama Mateus",
    "Nasci em guaiba",
    "estamos no ano de 2024"
]

# Inicializar o histórico e outros estados de sessão, se necessário
if "historico" not in st.session_state:
    st.session_state.historico = []
if 'input' not in st.session_state:
    st.session_state.input = ''
if 'ultima_resposta' not in st.session_state:
    st.session_state.ultima_resposta = ''

# Função para enviar a pergunta e receber a resposta
def send_question(question):
    # Adicionar a pergunta do usuário ao histórico
    st.session_state.historico.append({"role": "user", "content": question})
    
    # Criar uma mensagem de contexto com as preferências e o nome do usuário
    mensagens = [{"role": "system", "content": f"Você está atendendo o usuário {usuario_nome}. Considere as seguintes preferências: {', '.join(preferencias_conteudo)}."}]
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
st.title("Chat com IA - Perguntas e Respostas")

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
