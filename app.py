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

# ================= 1. FUNÇÕES DE LIMPEZA E CONVERSÃO NUMÉRICA =================

def clean_sold_data(texto):
    """
    [USADA PARA ORDENAÇÃO INTERNA] Converte a string 'Vendidos' para um número inteiro.
    """
    if pd.isna(texto) or not isinstance(texto, str) or texto.upper() == 'N/A' or not texto.strip():
        return 0 
    
    texto = texto.lower().replace('+', '').strip()
    
    if 'mil' in texto:
        try:
            base_value = float(texto.replace('mil', '').replace(',', '.'))
            return int(base_value * 1000)
        except ValueError:
            return 0
            
    try:
        return int(texto)
    except ValueError:
        return 0

def format_sold_data_for_display(texto):
    """
    [USADA PARA EXIBIÇÃO] Substitui 'mil' por '000' e remove o '+' para clareza na tabela.
    """
    if pd.isna(texto) or not isinstance(texto, str) or not texto.strip():
        return 'N/A' 
    
    texto = texto.strip()

    if texto.upper() == 'N/A' or clean_sold_data(texto) == 0:
        return 'N/A'
    
    texto = texto.replace('+', '').replace('mil', '000').strip()
    
    try:
        num = int(texto)
        return f"{num:,}".replace(",", ".") # Ex: 10.000
    except ValueError:
        return texto 

# ================= 2. FUNÇÃO DE CÁLCULO DE PRECIFICAÇÃO =================

def calculate_profit(pv, cp):
    """
    Calcula o lucro líquido e custos para Mercado Livre e Shopee.
    
    :param pv: Preço de Venda (Price Value)
    :param cp: Custo do Produto (Cost Price)
    :return: Dicionário com resultados de ML e Shopee.
    """
    
    # Se PV for zero ou menor que CP, retorna margens nulas para evitar divisão por zero ou resultados ilógicos.
    if pv <= cp:
        # Se PV for irreal, ainda retorna a estrutura para não quebrar a exibição
        return {
            'Mercado Livre': {'Custo Total': 0, 'Comissão': 0, 'Lucro Bruto': 0, 'Margem %': 0},
            'Shopee': {'Custo Total': 0, 'Comissão': 0, 'Lucro Bruto': 0, 'Margem %': 0}
        }

    # --- Custos Fixos e Percentuais Comuns ---
    
    TAX_IMPOSTO = 0.04       # 4% de imposto sobre PV
    TAX_MARKETING = 0.03     # 3% de marketing sobre PV
    COST_EMBALAGEM = 0.35    # R$ 0,35 por pedido
    COST_OPERACAO = 1.50     # R$ 1,50 por pedido
    
    COST_FIXO_VENDA = COST_EMBALAGEM + COST_OPERACAO # R$ 1.85
    COST_PERCENTUAL_BASE = TAX_IMPOSTO + TAX_MARKETING # 7%
    
    # --- Custos de Marketplace (Médios/Estimados) ---
    
    # Mercado Livre (25% FIXO sobre PV)
    ML_COMMISSION_RATE = 0.25
    ML_FIXED_COST = 0.00
    
    # Shopee (18% de comissão total)
    SHOPEE_COMMISSION_RATE = 0.18
    
    results = {}

    # --- Cálculo Mercado Livre ---
    ML_COMISSAO = (pv * ML_COMMISSION_RATE) + ML_FIXED_COST
    
    ML_CUSTO_TOTAL = (cp 
                      + (pv * COST_PERCENTUAL_BASE) 
                      + ML_COMISSAO 
                      + COST_FIXO_VENDA)
    
    ML_LUCRO_BRUTO = pv - ML_CUSTO_TOTAL
    ML_MARGEM_PERCENTUAL = (ML_LUCRO_BRUTO / pv)
    
    results['Mercado Livre'] = {
        'Custo Total': ML_CUSTO_TOTAL,
        'Comissão': ML_COMISSAO,
        'Lucro Bruto': ML_LUCRO_BRUTO,
        'Margem %': ML_MARGEM_PERCENTUAL * 100
    }

    # --- Cálculo Shopee ---
    SHOPEE_COMISSAO = (pv * SHOPEE_COMMISSION_RATE)
    SHOPEE_CUSTO_TOTAL = (cp 
                          + (pv * COST_PERCENTUAL_BASE) 
                          + SHOPEE_COMISSAO 
                          + COST_FIXO_VENDA)
    
    SHOPEE_LUCRO_BRUTO = pv - SHOPEE_CUSTO_TOTAL
    SHOPEE_MARGEM_PERCENTUAL = (SHOPEE_LUCRO_BRUTO / pv)
    
    results['Shopee'] = {
        'Custo Total': SHOPEE_CUSTO_TOTAL,
        'Comissão': SHOPEE_COMISSAO,
        'Lucro Bruto': SHOPEE_LUCRO_BRUTO,
        'Margem %': SHOPEE_MARGEM_PERCENTUAL * 100
    }
    
    return results

