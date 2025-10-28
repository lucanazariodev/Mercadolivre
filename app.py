import streamlit as st
import requests
import pandas as pd
import time
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import numpy as np 
import re 

# Constantes de configuração
DELAY_SECONDS = 3.0 
HEADERS = {
    # Headers para simular um navegador real (crucial para o ML)
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/110.0.0.0 Safari/537.36",
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

# ================= 1. Função de Web Scraping Principal =================
@st.cache_data(ttl=600) 
def scrape_mercado_livre(search_term, pages=1, sort_order="relevance"):
    all_results = []
    search_path = quote_plus(search_term) 
    
    # 🚨 Lógica de Ordenação: Adiciona o parâmetro de ordenação na URL
    sort_path = ""
    if sort_order == "lowest_price":
        # Parâmetro ML para ordenar por preço crescente
        sort_path = "_OrderId_PRICE*ASC" 
    # Para "relevance" (relevância), a URL fica sem o parâmetro, usando o padrão do ML

    with st.spinner(f"Buscando {pages} páginas para '{search_term}' (Classificação: {sort_order})..."):
        for page_num in range(pages):
            offset = page_num * 48 + 1
            # Constrói a URL com o offset (página) e o parâmetro de ordenação
            url = f"https://lista.mercadolivre.com.br/{search_path}_Desde_{offset}{sort_path}"
            
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                
                if r.status_code == 403:
                    st.error(f"Erro 403 na página {page_num + 1}: Seu IP de servidor está bloqueado.")
                    return pd.DataFrame()
                
                r.raise_for_status()

                soup = BeautifulSoup(r.text, "html.parser")
                items = soup.select("li.ui-search-layout__item")

                if not items:
                    if page_num == 0:
                        st.warning("Nenhum item encontrado na primeira página.")
                    break

                for item in items:
                    title, link, price_str, shipping_gratis, shipping_full, sold, item_id = "N/A", "N/A", "N/A", "Não", "Não", "N/A", "N/A"
                    
                    # 1. Link, Título e ID MLB (Focado nos seletores poly-component/ui-search)
                    link_el = item.select_one("a.poly-component__title, a.ui-search-link")
                    
                    if link_el and 'href' in link_el.attrs:
                        link = link_el['href']
                        title = link_el.text.strip()
                        
                        # ID MLB
                        match = re.search(r'MLB-(\d+)', link)
                        if match:
                            item_id = match.group(1)
                        else:
                            item_id = item.get('data-item-id', 'N/A')
                        
                    # 2. Preço
                    price_full_el = item.select_one("span.andes-money-amount span.andes-money-amount__fraction")
                    price_cents_el = item.select_one("span.andes-money-amount span.andes-money-amount__cents")
                    
                    if price_full_el:
                        price_str = price_full_el.text.strip()
                        if price_cents_el:
                            price_str += f",{price_cents_el.text.strip()}"
                        price_str = price_str.replace('R$', '').strip()
                        
                    # 3. Frete Grátis
                    shipping_el = item.select_one("p.ui-search-item__shipping-method")
                    if shipping_el and "Grátis" in shipping_el.text:
                        shipping_gratis = "Sim"
                    
                    # 4. Frete FULL (CORREÇÃO FINAL: busca pelo texto e classes de fulfillment)
                    # Verifica se existe algum selo de fulfillment OU se a palavra "FULL" está presente
                    full_el = item.select_one("span.ui-search-item__fulfillment-label, span.ui-search-item__fulfillment-label__text")
                    if full_el and "full" in full_el.text.lower():
                        shipping_full = "Sim"
                    # Fallback para busca por texto
                    elif item.find(string=re.compile(r"FULL", re.IGNORECASE)):
                         shipping_full = "Sim"
                    
                    # 5. Vendidos (Lógica de extração exata)
                    sold = "N/A"
                    all_poly_labels = item.select("span.poly-phrase-label")
                    for label in all_poly_labels:
                        if "vendidos" in label.text.lower():
                            sold_text = label.text.strip()
                            if '|' in sold_text:
                                # Pega o texto após o '|' e faz a limpeza
                                sold = sold_text.split('|')[-1].replace(' vendidos', '').strip()
                            else:
                                sold = sold_text.replace(' vendidos', '').strip()
                            break
                    
                    all_results.append({
                        "Nome": title,
                        "Preço": price_str,
                        "Vendidos": sold,
                        "Frete grátis": shipping_gratis,
                        "FULL": shipping_full,
                        "ID MLB": item_id,
                        "Página": page_num + 1, # Adicionando a página
                        "Link": link,
                    })
                
                st.info(f"Página {page_num + 1} de {pages} processada. Aguardando {DELAY_SECONDS}s...")
                time.sleep(DELAY_SECONDS)

            except requests.exceptions.RequestException as e:
                st.error(f"Erro de conexão na página {page_num + 1}: {e}")
                break

    return pd.DataFrame(all_results)

# ================= 2. Interface Streamlit =================
def main():
    st.set_page_config(layout="wide", page_title="Análise Mercado Livre (Scraping)")
    st.title("Ferramenta de Análise do Mercado Livre (Scraping)")
    st.markdown("Busca sequencial direta no HTML do Mercado Livre. **Não usa API oficial.**")

    st.sidebar.header("Configuração")
    st.sidebar.warning("O delay de 3 segundos está ativo para reduzir o risco de bloqueio.")

    search_term = st.text_input("Termo de Busca:", value="kit 3 calças jeans masculina")
    num_pages = st.number_input("Quantas páginas buscar?", min_value=1, max_value=10, value=1)
    
    # 🚨 Opção de Classificação (Novo)
    sort_option = st.selectbox(
        "Classificar Resultados por:",
        ("Mais Relevante", "Menor Preço")
    )

    # Mapeia a opção do usuário para o parâmetro interno
    sort_param = "relevance"
    if sort_option == "Menor Preço":
        sort_param = "lowest_price"
    # Note: A classificação por preço é feita pelo ML na URL, mas a ordenação final na tabela será a mesma.

    if st.button("Buscar Anúncios (Scraping)"):
        if not search_term:
            st.warning("Por favor, digite um termo de busca.")
            return

        df_results = scrape_mercado_livre(search_term, pages=num_pages, sort_order=sort_param)

        if not df_results.empty:
            st.success(f"Encontrados {len(df_results)} anúncios nas primeiras {num_pages} páginas.")
            
            # --- Tratamento de Preço e Ordenação (Interna para garantir consistência) ---
            try:
                # 1. Limpa o Preço
                df_results['Preço Limpo'] = (
                    df_results['Preço'].astype(str)
                    .str.replace('.', '', regex=False)
                    .str.replace(',', '.', regex=False)
                    .str.strip()
                )
                
                # 2. Converte para float
                df_results['Preço Limpo'] = pd.to_numeric(df_results['Preço Limpo'], errors='coerce')
                
                # 3. Ordena (Usando a coluna limpa para ordenação, que já foi solicitada na URL)
                if sort_option == "Menor Preço":
                    # Ordena internamente por preço para exibir corretamente (o ML faz isso, mas garantimos)
                    df_sorted = df_results.sort_values(by='Preço Limpo', na_position='last', ascending=True)
                else:
                    # Se for 'Mais Relevante', mantém a ordem em que o ML retornou os dados
                    df_sorted = df_results.copy()
                
                st.subheader(f"Resultados Encontrados ({sort_option}):")
                # Exibe a coluna Página e FULL na tabela
                st.dataframe(df_sorted[['Nome', 'Preço', 'Vendidos', 'Frete grátis', 'FULL', 'ID MLB', 'Página', 'Link']].head(num_pages * 48), use_container_width=True, hide_index=True)
                
            except Exception as e:
                st.error(f"Erro durante a ordenação ou limpeza dos dados: {e}")
                st.dataframe(df_results[['Nome', 'Preço', 'Vendidos', 'Frete grátis', 'FULL', 'ID MLB', 'Página', 'Link']], use_container_width=True, hide_index=True)
        
        else:
            st.warning("Nenhum resultado encontrado. Tente um termo diferente.")

if __name__ == '__main__':
    main()