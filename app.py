import requests
import pandas as pd
from urllib.parse import quote_plus

# A URL base do Mercado Livre. O endpoint /search que você está usando é público (não requer token)
ML_API_BASE = "https://api.mercadolibre.com"
ML_SITE = "MLB" # Para Mercado Livre Brasil

class MercadoLivreSearcher:
    """
    Classe para encapsular a lógica de busca, filtragem e ordenação de produtos
    no Mercado Livre, replicando a funcionalidade do código VBA.
    """
    
    def __init__(self, access_token=None):
        """
        Inicializa o objeto. Um access_token pode ser incluído para 
        futuras requisições autenticadas (como em /items para alguns detalhes).
        """
        self.headers = {
            'Authorization': f'Bearer {access_token}' if access_token else '',
            'Content-Type': 'application/json'
        }
        
    def _fetch_page(self, query: str, offset: int = 0) -> dict:
        """Faz a chamada à API do Mercado Livre para uma página específica."""
        # Codifica a query para ser segura na URL (substitui ' ' por '+')
        safe_query = quote_plus(query)
        
        url = f"{ML_API_BASE}/sites/{ML_SITE}/search?q={safe_query}&offset={offset}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status() # Levanta exceção para erros HTTP (4xx ou 5xx)
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Erro na requisição à API do Mercado Livre: {e}")
            return None

    def search(self, query: str, limit: int, sort_type: str) -> pd.DataFrame:
        """
        Realiza a busca principal e retorna o top N de resultados ordenados.

        Args:
            query (str): O termo de busca.
            limit (int): O número de resultados desejados (N).
            sort_type (str): O critério de ordenação ('price' para menor preço, 
                             'sold_quantity' para maior venda).

        Returns:
            pd.DataFrame: Um DataFrame com os resultados ordenados (Top N).
        """
        
        all_results = []
        offset = 0
        MAX_RESULTS_ML = 1000 # O limite de 1000 resultados do VBA
        
        print(f"Buscando '{query}' - Top {limit} por {sort_type}...")
        
        while offset < MAX_RESULTS_ML and offset < limit + 500: # Adicionando um buffer para o limite
            data = self._fetch_page(query, offset)
            
            if data is None:
                break

            total_items = data['paging'].get('total', 0)
            
            # O VBA faz a busca em múltiplos requests com offset. A API do ML retorna 50 por página
            if not data.get('results'):
                break

            all_results.extend(data['results'])
            
            # Determina o próximo offset para a paginação
            offset += len(data['results'])
            
            # Sai do loop se atingiu o limite de resultados ou o total disponível
            if offset >= total_items or offset >= MAX_RESULTS_ML:
                break
                
            # Limita as requisições se já tivermos resultados suficientes para N
            # Este é um refinamento para não buscar as 1000 páginas se N for pequeno
            if offset >= limit and len(all_results) >= limit * 2 and offset < MAX_RESULTS_ML - 50:
                 # Se já temos o dobro do 'limit' e estamos longe do MAX_RESULTS_ML, podemos parar.
                 # O código VBA continua buscando até 1000 para achar os melhores. Vamos seguir essa lógica.
                 # A forma mais performática é buscar tudo e ordenar, como faremos abaixo.
                 pass

        # === Processamento dos Dados ===

        if not all_results:
            print("Nenhum resultado encontrado.")
            return pd.DataFrame()

        # Converte a lista de dicionários para um DataFrame do pandas
        df = pd.DataFrame(all_results)
        
        # 1. Limpeza e Filtragem (Similar ao 'If JsonPROD("results")(i)("condition") <> "new" Then...')
        # Filtra apenas itens novos
        df_filtered = df[df['condition'] == 'new'].copy()
        
        if df_filtered.empty:
            print("Nenhum produto novo encontrado.")
            return pd.DataFrame()
        
        # 2. Seleção de Colunas e Tratamento
        
        # Colunas relevantes
        if sort_type == 'price':
            cols = ['id', 'title', 'price', 'permalink', 'thumbnail']
            df_final = df_filtered[cols]
            sort_order = True # Preço: Crescente (Menor preço)
        else: # sort_type == 'sold_quantity'
            cols = ['id', 'title', 'sold_quantity', 'permalink']
            df_final = df_filtered[cols]
            sort_order = False # Venda: Decrescente (Maior venda)
            
        # Limpeza do ID (Similar ao 'Replace(interm, "MLB", "")')
        df_final.loc[:, 'id'] = df_final['id'].str.replace('MLB', '')
        
        # 3. Ordenação (Substitui o Bubble Sort do VBA)
        # O Pandas ordena a lista inteira de forma muito mais eficiente
        df_sorted = df_final.sort_values(by=sort_type, ascending=sort_order)

        # 4. Retorna o Top N
        # O .head(limit) substitui toda a lógica de reordenação no loop do VBA
        return df_sorted.head(limit)

