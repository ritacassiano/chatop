"""CRUD administrativo para o banco SQLite do chatbot da operadora.

Execute com: streamlit run crud.py
Configure CRUD_ADMIN_PASSWORD no ambiente ou em .streamlit/secrets.toml.
"""

import hmac
import os
import sqlite3
import pandas as pd
import streamlit as st
from pathlib import Path


st.set_page_config(page_title="Administração da Operadora", page_icon="💳", layout="wide")

DB_PATH = Path(__file__).resolve().parent / "operadora.db"
COLUNAS = [
    "nome", "cpf", "numero_cartao", "limite_total", "limite_disponivel",
    "fatura_atual", "vencimento_cartao", "vencimento_fatura", "status_cartao",
]
STATUS = ["ativo", "bloqueado", "cancelado"]


def conectar():
    conexao = sqlite3.connect(DB_PATH, timeout=10)
    conexao.row_factory = sqlite3.Row
    return conexao


def tabela_existe():
    with conectar() as con:
        linha = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clientes'"
        ).fetchone()
        return linha is not None


def listar_clientes():
    with conectar() as con:
        linhas = con.execute(
            "SELECT rowid AS identificador, " + ", ".join(COLUNAS) +
            " FROM clientes ORDER BY nome COLLATE NOCASE"
        ).fetchall()
    return [dict(linha) for linha in linhas]


def cliente_por_id(identificador):
    with conectar() as con:
        linha = con.execute(
            "SELECT rowid AS identificador, " + ", ".join(COLUNAS) +
            " FROM clientes WHERE rowid = ?", (identificador,)
        ).fetchone()
    return dict(linha) if linha else None


def salvar_cliente(valores, identificador=None):
    with conectar() as con:
        if identificador is None:
            campos = ", ".join(COLUNAS)
            marcadores = ", ".join("?" for _ in COLUNAS)
            con.execute(
                f"INSERT INTO clientes ({campos}) VALUES ({marcadores})",
                tuple(valores[c] for c in COLUNAS),
            )
        else:
            atribuicoes = ", ".join(f"{c} = ?" for c in COLUNAS)
            con.execute(
                f"UPDATE clientes SET {atribuicoes} WHERE rowid = ?",
                tuple(valores[c] for c in COLUNAS) + (identificador,),
            )
        con.commit()


def excluir_cliente(identificador):
    with conectar() as con:
        con.execute("DELETE FROM clientes WHERE rowid = ?", (identificador,))
        con.commit()


def validar(valores):
    if not valores["nome"].strip():
        return "Informe o nome do cliente."
    if not valores["cpf"].strip():
        return "Informe o CPF do cliente."
    if not valores["numero_cartao"].strip():
        return "Informe o número do cartão (use dados fictícios nos testes)."
    if valores["limite_disponivel"] > valores["limite_total"]:
        return "O limite disponível não pode superar o limite total."
    return None


