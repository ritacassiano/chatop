import json
import sqlite3

import pandas as pd
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


# =========================================================
# 1. CONFIGURACAO DO STREAMLIT
# =========================================================
st.set_page_config(
    page_title="Chatbot Operadora Cartão",
    page_icon="💳",
    layout="centered",
)
st.title("🤖 Chatbot Atendimento - Operadora de Cartão")


# =========================================================
# 2. TREINAMENTO: TF-IDF + REGRESSAO LOGISTICA
# =========================================================
@st.cache_resource
def treinar_modelo():
    dados = pd.read_csv("perguntas.csv")
    X = dados["frase"].astype(str)
    y = dados["categoria"].astype(str)

    modelo = Pipeline([
        ("vetorizador", TfidfVectorizer(ngram_range=(1, 2))),
        ("classificador", LogisticRegression(max_iter=1000, random_state=42)),
    ])
    modelo.fit(X, y)
    return modelo


modelo = treinar_modelo()


# =========================================================
# 3. RESPOSTAS FIXAS
# =========================================================
@st.cache_data
def carregar_respostas():
    with open("respostas.json", "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


respostas_fixas = carregar_respostas()


# =========================================================
# 4. BANCO DE DADOS SQLITE
# =========================================================
def buscar_cliente(cpf):
    with sqlite3.connect("operadora.db") as conexao:
        cursor = conexao.execute("""
            SELECT nome, cpf, numero_cartao, limite_total,
                   limite_disponivel, fatura_atual,
                   vencimento_cartao, vencimento_fatura, status_cartao
            FROM clientes
            WHERE cpf = ?
        """, (cpf,))
        return cursor.fetchone()


def atualizar_status_cartao(cpf, novo_status):
    with sqlite3.connect("operadora.db") as conexao:
        conexao.execute("""
            UPDATE clientes
            SET status_cartao = ?
            WHERE cpf = ?
        """, (novo_status, cpf))
        conexao.commit()


# =========================================================
# 5. MEMORIA DA SESSAO
# =========================================================
if "historico" not in st.session_state:
    st.session_state.historico = []
if "cliente" not in st.session_state:
    st.session_state.cliente = None
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "probabilidades" not in st.session_state:
    st.session_state.probabilidades = None
if "acao_pendente" not in st.session_state:
    st.session_state.acao_pendente = None


# =========================================================
# 6. PROCESSAMENTO DAS PERGUNTAS
# =========================================================
def responder_pergunta(pergunta):
    pergunta = pergunta.lower().strip()
    cliente = st.session_state.cliente
    nome, cpf = cliente[0], cliente[1]

    # Encerramento deve funcionar inclusive durante uma confirmacao.
    if pergunta == "sair":
        st.session_state.cliente = None
        st.session_state.autenticado = False
        st.session_state.probabilidades = None
        st.session_state.acao_pendente = None
        st.session_state.historico = []
        return "Atendimento encerrado. Informe seu CPF para iniciar um novo atendimento."

    # -----------------------------------------------------
    # CONFIRMACAO: nenhuma alteracao ocorre antes de 'sim'.
    # -----------------------------------------------------
    if st.session_state.acao_pendente is not None:
        acao = st.session_state.acao_pendente

        if pergunta in ("não", "nao", "n", "cancelar", "desisto"):
            st.session_state.acao_pendente = None
            return f"{nome}, operação cancelada. Nenhuma alteração foi realizada."

        if pergunta not in ("sim", "s", "confirmo", "confirmar"):
            return (
                f"{nome}, há uma operação de {acao} aguardando confirmação. "
                "Responda 'sim' ou 'não'."
            )

        # Consulta novamente o banco antes de executar a acao.
        cliente_atual = buscar_cliente(cpf)
        if cliente_atual is None:
            st.session_state.acao_pendente = None
            return "Não foi possível localizar seu cadastro. Nenhuma alteração foi feita."

        status_atual = cliente_atual[8].lower()
        st.session_state.acao_pendente = None

        if acao == "bloqueio":
            if status_atual == "cancelado":
                return f"{nome}, seu cartão está cancelado e não pode ser bloqueado."
            if status_atual == "bloqueado":
                return f"{nome}, seu cartão já está bloqueado."
            novo_status = "bloqueado"
            mensagem = f"{nome}, seu cartão foi bloqueado com sucesso."

        elif acao == "desbloqueio":
            if status_atual == "cancelado":
                return f"{nome}, não é possível desbloquear um cartão cancelado."
            if status_atual == "ativo":
                return f"{nome}, seu cartão já está ativo."
            novo_status = "ativo"
            mensagem = f"{nome}, seu cartão foi desbloqueado com sucesso."

        elif acao == "cancelamento":
            if status_atual == "cancelado":
                return f"{nome}, seu cartão já está cancelado."
            novo_status = "cancelado"
            mensagem = f"{nome}, seu cartão foi cancelado com sucesso."

        else:
            return "Operação desconhecida. Nenhuma alteração foi realizada."

        atualizar_status_cartao(cpf, novo_status)
        st.session_state.cliente = buscar_cliente(cpf)
        return mensagem

    # Agradecimento (sem classificar no ML).
    if "obrigado" in pergunta or "obrigada" in pergunta:
        st.session_state.probabilidades = None
        return "Eu que agradeço! Posso ajudar em mais alguma coisa?"

    if not pergunta:
        return "Digite sua pergunta para que eu possa ajudar."

    # Classificacao da intencao e probabilidades no painel.
    categoria = modelo.predict([pergunta])[0]
    probabilidades = modelo.predict_proba([pergunta])[0]
    classes = modelo.named_steps["classificador"].classes_
    st.session_state.probabilidades = pd.DataFrame({
        "Categoria": classes,
        "Probabilidade": probabilidades,
    }).sort_values(by="Probabilidade", ascending=False)

    # Dados do cliente.
    limite = cliente[4]
    fatura = cliente[5]
    vencimento = cliente[7]
    status = cliente[8]

    if categoria == "limite":
        valor = f"{limite:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{nome}, seu limite disponível é de R$ {valor}"

    if categoria == "fatura":
        valor = f"{fatura:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{nome}, o valor da sua fatura atual é de R$ {valor}"

    if categoria == "vencimento":
        return f"{nome}, sua fatura atual vence no dia {vencimento}."

    if categoria == "status":
        return f"{nome}, o status atual do seu cartão é: {status}."

    # -----------------------------------------------------
    # ACOES SENSIVEIS: apenas solicita confirmacao.
    # -----------------------------------------------------
    if categoria == "bloqueio":
        if status.lower() == "cancelado":
            return f"{nome}, seu cartão está cancelado e não pode ser bloqueado."
        if status.lower() == "bloqueado":
            return f"{nome}, seu cartão já está bloqueado."
        st.session_state.acao_pendente = "bloqueio"
        return f"{nome}, você confirma o BLOQUEIO do seu cartão? Responda 'sim' ou 'não'."

    if categoria == "desbloqueio":
        if status.lower() == "cancelado":
            return f"{nome}, não é possível desbloquear um cartão cancelado."
        if status.lower() == "ativo":
            return f"{nome}, seu cartão já está ativo."
        st.session_state.acao_pendente = "desbloqueio"
        return f"{nome}, você confirma o DESBLOQUEIO do seu cartão? Responda 'sim' ou 'não'."

    if categoria == "cancelamento":
        if status.lower() == "cancelado":
            return f"{nome}, seu cartão já está cancelado."
        st.session_state.acao_pendente = "cancelamento"
        return f"{nome}, você confirma o CANCELAMENTO do seu cartão? Responda 'sim' ou 'não'."

    return respostas_fixas.get(
        categoria,
        "Desculpe, não encontrei uma resposta para sua solicitação."
    )


# =========================================================
# 7. INTERFACE STREAMLIT
# =========================================================
if not st.session_state.autenticado:
    st.subheader("Identificação do Cliente")
    cpf = st.text_input(
        "Por favor, digite seu CPF para iniciar o atendimento:",
        max_chars=14,
    )

    if st.button("Acessar Canal de Atendimento"):
        if not cpf:
            st.warning("O campo do CPF não pode ficar vazio.")
        else:
            cliente = buscar_cliente(cpf.strip())
            if cliente:
                st.session_state.cliente = cliente
                st.session_state.autenticado = True
                st.session_state.acao_pendente = None
                st.session_state.historico = [{
                    "role": "assistant",
                    "content": f"Olá, {cliente[0]}! No que posso te ajudar hoje?",
                }]
                st.rerun()
            else:
                st.error("CPF não cadastrado. Cadastre este cliente primeiro.")

else:
    with st.sidebar:
        cliente = st.session_state.cliente
        st.header("📊 Monitor de Machine Learning")
        st.markdown(f"**Cliente logado:** {cliente[0]}")
        st.markdown("**Modelo:** Regressão Logística 📈")
        st.markdown("**Extração:** TF-IDF (Unigrams + Bigrams)")
        st.markdown(f"**Status do cartão:** {cliente[8]}")
        st.divider()

        if st.session_state.probabilidades is not None:
            st.write("Probabilidades calculadas por classe:")
            st.bar_chart(
                data=st.session_state.probabilidades,
                x="Categoria",
                y="Probabilidade",
                horizontal=True,
            )
        else:
            st.info("Digite algo no chat para visualizar as probabilidades geradas pelo modelo.")

        st.divider()
        if st.button("Encerrar Atendimento"):
            st.session_state.cliente = None
            st.session_state.autenticado = False
            st.session_state.historico = []
            st.session_state.probabilidades = None
            st.session_state.acao_pendente = None
            st.rerun()

    for mensagem in st.session_state.historico:
        with st.chat_message(mensagem["role"]):
            st.markdown(mensagem["content"])

    pergunta = st.chat_input("Pergunte algo (ex: qual meu limite?, ver fatura...)")
    if pergunta:
        st.session_state.historico.append({"role": "user", "content": pergunta})
        resposta = responder_pergunta(pergunta)
        st.session_state.historico.append({"role": "assistant", "content": resposta})
        st.rerun()
