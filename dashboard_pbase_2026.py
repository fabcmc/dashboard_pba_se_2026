"""
PBA SE 2026 - Dashboard de Monitoramento Pedagógico
Objetivo: Acompanhar o engajamento (frequência) e a evolução da aprendizagem.
Framework: Streamlit + Pandas + Plotly
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json
import io

# =============================================================================
# 1. CONFIGURAÇÕES GERAIS E CONSTANTES (O topo do arquivo)
# =============================================================================
st.set_page_config(page_title="PBA SE 2026 | Monitoramento", page_icon="📊", layout="wide")

COLORS = {
    "primary": "#004A8F", "secondary": "#00A859", 
    "risco_alto": "#E52207", "risco_medio": "#F2A900",
    "niveis": {"N1": "#E52207", "N2": "#F2A900", "N3": "#85C441", "N4": "#00A859", "Pendente": "#BDBDBD"}
}

GOVERNANCA_CONSULTOR = dict(st.secrets["governanca_consultor"])

GOVERNANCA_ESPECIALISTA = dict(st.secrets["governanca_especialista"])

# =============================================================================
# 2. FUNÇÕES AUXILIARES DE NEGÓCIO E UI (Clean Code)
# =============================================================================
def extrair_dificuldades(valor):
    if pd.isna(valor): return []
    texto = str(valor).strip()
    if not texto or texto.lower() == 'nan': return []
    try:
        texto = texto.replace('""', '"')
        return [str(item).strip() for item in json.loads(texto) if str(item).strip()]
    except:
        limpo = texto.replace('[', '').replace(']', '').replace('"', '').replace("'", "")
        return [item.strip() for item in limpo.split(',') if item.strip()]

def criar_grafico_rosca(df_dados, coluna_dados, titulo, mapeamento, cores):
    s_map = df_dados[coluna_dados].map(mapeamento).fillna('Não Informado')
    s_map = s_map[s_map != 'Não Informado']
    contagem = s_map.value_counts().reset_index()
    contagem.columns = ['Categoria', 'Quantidade']
    
    fig = px.pie(
        contagem, names='Categoria', values='Quantidade', 
        color='Categoria', color_discrete_map=cores, title=titulo, hole=0.4
    )
    fig.update_traces(textposition='inside', textinfo='percent')
    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5),
        title_x=0.5, height=350, margin=dict(t=40, b=0, l=10, r=10)
    )
    return fig

def aplicar_estilo_tabela(df):
    styler = df.style
    
    # Regra de cores de alerta
    def estilo_alerta(valor):
        if not isinstance(valor, str):
            return ''
            
        # Nível Crítico (Vermelho) - Inclui o Possível Desistente e as Notas N1/N2
        if valor == 'Possível desistente' or valor in ['N1', 'N2']:
            return 'background-color: #FFCDD2; color: #B71C1C; font-weight: bold;'
            
        # Nível Atenção (Amarelo) - O Alto Risco passa a ser amarelo
        elif valor == 'Alto risco':
            return 'background-color: #FFF2CC; color: #D48806; font-weight: bold;'
            
        return ''
    
    # Aplica nas colunas de Alerta e nas colunas de Formativas
    colunas_alerta = [col for col in ['Alerta de Risco', 'Form. 1', 'Form. 2', 'Form. 3', 'Form. 4'] if col in df.columns]
    
    if colunas_alerta:
        try:
            styler = styler.map(estilo_alerta, subset=colunas_alerta)
        except AttributeError:
            styler = styler.applymap(estilo_alerta, subset=colunas_alerta)
            
    return styler

def limpar_filtros():
    st.session_state['filtro_fase'] = 'Todas'
    for chave in ['filtro_municipio', 'filtro_cons', 'filtro_esp', 'filtro_coord', 'filtro_alfab']:
        st.session_state[chave] = 'Todos'
    st.session_state['filtro_turma'] = 'Todas'

# =============================================================================
# 3. EXTRAÇÃO E TRANSFORMAÇÃO DE DADOS (ETL)
# =============================================================================
@st.cache_data(ttl=1800, show_spinner="Diagnosticando conexão com as bases de dados...")
def carregar_dados():
    # PROTEÇÃO DE DADOS: Consumindo os dois links de forma segura
    url_json_alfab = st.secrets["LINK_JSON_ALFABETIZANDOS"] 
    url_json_turmas = st.secrets["LINK_JSON_TURMAS"]
    
    # --- TESTE 1: BASE DE ALFABETIZANDOS ---
    try:
        df_alfab = pd.read_json(url_json_alfab)
        df_alfab.columns = df_alfab.columns.str.lower().str.strip()
    except Exception as e:
        st.error(f"❌ ERRO NA BASE DE ALFABETIZANDOS: O link fornecido não retornou um JSON válido. Detalhe técnico: {e}")
        st.stop()
        
    # --- TESTE 2: BASE DE TURMAS ---
    try:
        df_turmas = pd.read_json(url_json_turmas)
        df_turmas.columns = df_turmas.columns.str.lower().str.strip()
    except Exception as e:
        st.error(f"❌ ERRO NA BASE DE TURMAS: O link fornecido não retornou um JSON válido. Detalhe técnico: {e}")
        st.stop()
        
    # --- TESTE 3: CRUZAMENTO DOS DADOS (MERGE) ---
    try:
        colunas_duplicadas = [col for col in df_turmas.columns if col in df_alfab.columns and col != 'ds_turma']
        df_turmas_limpo = df_turmas.drop(columns=colunas_duplicadas)
        
        df_merged = pd.merge(df_alfab, df_turmas_limpo, left_on='turma', right_on='ds_turma', how='left')
        return df_merged
    except Exception as e:
        st.error(f"❌ ERRO NO CRUZAMENTO DAS BASES: Detalhe técnico: {e}")
        st.stop()

@st.cache_data(show_spinner="Aplicando regras operacionais...")
def processar_regras_negocio(df):
    df_clean = df.copy()
    if 'dt_inicio' in df_clean.columns:
        # 1. Converte texto (DD/MM/YYYY) para objeto de data oficial do Pandas. 
        # errors='coerce' transforma erros (ex: texto vazio) em 'NaT' (Not a Time) para não quebrar o código.
        df_clean['dt_inicio'] = pd.to_datetime(df_clean['dt_inicio'], format='%d/%m/%Y', errors='coerce')
        
        # 2. Extrai o mês e ano
        mes = df_clean['dt_inicio'].dt.month
        ano = df_clean['dt_inicio'].dt.year
        
        # 3. Motor de categorização
        condicoes_fase = [
            (mes == 4) & (ano == 2026),
            (mes == 8) & (ano == 2026),
            (mes == 9) & (ano == 2026)
        ]
        valores_fase = ['Fase I', 'Fase II', 'Aditivo']
        
        df_clean['fase_programa'] = np.select(condicoes_fase, valores_fase, default='Sem Previsão')
    else:
        df_clean['fase_programa'] = 'Sem Previsão'
    # ---------------------------------------------------------

    if 'turma' in df_clean.columns:
        df_clean = df_clean[~df_clean['turma'].str.contains('TURMA-P0000247-0001', case=False, na=False)]

    if 'qtd_presenca_alfabetizando' in df_clean.columns and 'qtd_aulas_dadas_turma' in df_clean.columns:
        df_clean['taxa_frequencia'] = (df_clean['qtd_presenca_alfabetizando'] / df_clean['qtd_aulas_dadas_turma'].replace(0, 1)) * 100
        df_clean['taxa_frequencia'] = df_clean['taxa_frequencia'].fillna(0).round(2)
        
        # Estabelecendo regras de risco de evasão com base na frequência e status do alfabetizando
        condicoes = [
            (df_clean['taxa_frequencia'] < 50) & (df_clean['status_alfabetizando'] != 'EVADIDO'),
            (df_clean['taxa_frequencia'] < 75) & (df_clean['status_alfabetizando'] != 'EVADIDO')
        ]
        valores = ['Possível desistente', 'Alto risco']
        
        # Se for < 50, aplica o primeiro. Se for < 75, aplica o segundo. O resto vira 'Adequado'.
        df_clean['risco_frequencia'] = np.select(condicoes, valores, default='Adequado')

    colunas_result = [col for col in df_clean.columns if col.endswith('_result') and 'socio' not in col]
    for col in colunas_result:
        df_clean[f"{col}_nivel"] = df_clean[col].fillna('Pendente').apply(lambda x: str(x)[:2] if str(x).strip().startswith('N') else 'Pendente')

    if 'coordenador' in df_clean.columns:
        df_clean['consultor'] = df_clean['coordenador'].astype(str).str.upper().str.strip().map(GOVERNANCA_CONSULTOR).fillna('Não Atribuído')
        df_clean['especialista'] = df_clean['coordenador'].astype(str).str.upper().str.strip().map(GOVERNANCA_ESPECIALISTA).fillna('Não Atribuído')

    return df_clean

@st.cache_data(show_spinner="Calculando Índices de Proficiência...")
def calcular_ipa_dinamico(df):
    df_ipa = df.copy()
    CONFIG_IPA = {
        1: {'tetos': {'ol': 32.0, 'pe': 32.0, 'al': 20.0}, 'questoes': {'ol': [1,2,3,4,5], 'pe': [1,2,3,4,5], 'al': [2,5]}},
        2: {'tetos': {'ol': 12.0, 'pe': 14.0, 'al': 18.0}, 'questoes': {'ol': [2,3,4], 'pe': [4,5], 'al': [1,2,3]}},
        3: {'tetos': {'ol': 9.0, 'pe': 27.0, 'al': 5.0}, 'questoes': {'ol': [1,5], 'pe': [2,4,5], 'al': [1,3]}},
        4: {'tetos': {'ol': 14.0, 'pe': 14.0, 'al': 22.0}, 'questoes': {'ol': [1,4,5], 'pe': [3,4,5], 'al': [1,2,3]}}
    }
    PESOS = {'ol': 0.40, 'pe': 0.45, 'al': 0.15}
    limites = [-1.1, 0.0, 1.49, 2.49, 3.49, 4.01]
    rotulos = ['Sem Dados', 'Iniciante', 'Em desenvolvimento', 'Alfabetizado(a)', 'Alfabetização consolidada']

    for eixo in ['ol', 'pe', 'al']: df_ipa[f'ipa_{eixo}_base'] = 1.0

    for form_id, regras in CONFIG_IPA.items():
        prefix = f'forma_{form_id}'
        if f'{prefix}_result_nivel' in df_ipa.columns:
            questoes_ids = set(regras['questoes']['ol'] + regras['questoes']['pe'] + regras['questoes']['al'])
            for q in questoes_ids: df_ipa[f'{prefix}_q{q}_calc'] = pd.to_numeric(df_ipa.get(f'{prefix}_q{q}', 0), errors='coerce').fillna(0)
            
            s_percent = {eixo: df_ipa[[f'{prefix}_q{q}_calc' for q in regras['questoes'][eixo]]].sum(axis=1) / regras['tetos'][eixo] for eixo in ['ol', 'pe', 'al']}
            filtro_realizou = df_ipa[f'{prefix}_result_nivel'] != 'Pendente'
            
            for eixo in ['ol', 'pe', 'al']:
                base_col = f'ipa_{eixo}_base' if form_id == 1 else f'ipa_{eixo}_forma_{form_id - 1}'
                col_ipa_eixo = f'ipa_{eixo}_forma_{form_id}'
                df_ipa.loc[filtro_realizou, col_ipa_eixo] = np.maximum(df_ipa.loc[filtro_realizou, base_col], form_id * s_percent[eixo][filtro_realizou])
                df_ipa[col_ipa_eixo] = df_ipa.get(col_ipa_eixo, pd.Series(0, index=df_ipa.index)).fillna(0)
                
            col_valor = f'ipa_{prefix}_valor'
            df_ipa.loc[filtro_realizou, col_valor] = sum(df_ipa.loc[filtro_realizou, f'ipa_{eixo}_forma_{form_id}'] * PESOS[eixo] for eixo in ['ol', 'pe', 'al']).round(2)
            df_ipa[col_valor] = df_ipa.get(col_valor, pd.Series(-1, index=df_ipa.index)).fillna(-1)
            df_ipa[f'ipa_{prefix}_classificacao'] = pd.cut(df_ipa[col_valor], bins=limites, labels=rotulos)
            
            df_ipa = df_ipa.drop(columns=[f'{prefix}_q{q}_calc' for q in questoes_ids])

    return df_ipa.drop(columns=['ipa_ol_base', 'ipa_pe_base', 'ipa_al_base'], errors='ignore')

# Execução do Motor de Dados
df_bruto = carregar_dados()
df_final = calcular_ipa_dinamico(processar_regras_negocio(df_bruto))


# =============================================================================
# 4. RENDERIZAÇÃO DA INTERFACE (UI)
# =============================================================================
st.title("📊 Painel de Monitoramento - Alfabetiza Sergipe 2026")
st.markdown("Acompanhamento de indicadores educacionais")

# FILTROS LATERAIS
st.sidebar.markdown("---")
st.sidebar.header("🎛️ Filtros de Análise")

# 1. Inicializamos a memória incluindo o filtro_fase
if 'filtro_fase' not in st.session_state: st.session_state['filtro_fase'] = 'Todas'
for key in ['filtro_municipio', 'filtro_cons', 'filtro_esp', 'filtro_coord', 'filtro_alfab']:
    if key not in st.session_state: st.session_state[key] = 'Todos'
if 'filtro_turma' not in st.session_state: st.session_state['filtro_turma'] = 'Todas'

st.sidebar.button("🔄 Limpar Todos os Filtros", on_click=limpar_filtros, use_container_width=True)

df_filtrado = df_final.copy()

# 2. Adicionamos a tupla da Fase no topo da lista inteligente de filtros
filtros = [
    ('fase_programa', 'Fase do Programa:', 'filtro_fase', 'Todas'),
    ('turma_municipio', 'Município:', 'filtro_municipio', 'Todos'),
    ('consultor', 'Consultor:', 'filtro_cons', 'Todos'),
    ('especialista', 'Especialista:', 'filtro_esp', 'Todos'),
    ('coordenador', 'Coordenador:', 'filtro_coord', 'Todos'),
    ('alfabetizador', 'Alfabetizador:', 'filtro_alfab', 'Todos'),
    ('turma', 'Turma:', 'filtro_turma', 'Todas')
]

for col, label, key, default in filtros:
    opcoes = [default] + sorted(df_filtrado[col].dropna().unique().tolist()) if col in df_filtrado.columns else [default]
    selecionado = st.sidebar.selectbox(label, opcoes, key=key)
    if selecionado != default: df_filtrado = df_filtrado[df_filtrado[col] == selecionado]

st.sidebar.info(f"Mostrando dados de **{df_filtrado.shape[0]}** alfabetizandos matriculados.")

# =============================================================================
# SEPARAÇÃO DINÂMICA: VIGENTES VS ENCERRADAS E MATRICULADOS VS ATIVOS
# =============================================================================
# 1. Identificamos as turmas por status (obedecendo aos filtros laterais)
if 'situacao_turma' in df_filtrado.columns:
    mascara_encerrada = df_filtrado['situacao_turma'] == 'Encerrada'
    mascara_concluida = df_filtrado['situacao_turma'] == 'Concluída'
    mascara_inativas = mascara_encerrada | mascara_concluida # Une as duas para limpar a base principal
else:
    # Fallback de segurança
    mascara_encerrada = pd.Series(False, index=df_filtrado.index)
    mascara_concluida = pd.Series(False, index=df_filtrado.index)
    mascara_inativas = pd.Series(False, index=df_filtrado.index)

# Contagem independente para os KPIs
qtd_encerradas_dinamica = df_filtrado[mascara_encerrada]['turma'].nunique()
qtd_concluidas_dinamica = df_filtrado[mascara_concluida]['turma'].nunique()

# 2. O painel principal (frequência, notas) só deve avaliar as turmas vigentes (nem encerradas, nem concluídas)
df_vigentes = df_filtrado[~mascara_inativas]
df_reais = df_filtrado[~mascara_encerrada]

# 3. Calculamos os alunos ativos (excluindo os evadidos) apenas das turmas vigentes
df_ativos = df_reais[df_reais['status_alfabetizando'] != 'EVADIDO'].copy()
df_em_funcionamento = df_vigentes[df_vigentes['status_alfabetizando'] != 'EVADIDO'].copy()

total_mat = df_filtrado.shape[0]
total_atv = df_ativos.shape[0]
total_curso = df_vigentes.shape[0]
evadidos = total_mat - total_atv

# =============================================================================
# INDICADORES GERAIS (KPIS)
# =============================================================================
st.markdown("---")
st.subheader("🎯 Visão Geral, Engajamento e Retenção")

possiveis_desistentes = df_ativos[df_ativos['taxa_frequencia'] < 50].shape[0]

# Dividindo o topo em 8 colunas agora
c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns(9)

c1.metric("Total Inscritos", f"{total_mat}")
c2.metric("Alunos Matriculados", f"{total_atv}")
c3.metric("Alunos em Curso", f"{total_curso}")

c4.metric(
    "Taxa Desistência", 
    f"{(evadidos/total_mat*100) if total_mat > 0 else 0:.1f}%", 
    f"{evadidos} evadidos" if evadidos > 0 else "Nenhuma", 
    delta_color="inverse"
)

c5.metric(
    "Possíveis Desistentes", 
    f"{possiveis_desistentes}", 
    "Ação Imediata" if possiveis_desistentes > 0 else "Estável", 
    delta_color="inverse"
)

c6.metric("Frequência Média", f"{df_ativos['taxa_frequencia'].mean() if total_atv > 0 else 0:.1f}%")

c7.metric("Turmas Ativas", f"{df_vigentes['turma'].nunique()}")

# KPI de Turmas Encerradas (Neutro/Atenção)
c8.metric(
    "Turmas Encerradas", 
    f"{qtd_encerradas_dinamica}", 
    "Interrompidas" if qtd_encerradas_dinamica > 0 else "", 
    delta_color="off"
)

# NOVO KPI: Turmas Concluídas (Sucesso)
c9.metric(
    "Turmas Concluídas", 
    f"{qtd_concluidas_dinamica}", 
    "Ciclo Finalizado" if qtd_concluidas_dinamica > 0 else "", 
    delta_color="normal" # "normal" deixará a seta/legenda verde, indicando positividade!
)

# DEMOGRÁFICO E TERRITORIAL
if 'turma_municipio' in df_ativos.columns and 'dt_nascimento' in df_ativos.columns:
    st.markdown("---")
    st.subheader("🗺️ Visão Territorial e Perfil Demográfico")
    cd1, cd2 = st.columns([1, 2])
    
    with cd1:
            df_idade = df_ativos.copy()
            
            # Correção 1: Adição do format='%d/%m/%Y' para remover o UserWarning
            df_idade['dt_nascimento'] = pd.to_datetime(df_idade['dt_nascimento'], format='%d/%m/%Y', errors='coerce')
            
            # Correção 2: Cálculo seguro de idade (Ano atual - Ano de nascimento) 
            ano_atual = pd.Timestamp.now().year
            df_idade['idade'] = ano_atual - df_idade['dt_nascimento'].dt.year
            
            rotulos_idade = ['15 a 24 anos', '25 a 34 anos', '35 a 44 anos', '45 a 54 anos', '55 a 64 anos', '65 a 74 anos', '75 anos ou mais']
            
            # Se alguma idade "maluca" resultar em 1000 anos, o pd.cut simplesmente a ignorará, 
            # protegendo o nosso gráfico de rosca de dados irreais.
            df_idade['faixa_etaria'] = pd.cut(df_idade['idade'], bins=[14, 24, 34, 44, 54, 64, 74, 150], labels=rotulos_idade)
            cont_idade = df_idade['faixa_etaria'].value_counts().reset_index().rename(columns={'index':'Faixa Etária', 'faixa_etaria': 'Faixa Etária', 'count': 'Quantidade'})
            
            fig_idade = px.pie(cont_idade, names='Faixa Etária', values='Quantidade', hole=0.4, title="Faixa Etária", color_discrete_sequence=px.colors.sequential.Teal)
            fig_idade.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5))
            st.plotly_chart(fig_idade, use_container_width=True)

    with cd2:
        df_muni = df_ativos.groupby('turma_municipio').agg(total_alunos=('alfabetizando', 'count'), total_turmas=('turma', 'nunique')).reset_index().sort_values('total_alunos')
        fig_muni = px.bar(df_muni, y='turma_municipio', x='total_alunos', orientation='h', title="Alfabetizandos e Turmas por Município", text='total_alunos', hover_data={'total_turmas': True, 'turma_municipio': False}, color_discrete_sequence=[COLORS['primary']])
        fig_muni.update_layout(height=max(400, len(df_muni)*35), xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig_muni, use_container_width=True)

# =============================================================================
# SOCIOEMOCIONAL (DINÂMICO)
# =============================================================================
st.markdown("---")
# 1. Alteração do título conforme solicitado
st.subheader("🧠 Contexto Socioemocional")

# 2. Criando o Dropdown para selecionar o momento da avaliação
tipo_socio = st.selectbox(
    "Selecione a Avaliação Socioemocional:", 
    ["Socioemocional de Entrada", "Socioemocional de Saída"]
)

# Definindo qual será o prefixo a ser procurado nas colunas do Pandas
prefixo_socio = 'socio_entr' if tipo_socio == "Socioemocional de Entrada" else 'socio_said'

# Verifica se pelo menos a Q1 da avaliação selecionada está presente na base
if f'{prefixo_socio}_q1' not in df_ativos.columns:
    st.info(f"Os dados da {tipo_socio} não estão disponíveis para este filtro ou ainda não foram carregados.")
else:
    # 3. Dicionário de Mapeamento Unificado (Baseado no .txt fornecido)
    # Corrigi pequenos erros de digitação (ex: 'Demosntra') para garantir qualidade visual
    mapeamento_textos = {
        # Variáveis da Socioemocional de Entrada
        'Demonstra motivação constante e desejo de continuar estudando': 'Demonstra motivação',
        'Demonstra interesse, mas com oscilações': 'Demonstra interesse',
        'Demonstra desmotivação ou desejo de interromper': 'Demonstra desmotivação',
        'São frequentes e pontuais': 'Frequentes e pontuais',
        'Frequência regular sem nenhuma falta': 'Frequência sem faltas',
        'Frequência regular com algumas faltas': 'Frequência com faltas',
        'Realiza com alguma ajuda': 'Realiza com ajuda',
        'Realiza com autonomia na maioria das situações': 'Realiza com autonomia',
        'Depende de ajuda constante': 'Depende de ajuda',
        'Tenta com apoio e incentivo': 'Tenta com apoio',
        'Tenta com iniciativa própria': 'Tenta com iniciativa',
        'Demonstra insegurança e evita tentar': 'Demonstra insegurança',
        'Persiste e aceita o erro como parte da aprendizagem': 'Persiste e aceita o erro',
        'Persiste, mas demonstra frustração': 'Persiste com frustração',
        'Desiste facilmente': 'Desiste facilmente',
        'Participa ativamente e coopera com os colegas': 'Participa e coopera',
        'Participa quando estimulado(a)': 'Participa quando estimulado(a)',
        'Evita interações': 'Evita interações',
        'Reconhece claramente e relata usos práticos': 'Reconhece claramente',
        'Reconhece em algumas situações': 'Reconhece algumas vezes',
        'Não reconhece': 'Não reconhece',
        
        # Variáveis da Socioemocional de Saída
        'Boa motivação e interesse constante': 'Boa motivação e interesse',
        'Baixa motivação e risco de evasão': 'Baixa motivação',
        'Frequência regular e boa permanência': 'Frequência e permanente',
        'Frequência irregular e evasões significativas': 'Frequência irregular',
        'Realizou com autonomia em várias situações': 'Realizou com autonomia',
        'Realizou com alguma ajuda': 'Realizou com ajuda',
        'Dependeu de ajuda constante': 'Dependeu de ajuda',
        'Demonstrou iniciativa e envolvimento': 'Demonstrou iniciativa',
        'Tentou com incentivo': 'Tentou com incentivo',
        'Demonstrou insegurança e resistência': 'Insegurança e resistência',
        'Persistiu e compreendeu o erro como parte da aprendizagem': 'Persistiu e superou',
        'Persistiu com apoio': 'Persistiu com apoio',
        'Desistiu com facilidade': 'Desistiu facilmente',
        'Participou e cooperou ativamente com os colegas': 'Participou ativamente',
        'Interagiu quando estimulado(a)': 'Interagiu sob estimulação',
        'Apresentou pouca interação': 'Pouca interação',
        'Reconhecimento claro e frequente com usos práticos': 'Reconhecimento frequente',
        'Reconhecimento parcial': 'Reconhecimento parcial',
        'Pouco reconhecimento': 'Pouco reconhecimento',
        'Predominância nos níveis mais avançados': 'Níveis avançados',
        'Distribuição equilibrada entre níveis': 'Distribuição entre níveis',
        'Predominância nos níveis iniciais': 'Níveis iniciais'
    }
    
    # Atribuição Semântica de Cores (Positivo = Verde, Neutro = Amarelo, Crítico = Vermelho)
    cores_socio = {k: COLORS['secondary'] for k in [
        'Demonstra motivação', 'Frequentes e pontuais', 'Frequência sem faltas', 'Realiza com autonomia',
        'Tenta com iniciativa', 'Persiste e aceita o erro', 'Participa e coopera', 'Reconhece claramente',
        'Boa motivação e interesse', 'Frequência e permanente', 'Realizou com autonomia', 'Demonstrou iniciativa',
        'Persistiu e superou', 'Participou ativamente', 'Reconhecimento frequente', 'Níveis avançados'
    ]}
    cores_socio.update({k: COLORS['risco_medio'] for k in [
        'Demonstra interesse', 'Frequência com faltas', 'Realiza com ajuda', 'Tenta com apoio',
        'Persiste com frustração', 'Participa quando estimulado(a)', 'Reconhece algumas vezes',
        'Realizou com ajuda', 'Tentou com incentivo', 'Persistiu com apoio', 'Interagiu sob estimulação',
        'Reconhecimento parcial', 'Distribuição entre níveis'
    ]})
    cores_socio.update({k: COLORS['risco_alto'] for k in [
        'Demonstra desmotivação', 'Depende de ajuda', 'Demonstra insegurança', 'Desiste facilmente',
        'Evita interações', 'Não reconhece', 'Baixa motivação', 'Frequência irregular', 'Dependeu de ajuda',
        'Insegurança e resistência', 'Desistiu facilmente', 'Pouca interação', 'Pouco reconhecimento',
        'Níveis iniciais'
    ]})

    # Titulos generalistas que funcionam perfeitamente para Entrada e Saída
    titulos = ["1. Motivação", "2. Assiduidade", "3. Autonomia", "4. Iniciativa", "5. Persistência", "6. Participação", "7. Usos Práticos", "8. Aquisição (Letramento)"]
    
    # Descobre quantas perguntas de múltipla escolha (rosca) nós temos para o momento selecionado (Q1 até Q8)
    cols_validas = [f'{prefixo_socio}_q{i}' for i in range(1, 9) if f'{prefixo_socio}_q{i}' in df_ativos.columns]

    # Renderização da Linha 1 (Sempre 4 gráficos)
    if len(cols_validas) > 0:
        st.markdown("<br>", unsafe_allow_html=True)
        c_l1 = st.columns(4)
        for i in range(min(4, len(cols_validas))):
            with c_l1[i]: 
                st.plotly_chart(criar_grafico_rosca(df_ativos, cols_validas[i], titulos[i], mapeamento_textos, cores_socio), use_container_width=True)

    # Renderização da Linha 2 (Dinâmica: 3 gráficos centralizados OU 4 gráficos distribuídos)
    if len(cols_validas) > 4:
        st.markdown("<br>", unsafe_allow_html=True)
        resto = len(cols_validas) - 4
        
        if resto == 3:
            # Layout especial [0.5, 1, 1, 1, 0.5] para centralizar os 3 gráficos restantes (Entrada)
            c_l2 = st.columns([0.5, 1, 1, 1, 0.5])
            for i in range(4, 7):
                with c_l2[i-3]: 
                    st.plotly_chart(criar_grafico_rosca(df_ativos, cols_validas[i], titulos[i], mapeamento_textos, cores_socio), use_container_width=True)
        else:
            # Layout padrão para os 4 gráficos restantes (Saída)
            c_l2 = st.columns(4)
            for i in range(4, min(8, len(cols_validas))):
                with c_l2[i-4]:
                    st.plotly_chart(criar_grafico_rosca(df_ativos, cols_validas[i], titulos[i], mapeamento_textos, cores_socio), use_container_width=True)

    # Gráfico Final: Dificuldades (Sempre é a Questão 9, independentemente se é entrada ou saída)
    col_q9 = f'{prefixo_socio}_q9'
    if col_q9 in df_ativos.columns:
        df_dif = df_ativos[[col_q9]].copy()
        df_dif['lista'] = df_dif[col_q9].apply(extrair_dificuldades)
        cont_dif = df_dif.explode('lista').dropna(subset=['lista'])['lista'].value_counts().reset_index().rename(columns={'lista':'Dificuldade', 'count':'Qtd'})
        cont_dif = cont_dif[cont_dif['Dificuldade'] != '']
        
        if not cont_dif.empty:
            fig_dif = px.bar(
                cont_dif, y='Dificuldade', x='Qtd', orientation='h', 
                title="Mapeamento de Desafios Relatados (Questão 9)", 
                text_auto=True, height=500, color_discrete_sequence=[COLORS['primary']]
            )
            fig_dif.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig_dif, use_container_width=True)

# AVALIAÇÕES E PROFICIÊNCIA
col_niveis = [col for col in df_ativos.columns if col.endswith('_result_nivel')]
if col_niveis:
    st.markdown("---")
    st.subheader("📈 Desempenho e Aplicação de Avaliações")
    dic_aval = {'diag_entr_result_nivel': 'Diagnóstica', 'forma_1_result_nivel': 'Formativa 1', 'forma_2_result_nivel': 'Formativa 2', 'forma_3_result_nivel': 'Formativa 3', 'forma_4_result_nivel': 'Formativa 4', 'diag_said_result_nivel': 'Saída'}
    opc_aval = {k: v for k, v in dic_aval.items() if k in col_niveis}
    aval_sel = st.selectbox("Selecione a Avaliação:", options=list(opc_aval.keys()), format_func=lambda x: opc_aval[x])
    
    ca1, ca2, ca3 = st.columns(3)
    
    with ca1:
        df_niv = df_ativos.copy()
        df_niv[aval_sel] = df_niv[aval_sel].replace({'Pendente': 'Sem dados'})
        cont_niv = df_niv[aval_sel].value_counts().reset_index().rename(columns={aval_sel: 'Nível', 'count': 'Qtd'})
        cont_niv['Nível'] = pd.Categorical(cont_niv['Nível'], categories=['N1','N2','N3','N4','Sem dados'], ordered=True)
        fig_n = px.bar(cont_niv.sort_values('Nível'), x='Nível', y='Qtd', color='Nível', color_discrete_map=COLORS['niveis'], text_auto=True, title=f"Níveis - {opc_aval[aval_sel]}")
        fig_n.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Alfabetizandos")
        st.plotly_chart(fig_n, use_container_width=True)
        
    with ca2:
        df_stat = df_ativos.copy()
        df_stat['Status'] = df_ativos[aval_sel].apply(lambda x: 'Pendente' if x == 'Pendente' or x == 'Sem dados' else 'Realizada')
        cont_stat = df_stat['Status'].value_counts().reset_index().rename(columns={'Status': 'Status', 'count': 'Qtd'})
        fig_s = px.pie(cont_stat, names='Status', values='Qtd', color='Status', color_discrete_map={'Realizada': COLORS['primary'], 'Pendente': COLORS['niveis']['Pendente']}, title=f"Cobertura (Alfabetizandos)", hole=0.4)
        st.plotly_chart(fig_s, use_container_width=True)

    # Lógica Avançada de Cobertura de Turmas (Agrupamento e Cálculo de Porcentagem)
    df_cobertura = df_ativos.groupby(['turma_municipio', 'turma', 'coordenador', 'alfabetizador'])[aval_sel].agg(
        Total_Alunos='count',
        Realizados=lambda x: sum((x != 'Pendente') & (x != 'Sem dados'))
    ).reset_index()
    
    # Cálculo da Taxa de Cobertura (%)
    df_cobertura['Taxa_Cobertura'] = (df_cobertura['Realizados'] / df_cobertura['Total_Alunos']) * 100
    df_cobertura['Status'] = df_cobertura['Realizados'].apply(lambda x: 'Realizada' if x > 0 else 'Pendente')

    with ca3:
        cont_turma_stat = df_cobertura['Status'].value_counts().reset_index().rename(columns={'Status': 'Status', 'count': 'Qtd Turmas'})
        fig_ts = px.pie(cont_turma_stat, names='Status', values='Qtd Turmas', color='Status', color_discrete_map={'Realizada': COLORS['primary'], 'Pendente': COLORS['niveis']['Pendente']}, title=f"Cobertura (Turmas)", hole=0.4)
        st.plotly_chart(fig_ts, use_container_width=True)

    # MENUS SANFONA (EXPANDERS) COM AS LISTAS DE AÇÃO
    st.markdown("<br>", unsafe_allow_html=True)
    col_exp1, col_exp2 = st.columns(2)
    
    # Lista 1: Turmas 100% Pendentes
    df_pendentes = df_cobertura[df_cobertura['Status'] == 'Pendente'].copy()
    if not df_pendentes.empty:
        with col_exp1:
            with st.expander(f"🚨 {len(df_pendentes)} turmas com pendência TOTAL (0%)"):
                df_pendentes = df_pendentes[['turma_municipio', 'turma', 'coordenador', 'alfabetizador', 'Total_Alunos']].sort_values('turma_municipio', ascending=True)
                df_pendentes = df_pendentes.rename(columns={'turma_municipio': 'Município', 'turma': 'Turma', 'coordenador': 'Coordenador', 'alfabetizador': 'Alfabetizador', 'Total_Alunos': 'Alfabetizandos'})
                st.dataframe(df_pendentes, use_container_width=True, hide_index=True)

    # Lista 2: Turmas Realizadas (Com percentual de adesão)
    df_realizadas = df_cobertura[df_cobertura['Status'] == 'Realizada'].copy()
    if not df_realizadas.empty:
        with col_exp2:
            with st.expander(f"✅ {len(df_realizadas)} turmas com lançamentos iniciados"):
                # Formatação visual: Arredonda a porcentagem e adiciona o símbolo %
                df_realizadas['Taxa_Cobertura'] = df_realizadas['Taxa_Cobertura'].apply(lambda x: f"{x:.1f}%")
                
                # Ordena da menor cobertura para a maior (para destacar quem lançou pouco)
                df_realizadas = df_realizadas.sort_values('Realizados', ascending=True)
                
                df_realizadas = df_realizadas[['turma_municipio', 'turma', 'coordenador','alfabetizador', 'Realizados', 'Total_Alunos', 'Taxa_Cobertura']].sort_values('turma_municipio', ascending=True)
                df_realizadas = df_realizadas.rename(columns={'turma_municipio': 'Município', 'turma': 'Turma', 'coordenador': 'Coordenador','alfabetizador': 'Alfabetizador', 'Realizados': 'Lançamentos', 'Total_Alunos': 'Total Alfabetizandos', 'Taxa_Cobertura': 'Cobertura (%)'})
                st.dataframe(df_realizadas, use_container_width=True, hide_index=True)


    if 'forma_' in aval_sel:
        col_ipa = f"ipa_{aval_sel.split('_result')[0]}_classificacao"
        if col_ipa in df_ativos.columns:
            st.markdown("---")
            st.subheader(f"🏆 IPA - {opc_aval[aval_sel]}")
            df_ipa = df_ativos[df_ativos[col_ipa] != 'Sem Dados'].copy()
            cont_ipa = df_ipa[col_ipa].value_counts().reset_index().rename(columns={col_ipa: 'IPA', 'count': 'Qtd'})
            cont_ipa['IPA'] = pd.Categorical(cont_ipa['IPA'], categories=['Iniciante', 'Em desenvolvimento', 'Alfabetizado(a)', 'Alfabetização consolidada'], ordered=True)
            
            c_v1, c_ipa, c_v2 = st.columns([1, 4, 1])
            with c_ipa:
                fig_i = px.bar(cont_ipa.sort_values('IPA'), x='IPA', y='Qtd', color='IPA', color_discrete_map={'Iniciante': COLORS['niveis']['N1'], 'Em desenvolvimento': COLORS['niveis']['N2'], 'Alfabetizado(a)': COLORS['niveis']['N3'], 'Alfabetização consolidada': COLORS['niveis']['N4']}, text_auto=True)
                fig_i.update_layout(showlegend=False, xaxis_title=None)
                st.plotly_chart(fig_i, use_container_width=True)

# OPERACIONAL
if 'turma_municipio' in df_ativos.columns:
    st.markdown("---")
    st.subheader("🏢 Operacional por Município (TR e Frequência)")
    co1, co2 = st.columns(2)
    with co1:
        df_tr = df_ativos.groupby(['turma_municipio', 'turma']).size().reset_index(name='qtd').groupby('turma_municipio')['qtd'].mean().reset_index().sort_values('qtd', ascending=False)
        fig_tr = px.bar(df_tr, x='turma_municipio', y='qtd', title="Média de Alfabetizandos por Turma", text_auto='.1f', color_discrete_sequence=[COLORS['primary']])
        fig_tr.add_hline(y=15, line_dash="dash", line_color=COLORS['risco_alto'], annotation_text="Mín (15)")
        fig_tr.add_hline(y=27, line_dash="dash", line_color=COLORS['risco_alto'], annotation_text="Máx (27)")
        fig_tr.update_layout(xaxis_title=None, yaxis_title=None)
        fig_tr.update_xaxes(tickangle=-45)
        st.plotly_chart(fig_tr, use_container_width=True)
        
    with co2:
        df_fq = df_ativos.groupby('turma_municipio')['taxa_frequencia'].mean().reset_index().sort_values('taxa_frequencia', ascending=False)
        fig_fq = px.bar(df_fq, x='turma_municipio', y='taxa_frequencia', title="Frequência Média (%)", text_auto='.1f', color_discrete_sequence=[COLORS['secondary']])
        fig_fq.add_hline(y=75, line_dash="dash", line_color=COLORS['risco_alto'], annotation_text="Meta (75%)")
        fig_fq.update_layout(xaxis_title=None, yaxis_title=None, yaxis_range=[0, 115])
        fig_fq.update_xaxes(tickangle=-45)
        st.plotly_chart(fig_fq, use_container_width=True)

# TABELA FINAL E EXPORTAÇÃO
st.markdown("---")
st.subheader("🔍 Detalhamento de Alfabetizandos Ativos e Ação de Monitoramento")

# --- NOVA LEGENDA PROFISSIONAL COM HTML/CSS ---
st.markdown("""
<div style='background-color: #f8f9fa; border-left: 4px solid #004A8F; padding: 12px 15px; border-radius: 4px; margin-bottom: 20px; font-size: 14.5px; color: #333;'>
    <b>Guia de Cores e Alertas de Frequência:</b><br>
    <div style='margin-top: 8px; display: flex; flex-wrap: wrap; gap: 15px;'>
        <div>
            <span style='background-color: #FFCDD2; color: #B71C1C; padding: 2px 8px; border-radius: 4px; font-weight: bold;'>Possível desistente</span> 
            <span> Frequência abaixo de 50% (Ação Imediata)</span>
        </div>
        <div>
            <span style='background-color: #FFF2CC; color: #D48806; padding: 2px 8px; border-radius: 4px; font-weight: bold;'>Alto risco</span> 
            <span> Frequência entre 50% e 74% (Atenção)</span>
        </div>
        <div>
            <span style='background-color: #E8F5E9; color: #2E7D32; padding: 2px 8px; border-radius: 4px; font-weight: bold;'>Adequado</span> 
            <span> Frequência ≥ 75% (Meta Atingida)</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

