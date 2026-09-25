import streamlit as st
import pandas as pd
import json
import sqlite3

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


# =========================================================
# CONFIGURAÇÃO DO STREAMLIT
# =========================================================

st.set_page_config(
    page_title="Chatbot Operadora Cartão",
    page_icon="💳",
    layout="centered"
)

st.title("🤖 Chatbot Atendimento - Operadora de Cartão")


# =========================================================
# TREINAMENTO DO MODELO
# =========================================================

@st.cache_resource
def treinar_modelo():
    dados = pd.read_csv("perguntas.csv")

    # Features (X) e Target (y)
    X = dados["frase"].astype(str)
    y = dados["categoria"].astype(str)

    # Pipeline: TF-IDF + Regressão Logística
    modelo = Pipeline([
        ("vetorizador", TfidfVectorizer(ngram_range=(1, 2))),
        ("classificador", LogisticRegression(
            max_iter=1000,
            random_state=42
        ))
    ])

    modelo.fit(X, y)

    return modelo


modelo = treinar_modelo()


# =========================================================
# RESPOSTAS FIXAS
# =========================================================

@st.cache_data
def carregar_respostas():
    with open("respostas.json", "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


respostas_fixas = carregar_respostas()


# =========================================================
# BANCO DE DADOS
# =========================================================

def buscar_cliente(cpf):
    conexao = sqlite3.connect("operadora.db")
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT nome, cpf, numero_cartao, limite_total,
               limite_disponivel, fatura_atual,
               vencimento_cartao, vencimento_fatura,
               status_cartao
        FROM clientes
        WHERE cpf = ?
    """, (cpf,))

    cliente = cursor.fetchone()

    conexao.close()

    return cliente


def atualizar_status_cartao(cpf, novo_status):
    conexao = sqlite3.connect("operadora.db")
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE clientes
        SET status_cartao = ?
        WHERE cpf = ?
    """, (novo_status, cpf))

    conexao.commit()
    conexao.close()


# =========================================================
# MEMÓRIA DA SESSÃO
# =========================================================

if "historico" not in st.session_state:
    st.session_state.historico = []

if "cliente" not in st.session_state:
    st.session_state.cliente = None

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if "probabilidades" not in st.session_state:
    st.session_state.probabilidades = None


# =========================================================
# FUNÇÃO PRINCIPAL DO CHATBOT
# =========================================================