# ================= 3. FUNÇÃO DE WEB SCRAPING PRINCIPAL (MANTIDA) =================
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
                r.raise_for_status()

                soup = BeautifulSoup(r.text, "html.parser")
                items = soup.select("li.ui-search-layout__item")

                if not items and page_num == 0:
                    st.warning("Nenhum item encontrado na primeira página.")
                    break

                for item in items:
                    # Inicialização das variáveis
                    title, link, price_str, shipping_gratis, shipping_full, sold, item_id, image_url = "N/A", "N/A", "N/A", "Não", "Não", "N/A", "N/A", "N/A"
                    
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

                    # Vendidos
                    all_poly_labels = item.select("span.poly-phrase-label")
                    for label in all_poly_labels:
                        if "vendidos" in label.text.lower():
                            sold_text = label.text.strip()
                            if '|' in sold_text:
                                sold = sold_text.split('|')[-1].replace(' vendidos', '').strip()
                            else:
                                sold = sold_text.replace(' vendidos', '').strip()
                            break
                            
                    # Frete Grátis e FULL
                    shipping_gratis, shipping_full = "Não", "Não" 
                    shipping_el = item.select_one("p.ui-search-item__shipping-method")
                    if shipping_el and "Grátis" in shipping_el.text:
                        shipping_gratis = "Sim"
                    full_el = item.select_one("span.ui-search-item__fulfillment-label, span.ui-search-item__fulfillment-label__text")
                    if full_el and "full" in full_el.text.lower():
                        shipping_full = "Sim"
                    elif item.find(string=re.compile(r"FULL", re.IGNORECASE)):
                         shipping_full = "Sim"
                            
                    # Captura da URL da Imagem de Capa
                    image_el = item.select_one("img.ui-search-result-image, img.ui-search-result-grid__image")
                    
                    if image_el:
                        if 'data-src' in image_el.attrs:
                            image_url = image_el['data-src']
                        elif 'src' in image_el.attrs:
                            image_url = image_el['src']
                        
                        if image_url != "N/A":
                             image_url = image_url.replace('-I.webp', '-O.webp').replace('-V.webp', '-O.webp') 
                        
                    all_results.append({
                        "Nome": title,
                        "Preço": price_str,
                        "Vendidos": sold, 
                        "Frete grátis": shipping_gratis,
                        "FULL": shipping_full,
                        "ID MLB": item_id,
                        "Página": page_num + 1,
                        "Link": link,
                        "Capa": image_url, 
                    })
                    
                st.info(f"Página {page_num + 1} de {pages} processada. Aguardando {DELAY_SECONDS}s...")
                time.sleep(DELAY_SECONDS)

            except requests.exceptions.RequestException as e:
                st.error(f"Erro de conexão na página {page_num + 1}: {e}")
                break

    return pd.DataFrame(all_results)

# ================= 4. FUNÇÕES DE ANÁLISE DE MERCADO =================
# Mantidas

