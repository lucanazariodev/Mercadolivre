import streamlit as st
import requests
import pandas as pd
import time 
from urllib.parse import quote_plus

# A URL base e o site para o Mercado Livre (Brasil)
ML_SITE = "MLB"
ML_API_BASE = "https://api.mercadolibre.com"

class MercadoLivreSearcher:
    """
    Classe para encapsular a lógica de busca e paginação na API do Mercado Livre.
    """
    def __init__(self, access_token=None):
        """
        Configura os cabeçalhos com User-Agent e token condicional.
        """
        self.headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'ML-Streamlit-Analysis-App/1.0 (Contato: usuario)' 
        }
        
        if access_token:
             self.headers['Authorization'] = f'Bearer {access_token}'
    
    def _fetch_page(self, query: str, offset: int = 0) -> dict:
        """Faz a chamada à API do Mercado Livre para uma página específica."""
        safe_query = quote_plus(query)
        url = f"{ML_API_BASE}/sites/{ML_SITE}/search?q={safe_query}&offset={offset}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status() 
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Erro na requisição à API do Mercado Livre: {e}")
            return None

    # st.cache_data NÃO DEVE ser usado em um método de classe, pois o Streamlit
    # não consegue fazer o hash do argumento 'self' de forma confiável.
    # Já corrigido para '_self', mas vamos encapsular o cache_data em um helper
    # que usa o 'searcher' como um argumento de estado.
    
    # REMOÇÃO DO CACHE DA CLASSE PARA EVITAR COMPORTAMENTO INESPERADO COM O TOKEN
    def search(self, query: str, limit: int, sort_type: str) -> pd.DataFrame:
        """
        Realiza a busca completa e retorna o Top N de resultados ordenados.
        """
        all_results = []
        offset = 0
        MAX_RESULTS_ML = 1000

        with st.spinner(f"Buscando até {MAX_RESULTS_ML} itens para '{query}'..."):
            
            while offset < MAX_RESULTS_ML: 
                data = self._fetch_page(query, offset)
                
                if data is None:
                    break
                
                # Se for o JSON de tracking/log, ele não tem 'results' e o loop deve parar
                if not data.get('results'):
                    st.warning("A busca parou. Resposta da API não contém resultados (pode ser rate-limiting ou bloqueio).")
                    break

                all_results.extend(data['results'])
                total_items = data['paging'].get('total', 0)
                
                offset += len(data['results'])
                
                if offset >= total_items or offset >= MAX_RESULTS_ML:
                    break
                
                # AUMENTO DO DELAY: 1.0 segundo entre as requisições de página
                if offset < MAX_RESULTS_ML:
                    time.sleep(1.0) 

        if not all_results:
            return pd.DataFrame()

        # === Processamento, Filtragem e Ordenação com Pandas ===
        df = pd.DataFrame(all_results)
        df_filtered = df[df['condition'] == 'new'].copy()
        
        if df_filtered.empty:
            st.warning("Nenhum produto NOVO encontrado. O filtro 'new' foi aplicado.")
            return pd.DataFrame()
        
        # Configuração das colunas de saída
        if sort_type == 'price':
            cols_to_keep = ['id', 'title', 'price', 'permalink'] 
            df_final = df_filtered[cols_to_keep]
            sort_order = True 
            df_final.rename(columns={'price': 'Preço'}, inplace=True)
            sort_column_name = 'Preço'
        else:
            cols_to_keep = ['id', 'title', 'sold_quantity', 'permalink'] 
            df_final = df_filtered[cols_to_keep]
            sort_order = False 
            df_final.rename(columns={'sold_quantity': 'Vendas'}, inplace=True)
            sort_column_name = 'Vendas'
            
        # Limpeza e Renomeação Final
        df_final['id'] = df_final['id'].astype(str).str.replace('MLB', '')
        df_final.rename(columns={
            'id': 'ID_MLB',
            'permalink': 'Link',
            'title': 'Título'
        }, inplace=True)

        df_sorted = df_final.sort_values(by=sort_column_name, ascending=sort_order).head(limit)
        
        return df_sorted

# O Streamlit lida melhor com cache em funções fora da classe
@st.cache_data(ttl=3600)
def cached_search(query, limit, sort_type, access_token_state):
    """Função wrapper para usar o cache do Streamlit de forma segura."""
    # O token é passado como estado para forçar o cache a invalidar se o token mudar
    searcher = MercadoLivreSearcher(access_token=access_token_state)
    return searcher.search(query, limit, sort_type)

# --- Aplicação Streamlit Principal ---
def main():
    st.set_page_config(layout="wide", page_title="Análise Mercado Livre")
    
    st.title("Ferramenta de Análise do Mercado Livre")
    st.markdown("Implementação em Python/Streamlit do seu código VBA para buscar Top N por Preço ou Vendas (Apenas produtos Novos).")

    st.sidebar.header("Configuração de Credenciais")
    st.sidebar.info("A busca de produtos (`/search`) é pública, mas um token válido é essencial para evitar bloqueios.")
    
    ACCESS_TOKEN = st.sidebar.text_input(
        "Access Token (Suas últimas credenciais válidas):", 
        type="password",
        # Use o token como uma chave de estado para forçar a função cacheada a reexecutar
        key='access_token_input'
    )

    # Abas para separar as duas funcionalidades
    tab1, tab2 = st.tabs(["Menor Preço", "Maior Venda"])

    # === Lógica para Menor Preço ===
    with tab1:
        st.header("Menor Preço")
        query_price = st.text_input(
            "Termo de Busca:", 
            "placa de video rtx 3060",
            key='query_price'
        )
        limit_price = st.number_input(
            "Número de Resultados (N):", 
            min_value=1, max_value=200, value=20, step=1,
            key='limit_price'
        )

        if st.button("Buscar Top N por Menor Preço", key='btn_price') and query_price:
            
            # Chama a função cacheada, passando o token como argumento de estado
            top_menor_preco = cached_search(
                query=query_price, 
                limit=limit_price, 
                sort_type='price',
                access_token_state=ACCESS_TOKEN
            )
            
            if not top_menor_preco.empty:
                st.success(f"Top {limit_price} produtos Novos, ordenados por Menor Preço:")
                
                display_df = top_menor_preco[['ID_MLB', 'Link', 'Preço', 'Título']].copy()
                
                display_df['Preço'] = display_df['Preço'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            

    # === Lógica para Maior Venda ===
    with tab2:
        st.header("Maior Venda")
        query_sales = st.text_input(
            "Termo de Busca:", 
            "cadeira gamer",
            key='query_sales'
        )
        limit_sales = st.number_input(
            "Número de Resultados (N):", 
            min_value=1, max_value=200, value=20, step=1,
            key='limit_sales'
        )

        if st.button("Buscar Top N por Maior Venda", key='btn_sales') and query_sales:
            
            # Chama a função cacheada, passando o token como argumento de estado
            top_maior_venda = cached_search(
                query=query_sales, 
                limit=limit_sales, 
                sort_type='sold_quantity',
                access_token_state=ACCESS_TOKEN
            )
            
            if not top_maior_venda.empty:
                st.success(f"Top {limit_sales} produtos Novos, ordenados por Maior Vendas:")
                
                display_df = top_maior_venda[['ID_MLB', 'Link', 'Vendas', 'Título']].copy()
                display_df['Vendas'] = display_df['Vendas'].astype(int)
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
if __name__ == '__main__':
    main()