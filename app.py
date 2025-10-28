import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from urllib.parse import quote_plus
import time

# --- AUTENTICAÇÃO DO MERCADO LIVRE ---
# Token mais recente (Válido por 6 horas)
ACCESS_TOKEN = "APP_USR-2395996998241392-102721-b5a386a938e4b305786ec0a9eca50ef6-1965939634" 
# -----------------------------------

# Configuração de Headers BASE: Simulação de navegador
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
}

# --- NOVO: HEADER DE AUTORIZAÇÃO OBRIGATÓRIO ---
# Adiciona o token no cabeçalho, conforme documentação do ML.
HEADERS_AUTH = HEADERS.copy()
HEADERS_AUTH['Authorization'] = f'Bearer {ACCESS_TOKEN}'
# -----------------------------------------------

st.set_page_config(page_title="Relatório Mercado Livre", layout="centered")

st.title("📊 Consulta de Produtos no Mercado Livre")

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
if st.button("🔍 Buscar anúncios"):
    if not termo.strip():
        st.error("Digite um termo de busca válido.")
    else:
        with st.spinner("Buscando anúncios..."):
            # Codifica o termo de busca para ser seguro em URL
            q = quote_plus(termo)
            
            # 1. Busca Principal: TOKEN AGORA ESTÁ NO HEADER (HEADERS_AUTH)
            url_search = f"https://api.mercadolibre.com/sites/MLB/search?q={q}&limit={limite}&sort={sort_param}"
            
            try:
                # Usa HEADERS_AUTH, sem token na URL
                res = requests.get(url_search, headers=HEADERS_AUTH, timeout=15)
                res.raise_for_status() 
                dados = res.json()
            except Exception as e:
                # O erro 403 aqui é de bloqueio de ambiente/rede.
                st.error(f"Erro ao acessar a API: {e}")
                st.info("O bloqueio é severo. O código agora segue a recomendação de Header.")
                st.stop()

            resultados = []
            
            # 2. Busca Detalhada para cada item: TOKEN AGORA ESTÁ NO HEADER
            for item in dados.get("results", []):
                try:
                    # Atraso para evitar ser banido durante o loop
                    time.sleep(1) 
                    
                    detalhe_url = f"https://api.mercadolibre.com/items/{item['id']}" # SEM TOKEN NA URL AQUI
                    # Usa HEADERS_AUTH
                    detalhe = requests.get(detalhe_url, headers=HEADERS_AUTH, timeout=10).json()
                    date_created = detalhe.get("date_created", "")
                except:
                    date_created = ""
                    
                resultados.append({
                    "Título": item.get("title", ""),
                    "Preço (R$)": item.get("price", ""),
                    "Vendas": item.get("sold_quantity", 0), 
                    "Data de Criação": date_created,
                    "Link": item.get("permalink", "")
                })

            if not resultados:
                st.warning("Nenhum resultado encontrado.")
            else:
                df = pd.DataFrame(resultados)
                st.success(f"{len(df)} anúncios encontrados!")
                st.dataframe(df)

                # --- Exportar para Excel ---
                data_atual = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                nome_arquivo = f"relatorio_ml_{data_atual}.xlsx"
                
                df.to_excel(nome_arquivo, index=False)

                with open(nome_arquivo, "rb") as f:
                    st.download_button(
                        label="Baixar relatório em Excel",
                        data=f,
                        file_name=nome_arquivo,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )