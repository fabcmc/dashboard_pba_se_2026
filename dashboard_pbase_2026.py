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

TURMAS_ENCERRADAS = [
    "TURMA-28022645-0001",
    "TURMA-28013360-0001"
]

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
    for chave in ['filtro_municipio', 'filtro_cons', 'filtro_esp', 'filtro_coord', 'filtro_alfab']:
        st.session_state[chave] = 'Todos'
    st.session_state['filtro_turma'] = 'Todas'

# =============================================================================
# 3. EXTRAÇÃO E TRANSFORMAÇÃO DE DADOS (ETL)
# =============================================================================
@st.cache_data(ttl=3600, show_spinner="Conectando à base de dados segura...")
def carregar_dados():
    try:
        # PROTEÇÃO DE DADOS: Uso obrigatório do Secrets para o link da API
        url_json = st.secrets["LINK_JSON_FGV"] 
        df = pd.read_json(url_json)
        df.columns = df.columns.str.lower().str.strip()
        return df
    except Exception as e:
        st.error(f"Erro de conexão com a fonte de dados: {e}")
        st.stop()

@st.cache_data(show_spinner="Aplicando regras operacionais...")
def processar_regras_negocio(df):
    df_clean = df.copy()
    if 'turma' in df_clean.columns:
        df_clean = df_clean[~df_clean['turma'].str.contains('TURMA-P0000247-0001', case=False, na=False)]
        df_clean = df_clean[~df_clean['turma'].isin(TURMAS_ENCERRADAS)]

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
st.title("📊 Painel de Monitoramento - Alfabetiza Sergipe 2026.1")
st.markdown("Acompanhamento de indicadores educacionais")

# FILTROS LATERAIS
st.sidebar.markdown("---")
st.sidebar.header("🎛️ Filtros de Análise")

# 1. Inicializamos a memória incluindo o filtro_municipio
for key in ['filtro_municipio', 'filtro_cons', 'filtro_esp', 'filtro_coord', 'filtro_alfab']:
    if key not in st.session_state: st.session_state[key] = 'Todos'
if 'filtro_turma' not in st.session_state: st.session_state['filtro_turma'] = 'Todas'

st.sidebar.button("🔄 Limpar Todos os Filtros", on_click=limpar_filtros, use_container_width=True)

df_filtrado = df_final.copy()

# 2. Adicionamos a tupla do Município no topo da lista (antes do consultor)
filtros = [
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

# SEPARAÇÃO MATRICULADOS VS ATIVOS
df_ativos = df_filtrado[df_filtrado['status_alfabetizando'] != 'EVADIDO'].copy()
total_mat, total_atv = df_filtrado.shape[0], df_ativos.shape[0]
evadidos = total_mat - total_atv

# Indicadores Gerais
st.markdown("---")
st.subheader("🎯 Visão Geral, Engajamento e Retenção")

possiveis_desistentes = df_ativos[df_ativos['taxa_frequencia'] < 50].shape[0]

# Verifica na base original (df_bruto) quantas turmas da nossa lista realmente vieram no JSON
qtd_encerradas = df_bruto[df_bruto['turma'].isin(TURMAS_ENCERRADAS)]['turma'].nunique()

# Dividindo o topo em 7 colunas
c1, c2, c3, c4, c5, c6, c7 = st.columns(7)

c1.metric("Total Matriculados", f"{total_mat}")
c2.metric("Alunos Ativos", f"{total_atv}")

c3.metric(
    "Taxa Desistência", 
    f"{(evadidos/total_mat*100) if total_mat > 0 else 0:.1f}%", 
    f"{evadidos} evadidos" if evadidos > 0 else "Nenhuma", 
    delta_color="inverse"
)

c4.metric(
    "Possíveis Desistentes", 
    f"{possiveis_desistentes}", 
    "Ação Imediata" if possiveis_desistentes > 0 else "Estável", 
    delta_color="inverse"
)

c5.metric("Frequência Média", f"{df_ativos['taxa_frequencia'].mean() if total_atv > 0 else 0:.1f}%")
c6.metric("Turmas Ativas", f"{df_filtrado['turma'].nunique()}")

# Turmas Encerradas (delta_color="off" deixa a legenda cinza, indicando um dado informativo e neutro)
c7.metric(
    "Turmas Encerradas", 
    f"{qtd_encerradas}", 
    "Finalizado Antes do Tempo", 
    delta_color="off"
)

# DEMOGRÁFICO E TERRITORIAL
if 'turma_municipio' in df_ativos.columns and 'dt_nascimento' in df_ativos.columns:
    st.markdown("---")
    st.subheader("🗺️ Visão Territorial e Perfil Demográfico")
    cd1, cd2 = st.columns([1, 2])
    
    with cd1:
        df_idade = df_ativos.copy()
        df_idade['dt_nascimento'] = pd.to_datetime(df_idade['dt_nascimento'], errors='coerce')
        df_idade['idade'] = (pd.Timestamp.now() - df_idade['dt_nascimento']).dt.days // 365
        rotulos_idade = ['15 a 24 anos', '25 a 34 anos', '35 a 44 anos', '45 a 54 anos', '55 a 64 anos', '65 a 74 anos', '75 anos ou mais']
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

# SOCIOEMOCIONAL
if 'socio_entr_q1' in df_ativos.columns and 'socio_entr_q9' in df_ativos.columns:
    st.markdown("---")
    st.subheader("🧠 Contexto Socioemocional de Entrada")
    
    map_txt = {
        'Demonstra motivação constante e desejo de continuar estudando': 'Alta Motivação', 'Demonstra interesse, mas com oscilações': 'Interesse oscilante', 'Demonstra desmotivação ou desejo de interromper': 'Desmotivação', 
        'São frequentes e pontuais': 'Frequentes e pontuais', 'Frequência regular sem nenhuma falta': 'Freq. sem faltas', 'Frequência regular com algumas faltas': 'Freq. com faltas', 
        'Realiza com alguma ajuda': 'Realiza com ajuda', 'Realiza com autonomia na maioria das situações': 'Realiza com autonomia', 'Depende de ajuda constante': 'Depende de ajuda', 
        'Tenta com apoio e incentivo': 'Tenta com apoio', 'Tenta com iniciativa própria': 'Tenta com iniciativa', 'Demonstra insegurança e evita tentar': 'Insegurança', 
        'Persiste e aceita o erro como parte da aprendizagem': 'Aceita o erro', 'Persiste, mas demonstra frustração': 'Frustração', 'Desiste facilmente': 'Desiste facilmente', 
        'Participa ativamente e coopera com os colegas': 'Participa ativamente', 'Participa quando estimulado(a)': 'Participa se estimulado', 'Evita interações': 'Evita interações', 
        'Reconhece claramente e relata usos práticos': 'Reconhece claramente', 'Reconhece em algumas situações': 'Reconhece às vezes', 'Não reconhece': 'Não reconhece'
    }
    
    cores_socio = {k: COLORS['secondary'] for k in ['Alta Motivação', 'Frequentes e pontuais', 'Realiza com autonomia', 'Tenta com iniciativa', 'Aceita o erro', 'Participa ativamente', 'Reconhece claramente']}
    cores_socio.update({k: COLORS['risco_medio'] for k in ['Interesse oscilante', 'Freq. sem faltas', 'Realiza com ajuda', 'Tenta com apoio', 'Frustração', 'Participa se estimulado', 'Reconhece às vezes']})
    cores_socio.update({k: COLORS['risco_alto'] for k in ['Desmotivação', 'Freq. com faltas', 'Depende de ajuda', 'Insegurança', 'Desiste facilmente', 'Evita interações', 'Não reconhece']})

    titulos = ["1. Motivação", "2. Assiduidade", "3. Autonomia", "4. Iniciativa", "5. Persistência", "6. Participação", "7. Usos Práticos"]
    cols_q = [f'socio_entr_q{i}' for i in range(1, 8)]

    st.markdown("<br>", unsafe_allow_html=True)
    c_l1 = st.columns(4)
    for i in range(4):
        if cols_q[i] in df_ativos.columns:
            with c_l1[i]: st.plotly_chart(criar_grafico_rosca(df_ativos, cols_q[i], titulos[i], map_txt, cores_socio), use_container_width=True)

    c_l2 = st.columns([0.5, 1, 1, 1, 0.5])
    for i in range(4, 7):
        if cols_q[i] in df_ativos.columns:
            with c_l2[i-3]: st.plotly_chart(criar_grafico_rosca(df_ativos, cols_q[i], titulos[i], map_txt, cores_socio), use_container_width=True)

    df_dif = df_ativos[['socio_entr_q9']].copy()
    df_dif['lista'] = df_dif['socio_entr_q9'].apply(extrair_dificuldades)
    cont_dif = df_dif.explode('lista').dropna(subset=['lista'])['lista'].value_counts().reset_index().rename(columns={'lista':'Dificuldade', 'count':'Qtd'})
    cont_dif = cont_dif[cont_dif['Dificuldade'] != '']
    
    fig_dif = px.bar(cont_dif, y='Dificuldade', x='Qtd', orientation='h', title="8. Dificuldades (Q9)", text_auto=True, height=500, color_discrete_sequence=[COLORS['primary']])
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