def analyze_keywords_8020(df):
    """Identifica os termos mais frequentes nos títulos dos 20% de itens mais vendidos."""
    top_20_count = max(10, int(len(df) * 0.20))
    df_top_vendas = df.sort_values(by='Vendidos_Numérico', ascending=False).head(top_20_count)
    
    all_words = []
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
    
    max_cost_80 = avg_selling_price / (1 + markup_min)
    max_cost_100 = avg_selling_price / (1 + markup_exc)
    
    return avg_selling_price, max_cost_80, max_cost_100

# ================= 5. FUNÇÃO DE EXPORTAÇÃO =================

def convert_df_to_csv(df):
    """Converte o DataFrame para o formato CSV (com separador ; para Excel)"""
    df_export = df.drop(columns=['Vendidos_Numérico', 'Preço Limpo'], errors='ignore')
    return df_export.to_csv(index=False, sep=';', encoding='utf-8-sig')


# ================= 6. INTERFACE STREAMLIT (main) =================

def main():
    st.set_page_config(layout="wide", page_title="Análise de Mercado Livre (Inteligência)")
    st.title("Ferramenta de Análise de Mercado Livre")
    st.markdown("Coleta dados, gera Inteligência de Mercado e **Calcula Lucro Real**.")

    st.sidebar.header("Configuração")
    st.sidebar.warning("ATENÇÃO: Limpe o cache (menu superior direito) após mudar o código!")
    
    # ------------------ ENTRADAS DE CUSTO E PREÇO DE VENDA (NOVAS) ------------------
    st.sidebar.subheader("💰 Simulação de Custo")
    
    cost_price = st.sidebar.number_input(
        "Custo do Produto (CP - R$):", 
        min_value=0.01, 
        value=50.00, 
        step=0.01,
        format="%.2f",
        help="Seu preço de custo de aquisição (sem embalagem/operação)."
    )

    selling_price = st.sidebar.number_input(
        "Preço de Venda (PV - R$):", 
        min_value=0.01, 
        value=100.00,  # Valor inicial padrão 2x CP
        step=0.01,
        format="%.2f",
        help="Preço que você planeja vender o produto."
    )
    
    # Executa o cálculo de precificação
    profit_results = calculate_profit(selling_price, cost_price)
    
    # Exibe o Relatório de Precificação na Sidebar
    st.sidebar.subheader("Resumo de Lucro")
    
    def format_profit(value):
        color = 'green' if value > 0 else 'red'
        return f'<span style="color:{color}; font-weight:bold;">R$ {value:.2f}</span>'

    # Certifica que PV é maior que CP
    if selling_price <= cost_price:
        st.sidebar.error("PV deve ser maior que CP para o cálculo.")
    else:
        st.sidebar.markdown(f"**Custo do Produto (CP):** R$ {cost_price:.2f}")
        st.sidebar.markdown(f"**Preço de Venda (PV):** R$ {selling_price:.2f}")
        
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**Mercado Livre (Taxa: 25%)**")
        st.sidebar.markdown(f"Lucro Líquido: {format_profit(profit_results['Mercado Livre']['Lucro Bruto'])}", unsafe_allow_html=True)
        st.sidebar.markdown(f"Margem: **{profit_results['Mercado Livre']['Margem %']:.1f}%**")
        
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**Shopee (Taxa: 18%)**")
        st.sidebar.markdown(f"Lucro Líquido: {format_profit(profit_results['Shopee']['Lucro Bruto'])}", unsafe_allow_html=True)
        st.sidebar.markdown(f"Margem: **{profit_results['Shopee']['Margem %']:.1f}%**")
        st.sidebar.markdown("---")
    
    # ------------------ CAMPOS DE BUSCA ------------------

    search_term = st.text_input("Termo de Busca:", value="ralo inteligente click inox")
    num_pages = st.number_input("Quantas páginas buscar?", min_value=1, max_value=10, value=1)
    
    sort_option = st.selectbox(
        "Classificar Resultados por:",
        ("Mais Vendido", "Mais Relevante", "Menor Preço")
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
                # 1. Limpeza de Preço (Interno)
                df_results['Preço Limpo'] = (
                    df_results['Preço'].astype(str)
                    .str.replace('.', '', regex=False)
                    .str.replace(',', '.', regex=False)
                    .str.strip()
                )
                df_results['Preço Limpo'] = pd.to_numeric(df_results['Preço Limpo'], errors='coerce')
                
                # 2. CRIAÇÃO: Coluna Vendidos para Numérico
                df_results['Vendidos_Numérico'] = df_results['Vendidos'].apply(clean_sold_data)
                
                # 3. Formatação da coluna 'Vendidos' para exibição
                df_results['Vendidos'] = df_results['Vendidos'].apply(format_sold_data_for_display)

                # 4. Ordenação Final
                df_sorted = df_results.copy()
                if sort_option == "Menor Preço":
                    df_sorted = df_sorted.sort_values(by='Preço Limpo', na_position='last', ascending=True)
                elif sort_option == "Mais Vendido":
                    df_sorted = df_sorted.sort_values(
                        by=['Vendidos_Numérico', 'Preço Limpo'], 
                        ascending=[False, True]
                    )
                
            except Exception as e:
                st.error(f"Erro no pré-processamento dos dados: {e}")
                return

            st.success(f"Encontrados {len(df_results)} anúncios nas primeiras {num_pages} páginas.")
            
            # --- 2. Análise de Palavras-Chave (80/20) e Custo Ideal ---
            st.header("✨ Análise de Inteligência de Mercado")
            
            with st.container():
                keywords_8020, df_top_vendas = analyze_keywords_8020(df_results.copy())
                
                st.subheader("1. 80/20: Palavras-Chave de Alta Conversão (Top 20% Mais Vendidos)")
                
                if keywords_8020 and df_top_vendas['Vendidos_Numérico'].sum() > 0:
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
                                help="Seu preço de compra não deve exceder este valor para obter pelo menos 80% de Markup.")
                                
                    col3.metric("Custo Máximo (Markup 100% - Excelente)", 
                                f"R$ {cost_100:,.2f}", 
                                help="Para atingir 100% de Markup, seu custo de compra não deve exceder este valor."
                                )
                    
                    st.markdown(f"""
                        **Sua Decisão:**
                        * Para vender no preço médio da concorrência (R$ **{avg_price:,.2f}**):
                            * Você precisa comprar o produto por, no máximo, R$ **{cost_80:,.2f}** para ter um markup de 80%.
                            * Você precisa comprar o produto por, no máximo, R$ **{cost_100:,.2f}** para ter um markup de 100%.
                    """)
                else:
                    st.warning("Não foi possível calcular o preço de custo ideal.")


            # --- 4. Tabela de Dados Brutos ---
            st.header("📊 Dados Detalhados Coletados")
            
            # Botão de Exportação
            csv = convert_df_to_csv(df_sorted.head(num_pages * 48))
            
            st.download_button(
                label="⬇️ Exportar Tabela para CSV (Excel)",
                data=csv,
                file_name=f'analise_ml_{search_term.replace(" ", "_")}.csv',
                mime='text/csv',
                help="Baixa os dados brutos em formato CSV."
            )

            column_configuration = {
                "Capa": st.column_config.ImageColumn(
                    "Capa",
                    help="Imagem de capa do anúncio.",
                    width="small" 
                ),
                "Link": st.column_config.LinkColumn(
                    "Link",
                    display_text="Abrir Anúncio",
                    width="small"
                ),
            }
            
            # Exibe o DataFrame classificado
            st.dataframe(
                df_sorted.head(num_pages * 48), 
                column_config=column_configuration, 
                use_container_width=True, 
                column_order=['Capa', 'Nome', 'Preço', 'Vendidos', 'Frete grátis', 'FULL', 'ID MLB', 'Página', 'Link'],
                hide_index=True
            )
        
        else:
            st.warning("Nenhum resultado encontrado. Tente um termo diferente.")

if __name__ == '__main__':
    main()