# --- Exemplo de Uso/Deploy ---
if __name__ == '__main__':
    # Usando suas "últimas credenciais válidas"
    # Se você está usando um endpoint que requer autenticação, coloque seu Access Token aqui.
    # Exemplo: access_token = "SEU_ACCESS_TOKEN_AQUI"
    # Para o search público, deixamos como None.
    ACCESS_TOKEN = None 

    # Simulação da leitura dos inputs do Excel (C4 e D4/J4)
    QUERY_MENOR_PRECO = "iphone 13 pro max"
    LIMIT_MENOR_PRECO = 10 

    QUERY_MAIOR_VENDA = "máquina de lavar roupa"
    LIMIT_MAIOR_VENDA = 5 
    
    # ---------------------------------------------
    # Exemplo 1: Menor Preço (Similar ao getJSON_ML_Menorpreco)
    # ---------------------------------------------
    searcher = MercadoLivreSearcher(access_token=ACCESS_TOKEN)
    
    top_menor_preco = searcher.search(
        query=QUERY_MENOR_PRECO, 
        limit=LIMIT_MENOR_PRECO, 
        sort_type='price'
    )
    
    print("\n--- Resultados (Menor Preço) ---")
    if not top_menor_preco.empty:
        # Renomeando as colunas para simular o output do VBA: ID, Link, Preço, Título
        top_menor_preco.rename(columns={
            'id': 'ID_MLB',
            'permalink': 'Link',
            'price': 'Preço',
            'title': 'Título'
        }, inplace=True)
        # Selecionando colunas na ordem desejada para o output
        output_cols = ['ID_MLB', 'Link', 'Preço', 'Título', 'thumbnail']
        print(top_menor_preco[output_cols])
        
        # Se você estivesse integrando com o Excel, usaria uma biblioteca 
        # como openpyxl ou pandas.to_excel para escrever esses dados
        # no arquivo, simulando o Range("E" & i + 3) = ...

    # ---------------------------------------------
    # Exemplo 2: Maior Venda (Similar ao getJSON_ML_Maiorvenda)
    # ---------------------------------------------
    
    top_maior_venda = searcher.search(
        query=QUERY_MAIOR_VENDA, 
        limit=LIMIT_MAIOR_VENDA, 
        sort_type='sold_quantity'
    )
    
    print("\n--- Resultados (Maior Venda) ---")
    if not top_maior_venda.empty:
        # Renomeando as colunas para simular o output do VBA: ID, Link, Quantidade, Título
        top_maior_venda.rename(columns={
            'id': 'ID_MLB',
            'permalink': 'Link',
            'sold_quantity': 'Vendas',
            'title': 'Título'
        }, inplace=True)
        # Selecionando colunas na ordem desejada para o output
        output_cols = ['ID_MLB', 'Link', 'Vendas', 'Título']
        print(top_maior_venda[output_cols])