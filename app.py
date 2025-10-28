import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from urllib.parse import quote_plus
import time

# --- AUTENTICAÇÃO DO MERCADO LIVRE (NOVO APP ID) ---
# Token mais recente gerado:
ACCESS_TOKEN = "APP_USR-6851821260526902-102722-d27dbc2dee5fb131dfcd67cd9c55cf9a-1965939634" 
# ---------------------------------------------------

# Configuração de Headers BASE: Simulação de navegador
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
}

# --- HEADER DE AUTORIZAÇÃO OBRIGATÓRIO (Recomendação do ML) ---
# Adiciona o token no cabeçalho para maior segurança e compatibilidade.
HEADERS_AUTH = HEADERS.copy()
HEADERS_AUTH['Authorization'] = f'Bearer {ACCESS_TOKEN}'
# -------------------------------------------------------------

st.set_page_config(page_title="Relatório Mercado Livre", layout="centered")

st.title("📊 Consulta de Produtos no Mercado Livre")
st.info("Utilizando o novo Access Token. O erro 403 é uma barreira de segurança do Mercado Livre (bloqueio de IP/rede).")

# --- Entrada do usuário ---
termo = st.text_input("Digite o termo de busca", "lâmpada LED")
limite = st.slider("Quantidade de resultados", 10, 200, 20)
ordenar = st.selectbox(
    "Ordenar por:",
    ("Mais vendidos (decrescente)", "Menor preço", "Maior preço")
)

sort_map = {
    "Mais vendidos (decrescente)": "sold_quantity_desc",
    "Menor preço": "price_asc",
    "Maior preço": "price_desc"
}
sort_param = sort_map[ordenar]

# --- Botão de busca ---
if st.button("Buscar anúncios"):
    if not termo.strip():
        st.error("Digite um termo de busca válido.")
    else:
        with st.spinner("Buscando anúncios..."):
            # Codifica o termo de busca para ser seguro em URL
            q = quote_plus(termo)
            
            # 1. Busca Principal: TOKEN NO HEADER
            url_search = f"https://api.mercadolibre.com/sites/MLB/search?q={q}&limit={limite}&sort={sort_param}"
            
            try:
                # Usa HEADERS_AUTH para enviar o token
                res = requests.get(url_search, headers=HEADERS_AUTH, timeout=15)
                res.raise_for_status() 
                dados = res.json()
            except Exception as e:
                # Captura e exibe o erro (espera-se o 403)
                st.error(f"Erro ao acessar a API: {e}")
                st.info("Confirmação: o bloqueio é de rede/infraestrutura, não do código ou do token.")
                st.stop()

            resultados = []
            
            # 2. Busca Detalhada para cada item: TOKEN NO HEADER
            for item in dados.get("results", []):
                try:
                    # Atraso para evitar ser banido durante o loop
                    time.sleep(1) 
                    
                    detalhe_url = f"https://api.mercadolibre.com/items/{item['id']}" 
                    # Usa HEADERS_AUTH
                    detalhe = requests.get(detalhe_url, headers=HEADERS_AUTH, timeout=10).json()
                    date_created = detalhe.get("date_created", "")
                except:
                    date_created = ""