def responder_pergunta(pergunta):

    pergunta = pergunta.lower().strip()
    cliente = st.session_state.cliente

    # Encerramento
    if pergunta == "sair":
        st.session_state.cliente = None
        st.session_state.autenticado = False
        st.session_state.probabilidades = None

        return (
            "Atendimento encerrado. "
            "Informe seu CPF para iniciar um novo atendimento."
        )

    # Agradecimento
    if "obrigado" in pergunta or "obrigada" in pergunta:
        st.session_state.probabilidades = None
        return "Eu que agradeço! Posso ajudar em mais alguma coisa?"

    # -----------------------------------------------------
    # PREVISÃO DA CATEGORIA
    # -----------------------------------------------------

    categoria = modelo.predict([pergunta])[0]
    probabilidades = modelo.predict_proba([pergunta])[0]

    classificador = modelo.named_steps["classificador"]
    classes = classificador.classes_

    # Dados para o gráfico lateral
    df_probabilidades = pd.DataFrame({
        "Categoria": classes,
        "Probabilidade": probabilidades
    })

    st.session_state.probabilidades = df_probabilidades.sort_values(
        by="Probabilidade",
        ascending=False
    )

    # -----------------------------------------------------
    # DADOS DO CLIENTE
    # -----------------------------------------------------

    nome = cliente[0]
    cpf = cliente[1]
    limite = cliente[4]
    fatura = cliente[5]
    vencimento = cliente[7]
    status = cliente[8]

    # -----------------------------------------------------
    # CONSULTAS
    # -----------------------------------------------------

    if categoria == "limite":

        valor = (
            f"{limite:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

        return f"{nome}, seu limite disponível é de R$ {valor}"


    elif categoria == "fatura":

        valor = (
            f"{fatura:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

        return f"{nome}, o valor da sua fatura atual é de R$ {valor}"


    elif categoria == "vencimento":

        return f"{nome}, sua fatura atual vence no dia {vencimento}."


    elif categoria == "status":

        return f"{nome}, o status atual do seu cartão é: {status}."


    # -----------------------------------------------------
    # BLOQUEIO
    # -----------------------------------------------------

    elif categoria == "bloqueio":

        if status.lower() == "cancelado":
            return (
                f"{nome}, seu cartão está cancelado "
                "e não pode ser bloqueado."
            )

        if status.lower() == "bloqueado":
            return f"{nome}, seu cartão já está bloqueado."

        atualizar_status_cartao(cpf, "bloqueado")

        # Atualiza os dados armazenados na sessão
        st.session_state.cliente = buscar_cliente(cpf)

        return f"{nome}, seu cartão foi bloqueado com sucesso."


    # -----------------------------------------------------
    # DESBLOQUEIO
    # -----------------------------------------------------

    elif categoria == "desbloqueio":

        if status.lower() == "cancelado":
            return (
                f"{nome}, não é possível desbloquear "
                "um cartão cancelado."
            )

        if status.lower() == "ativo":
            return f"{nome}, seu cartão já está ativo."

        atualizar_status_cartao(cpf, "ativo")

        st.session_state.cliente = buscar_cliente(cpf)

        return f"{nome}, seu cartão foi desbloqueado com sucesso."


    # -----------------------------------------------------
    # CANCELAMENTO
    # -----------------------------------------------------

    elif categoria == "cancelamento":

        if status.lower() == "cancelado":
            return f"{nome}, seu cartão já está cancelado."

        atualizar_status_cartao(cpf, "cancelado")

        st.session_state.cliente = buscar_cliente(cpf)

        return f"{nome}, seu cartão foi cancelado com sucesso."


    # -----------------------------------------------------
    # RESPOSTAS FIXAS DO JSON
    # -----------------------------------------------------

    else:

        return respostas_fixas.get(
            categoria,
            "Desculpe, não encontrei uma resposta para sua solicitação."
        )


# =========================================================
# IDENTIFICAÇÃO DO CLIENTE
# =========================================================

if not st.session_state.autenticado:

    st.subheader("Identificação do Cliente")

    cpf = st.text_input(
        "Por favor, digite seu CPF para iniciar o atendimento:",
        max_chars=14
    )

    if st.button("Acessar Canal de Atendimento"):

        if not cpf:
            st.warning("O campo do CPF não pode ficar vazio.")

        else:
            cliente = buscar_cliente(cpf.strip())

            if cliente:
                st.session_state.cliente = cliente
                st.session_state.autenticado = True

                st.session_state.historico.append({
                    "role": "assistant",
                    "content":
                        f"Olá, {cliente[0]}! "
                        "No que posso te ajudar hoje?"
                })

                st.rerun()

            else:
                st.error(
                    "CPF não cadastrado. "
                    "Cadastre este cliente primeiro."
                )


# =========================================================
# CHATBOT
# =========================================================

else:

    # -----------------------------------------------------
    # PAINEL LATERAL
    # -----------------------------------------------------

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
                horizontal=True
            )

        else:

            st.info(
                "Digite algo no chat para visualizar "
                "as probabilidades geradas pelo modelo."
            )

        st.divider()

        if st.button("Encerrar Atendimento"):

            st.session_state.cliente = None
            st.session_state.autenticado = False
            st.session_state.historico = []
            st.session_state.probabilidades = None

            st.rerun()


    # -----------------------------------------------------
    # HISTÓRICO DA CONVERSA
    # -----------------------------------------------------

    for mensagem in st.session_state.historico:

        with st.chat_message(mensagem["role"]):
            st.markdown(mensagem["content"])


    # -----------------------------------------------------
    # ENTRADA DO USUÁRIO
    # -----------------------------------------------------

    pergunta = st.chat_input(
        "Pergunte algo (ex: qual meu limite?, ver fatura...)"
    )

    if pergunta:

        # Mensagem do usuário
        st.session_state.historico.append({
            "role": "user",
            "content": pergunta
        })

        # Processa a pergunta
        resposta = responder_pergunta(pergunta)

        # Resposta do chatbot
        st.session_state.historico.append({
            "role": "assistant",
            "content": resposta
        })

        st.rerun()