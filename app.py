# CÓDIGO FINAL SEM AUTENTICAÇÃO (Para colar no app.py)
import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from urllib.parse import quote_plus
import time

# --- SEM AUTENTICAÇÃO ---
# Removemos o Access Token e as credenciais.
# O acesso é tratado como totalmente público para tentar contornar o 403.
# ------------------------

# Configuração de Headers: Simulação de navegador mais detalhada
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
}

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
            
            # 1. Busca Principal: URL totalmente pública (SEM TOKEN)
            url_search = f"https://api.mercadolibre.com/sites/MLB/search?q={q}&limit={limite}&sort={sort_param}"
            
            try:
                res = requests.get(url_search, headers=HEADERS, timeout=15)
                res.raise_for_status() 
                dados = res.json()
            except Exception as e:
                # Se falhar, a conclusão é que o ambiente local está bloqueado.
                st.error(f"Erro ao acessar a API: {e}")
                st.info("O bloqueio é no nível da rede/IP. A única solução é o deploy na nuvem.")
                st.stop()

            resultados = []
            
            # 2. Busca Detalhada para cada item: URL totalmente pública (SEM TOKEN)
            for item in dados.get("results", []):
                try:
                    # Atraso para evitar ser banido durante o loop
                    time.sleep(1) 
                    
                    detalhe_url = f"https://api.mercadolibre.com/items/{item['id']}" # SEM TOKEN AQUI
                    detalhe = requests.get(detalhe_url, headers=HEADERS, timeout=10).json() # LINHA 68 CORRIGIDA
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
                        label="⬇️ Baixar relatório em Excel",
                        data=f,
                        file_name=nome_arquivo,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )