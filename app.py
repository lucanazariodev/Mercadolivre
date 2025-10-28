import streamlit as st
import requests
import pandas as pd
import time
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import numpy as np 
import re 
from collections import Counter

# Constantes de configuração
DELAY_SECONDS = 3.0 
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/110.0.0.0 Safari/537.36",
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

# ================= 1. FUNÇÃO DE WEB SCRAPING PRINCIPAL =================
@st.cache_data(ttl=600) 
def scrape_mercado_livre(search_term, pages=1, sort_order="relevance"):
    all_results = []
    search_path = quote_plus(search_term) 
    
    sort_path = ""
    if sort_order == "lowest_price":
        sort_path = "_OrderId_PRICE*ASC" 

    with st.spinner(f"Buscando {pages} páginas para '{search_term}' (Classificação: {sort_order})..."):
        for page_num in range(pages):
            offset = page_num * 48 + 1
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
                    
                    # Link, Título e ID MLB
                    link_el = item.select_one("a.poly-component__title, a.ui-search-link")
                    
                    if link_el and 'href' in link_el.attrs:
                        link = link_el['href']
                        title = link_el.text.strip()
                        
                        match = re.search(r'MLB-(\d+)', link)
                        if match:
                            item_id = match.group(1)
                        else:
                            item_id = item.get('data-item-id', 'N/A')
                        
                    # Preço
                    price_full_el = item.select_one("span.andes-money-amount span.andes-money-amount__fraction")
                    price_cents_el = item.select_one("span.andes-money-amount span.andes-money-amount__cents")
                    
                    if price_full_el:
                        price_str = price_full_el.text.strip()
                        if price_cents_el:
                            price_str += f",{price_cents_el.text.strip()}"
                        price_str = price_str.replace('R$', '').strip()
                        
                    # Frete Grátis
                    shipping_el = item.select_one("p.ui-search-item__shipping-method")
                    if shipping_el and "Grátis" in shipping_el.text:
                        shipping_gratis = "Sim"
                    
                    # Frete FULL
                    full_el = item.select_one("span.ui-search-item__fulfillment-label, span.ui-search-item__fulfillment-label__text")
                    if full_el and "full" in full_el.text.lower():
                        shipping_full = "Sim"
                    elif item.find(string=re.compile(r"FULL", re.IGNORECASE)):
                         shipping_full = "Sim"
                    
                    # Vendidos
                    sold = "N/A"
                    all_poly_labels = item.select("span.poly-phrase-label")
                    for label in all_poly_labels:
                        if "vendidos" in label.text.lower():
                            sold_text = label.text.strip()
                            if '|' in sold_text:
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
                        "Página": page_num + 1,
                        "Link": link,
                    })
                
                st.info(f"Página {page_num + 1} de {pages} processada. Aguardando {DELAY_SECONDS}s...")
                time.sleep(DELAY_SECONDS)

            except requests.exceptions.RequestException as e:
                st.error(f"Erro de conexão na página {page_num + 1}: {e}")
                break

    return pd.DataFrame(all_results)

# ================= 2. FUNÇÕES DE ANÁLISE DE MERCADO =================

def analyze_keywords_8020(df):
    """Identifica os termos mais frequentes nos títulos dos 20% de itens mais vendidos."""
    def clean_sold(s):
        s = str(s).lower().replace('+', '').replace('mil', '000').strip()
        try:
            # Tenta converter para float (para que 1000 se torne 1000.0)
            return float(s)
        except ValueError:
            return 0
    
    df['Vendidos_Num'] = df['Vendidos'].apply(clean_sold)
    
    top_20_count = max(10, int(len(df) * 0.20))
    df_top_vendas = df.sort_values(by='Vendidos_Num', ascending=False).head(top_20_count)
    
    all_words = []
    # Usar uma lista de stopwords definidas para o contexto (pode ser expandida)
    stopwords = {"de", "a", "o", "que", "e", "é", "do", "da", "em", "um", "uma", "para", "com", "no", "na", "por", "mais", "os", "as", "dos", "das", "tem", "são", "ao", "à", "se", "ser", "ou", "quando", "muito", "meu", "minha", "seu", "sua", "esse", "essa", "este", "esta", "para", "mas", "como", "modelo", "slim", "kit", "calças", "envio", "imediato", "par"}
    
    for title in df_top_vendas['Nome'].astype(str):
        words = re.findall(r'\b[a-z]{3,}\b', title.lower())
        words = [word for word in words if word not in stopwords]
        all_words.extend(words)
        
    word_counts = Counter(all_words).most_common(10)
    
    return word_counts, df_top_vendas

def analyze_cost_price(df_top_vendas, markup_min=0.80, markup_exc=1.00):
    """Calcula o preço de compra ideal para atingir os markups alvo."""
    
    df_valid = df_top_vendas.dropna(subset=['Preço Limpo'])
    
    if df_valid.empty:
        return None, None, None

    avg_selling_price = df_valid['Preço Limpo'].mean()
    
    # Preço_Venda / (1 + Markup_Alvo)
    max_cost_80 = avg_selling_price / (1 + markup_min)
    max_cost_100 = avg_selling_price / (1 + markup_exc)
    
    return avg_selling_price, max_cost_80, max_cost_100

# ================= 3. INTERFACE STREAMLIT (main) =================
def main():
    st.set_page_config(layout="wide", page_title="Análise de Mercado Livre (Inteligência)")
    st.title("Ferramenta de Análise de Mercado Livre")
    st.markdown("Coleta dados e gera **Inteligência de Mercado** (80/20, Custo Ideal).")

    st.sidebar.header("Configuração")
    st.sidebar.warning("O delay de 3 segundos está ativo para reduzir o risco de bloqueio.")
    
    search_term = st.text_input("Termo de Busca:", value="kit 3 calças jeans masculina")
    num_pages = st.number_input("Quantas páginas buscar?", min_value=1, max_value=10, value=1)
    
    sort_option = st.selectbox(
        "Classificar Resultados por:",
        ("Mais Relevante", "Menor Preço")
    )

    sort_param = "relevance"
    if sort_option == "Menor Preço":
        sort_param = "lowest_price"
    
    if st.button("Executar Análise de Mercado"):
        if not search_term:
            st.warning("Por favor, digite um termo de busca.")
            return

        df_results = scrape_mercado_livre(search_term, pages=num_pages, sort_order=sort_param)

        if not df_results.empty:
            
            # --- Pré-processamento e Ordenação ---
            try:
                # Limpeza de Preço
                df_results['Preço Limpo'] = (
                    df_results['Preço'].astype(str)
                    .str.replace('.', '', regex=False)
                    .str.replace(',', '.', regex=False)
                    .str.strip()
                )
                df_results['Preço Limpo'] = pd.to_numeric(df_results['Preço Limpo'], errors='coerce')
                
                # Ordenação
                if sort_option == "Menor Preço":
                    df_sorted = df_results.sort_values(by='Preço Limpo', na_position='last', ascending=True)
                else:
                    df_sorted = df_results.copy()
            except Exception as e:
                st.error(f"Erro no pré-processamento dos dados: {e}")
                return

            st.success(f"Encontrados {len(df_results)} anúncios nas primeiras {num_pages} páginas.")
            
            # --- 2. Análise de Palavras-Chave (80/20) ---
            st.header("✨ Análise de Inteligência de Mercado")
            
            with st.container():
                keywords_8020, df_top_vendas = analyze_keywords_8020(df_results.copy())
                
                st.subheader("1. 80/20: Palavras-Chave de Alta Conversão (Top 20% Mais Vendidos)")
                
                if keywords_8020 and df_top_vendas['Vendidos_Num'].sum() > 0:
                    st.markdown("**Quais termos os anúncios mais vendidos possuem?** Estes termos devem ser priorizados em seus títulos.")
                    
                    df_keywords = pd.DataFrame(keywords_8020, columns=['Palavra', 'Frequência'])
                    st.dataframe(df_keywords, use_container_width=True, hide_index=True)
                else:
                    st.warning("Não foi possível realizar a análise de palavras-chave. Verifique se o campo 'Vendidos' está preenchido nos resultados brutos.")

            # --- 3. Análise de Custo Ideal ---
            with st.container():
                avg_price, cost_80, cost_100 = analyze_cost_price(df_top_vendas)
                
                st.subheader("2. Custo Ideal para o Seu Markup")
                
                if avg_price:
                    col1, col2, col3 = st.columns(3)
                    
                    col1.metric("Preço Médio de Venda (Concorrentes Top)", f"R$ {avg_price:,.2f}")
                    
                    col2.metric("Custo Máximo (Markup 80% - Ruim)", 
                                f"R$ {cost_80:,.2f}", 
                                help="Seu preço de compra não deve exceder este valor para obter pelo menos 80% de Markup (com base no preço médio de venda).")
                                
                    col3.metric("Custo Máximo (Markup 100% - Excelente)", 
                                f"R$ {cost_100:,.2f}", 
                                help="Para atingir 100% de Markup, seu custo de compra não deve exceder este valor."
                                )
                    
                    st.markdown(f"""
                        **Sua Decisão:**
                        * Para vender no preço médio da concorrência (R$ **{avg_price:,.2f}**):
                            * Você precisa comprar o produto por, no máximo, R$ **{cost_80:,.2f}** para ter um markup de 80%.
                            * Você precisa comprar o produto por, no máximo, R$ **{cost_100:,.2f}** para ter um markup de 100%.
                        * **Cuidado:** Estes cálculos não incluem taxas do Mercado Livre, impostos e frete. Considere estes custos adicionais ao definir seu preço de compra alvo.
                    """)
                else:
                    st.warning("Não foi possível calcular o preço de custo ideal. Verifique se os itens mais vendidos possuem preços válidos.")


            # --- 4. Tabela de Dados Brutos ---
            st.header("📊 Dados Detalhados Coletados")
            st.dataframe(df_sorted[['Nome', 'Preço', 'Vendidos', 'Frete grátis', 'FULL', 'ID MLB', 'Página', 'Link']].head(num_pages * 48), use_container_width=True, hide_index=True)
        
        else:
            st.warning("Nenhum resultado encontrado. Tente um termo diferente.")

if __name__ == '__main__':
    main()