cols_disp = ['alfabetizando', 'turma', 'status_alfabetizando', 'taxa_frequencia', 'risco_frequencia'] + [col for col in ['diag_entr_result_nivel', 'forma_1_result_nivel', 'forma_2_result_nivel', 'forma_3_result_nivel', 'forma_4_result_nivel', 'diag_said_result_nivel'] if col in df_ativos.columns]
df_tab = df_ativos[cols_disp].rename(columns={'alfabetizando': 'Nome do Alfabetizando', 'turma': 'Turma', 'status_alfabetizando': 'Status', 'taxa_frequencia': 'Frequência (%)', 'risco_frequencia': 'Alerta de Risco', 'diag_entr_result_nivel': 'Diag. Entrada', 'forma_1_result_nivel': 'Form. 1', 'forma_2_result_nivel': 'Form. 2', 'forma_3_result_nivel': 'Form. 3', 'forma_4_result_nivel': 'Form. 4', 'diag_said_result_nivel': 'Aval. Saída'})

st.dataframe(aplicar_estilo_tabela(df_tab), use_container_width=True, hide_index=True, height=450)

buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
    df_tab.to_excel(writer, index=False, sheet_name='Alfabetizandos_Ativos')
    for i, col in enumerate(df_tab.columns): writer.sheets['Alfabetizandos_Ativos'].set_column(i, i, max(df_tab[col].astype(str).map(len).max(), len(col)) + 2)

st.download_button("📥 Baixar Lista (Excel)", data=buffer.getvalue(), file_name='pba2026_alfabetizandos.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')