def formulario(prefixo, inicial=None):
    inicial = inicial or {}
    with st.form(f"form_{prefixo}"):
        nome = st.text_input("Nome", value=inicial.get("nome", ""))
        cpf = st.text_input("CPF", value=inicial.get("cpf", ""))
        numero_cartao = st.text_input(
            "Número do cartão (fictício)", value=inicial.get("numero_cartao", "")
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            limite_total = st.number_input(
                "Limite total (R$)", min_value=0.0,
                value=float(inicial.get("limite_total") or 0), step=100.0, format="%.2f",
            )
        with c2:
            limite_disponivel = st.number_input(
                "Limite disponível (R$)", min_value=0.0,
                value=float(inicial.get("limite_disponivel") or 0), step=100.0,
                format="%.2f",
            )
        with c3:
            fatura_atual = st.number_input(
                "Fatura atual (R$)", min_value=0.0,
                value=float(inicial.get("fatura_atual") or 0), step=50.0, format="%.2f",
            )
        c4, c5, c6 = st.columns(3)
        with c4:
            vencimento_cartao = st.text_input(
                "Vencimento do cartão (formato original do banco)",
                value=str(inicial.get("vencimento_cartao") or ""),
            )
        with c5:
            vencimento_fatura = st.text_input(
                "Vencimento da fatura (formato original do banco)",
                value=str(inicial.get("vencimento_fatura") or ""),
            )
        with c6:
            status_atual = str(inicial.get("status_cartao") or "ativo").lower()
            status = st.selectbox(
                "Status do cartão", STATUS,
                index=STATUS.index(status_atual) if status_atual in STATUS else 0,
            )
        enviado = st.form_submit_button("Salvar cliente", type="primary")
    valores = {
        "nome": nome.strip(), "cpf": cpf.strip(),
        "numero_cartao": numero_cartao.strip(),
        "limite_total": limite_total, "limite_disponivel": limite_disponivel,
        "fatura_atual": fatura_atual,
        "vencimento_cartao": vencimento_cartao.strip(),
        "vencimento_fatura": vencimento_fatura.strip(),
        "status_cartao": status,
    }
    return enviado, valores


def senha_configurada():
    try:
        senha = st.secrets.get("CRUD_ADMIN_PASSWORD")
        if senha:
            return str(senha)
    except (FileNotFoundError, KeyError):
        pass
    return os.getenv("CRUD_ADMIN_PASSWORD", "")


st.title("💳 Administração da Operadora")
st.caption("CRUD didático: cadastre, consulte, atualize e exclua clientes do SQLite.")

senha = senha_configurada()
if not senha:
    st.error(
        "Acesso administrativo desativado. Configure CRUD_ADMIN_PASSWORD "
        "no ambiente ou no arquivo .streamlit/secrets.toml (não envie a senha ao GitHub)."
    )
    st.stop()

if not st.session_state.get("crud_autenticado", False):
    with st.form("login_admin"):
        tentativa = st.text_input("Senha administrativa", type="password")
        entrar = st.form_submit_button("Entrar")
    if entrar:
        if hmac.compare_digest(tentativa, senha):
            st.session_state.crud_autenticado = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    st.stop()

with st.sidebar:
    st.success("Área administrativa")
    if st.button("Sair da administração"):
        st.session_state.crud_autenticado = False
        st.rerun()
    st.warning("Use apenas dados fictícios neste projeto de demonstração.")

if not DB_PATH.exists():
    st.error(f"Banco não encontrado: {DB_PATH}. Coloque crud.py na pasta do operadora.db.")
    st.stop()
if not tabela_existe():
    st.error("A tabela 'clientes' não existe no banco de dados.")
    st.stop()

abas = st.tabs(["Consultar", "Cadastrar", "Editar", "Excluir"])

with abas[0]:
    st.subheader("Clientes cadastrados")
    clientes = listar_clientes()
    termo = st.text_input("Pesquisar por nome ou CPF", key="busca")
    filtrados = [c for c in clientes if termo.lower() in c["nome"].lower() or termo in c["cpf"]]
    if filtrados:
        colunas_visiveis = ["identificador", "nome", "cpf", "limite_total", "limite_disponivel", "fatura_atual", "vencimento_cartao", "vencimento_fatura", "status_cartao"]
        st.dataframe(pd.DataFrame(filtrados)[colunas_visiveis], hide_index=True, use_container_width=True)
        st.caption(f"{len(filtrados)} cliente(s) exibido(s). Números de cartão não são mostrados na tabela.")
    else:
        st.info("Nenhum cliente encontrado.")

with abas[1]:
    st.subheader("Cadastrar cliente")
    enviado, valores = formulario("novo")
    if enviado:
        erro = validar(valores)
        if erro:
            st.error(erro)
        else:
            try:
                salvar_cliente(valores)
                st.success("Cliente cadastrado com sucesso!")
            except sqlite3.IntegrityError as exc:
                st.error(f"Não foi possível cadastrar: verifique CPF e número do cartão duplicados. Detalhes: {exc}")
            except sqlite3.Error as exc:
                st.error(f"Erro no banco: {exc}")

with abas[2]:
    st.subheader("Editar cliente")
    clientes = listar_clientes()
    if not clientes:
        st.info("Não há clientes cadastrados.")
    else:
        opcoes = {f"{c['nome']} — CPF {c['cpf']} (ID {c['identificador']})": c["identificador"] for c in clientes}
        selecionado = st.selectbox("Selecione o cliente", list(opcoes), key="editar_cliente")
        identificador = opcoes[selecionado]
        atual = cliente_por_id(identificador)
        if atual:
            enviado, valores = formulario(f"editar_{identificador}", atual)
            if enviado:
                erro = validar(valores)
                if erro:
                    st.error(erro)
                else:
                    try:
                        salvar_cliente(valores, identificador)
                        st.success("Cadastro atualizado com sucesso!")
                    except sqlite3.IntegrityError as exc:
                        st.error(f"Não foi possível atualizar: {exc}")
                    except sqlite3.Error as exc:
                        st.error(f"Erro no banco: {exc}")

with abas[3]:
    st.subheader("Excluir cliente")
    clientes = listar_clientes()
    if not clientes:
        st.info("Não há clientes cadastrados.")
    else:
        opcoes = {f"{c['nome']} — CPF {c['cpf']} (ID {c['identificador']})": c["identificador"] for c in clientes}
        selecionado = st.selectbox("Selecione o cliente", list(opcoes), key="excluir_cliente")
        identificador = opcoes[selecionado]
        st.warning("A exclusão é permanente e remove o cadastro do banco de dados.")
        with st.form(f"excluir_{identificador}"):
            confirmar = st.checkbox("Confirmo que desejo excluir este cliente")
            excluir = st.form_submit_button("Excluir definitivamente")
        if excluir:
            if not confirmar:
                st.error("Marque a confirmação para excluir.")
            else:
                try:
                    excluir_cliente(identificador)
                    st.success("Cliente excluído com sucesso!")
                    st.rerun()
                except sqlite3.Error as exc:
                    st.error(f"Erro ao excluir: {exc}")
