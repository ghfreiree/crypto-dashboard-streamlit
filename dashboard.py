"""
Dashboard Cripto — dados de mercado da CoinGecko.

Fonte: https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart
       (séries de preço, capitalização de mercado e volume negociado)

Execução:
    streamlit run dashboard.py
"""

from __future__ import annotations

import os
import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# --------------------------------------------------------------------------- #
# Configuração da página
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title='Dashboard Cripto | CoinGecko',
    page_icon=':chart_with_upwards_trend:',
    layout='wide',
    initial_sidebar_state='expanded',
)

API = 'https://api.coingecko.com/api/v3'
TIMEOUT = 30
MAX_COMPARACAO = 8

# A API devolve os timestamps em UTC. A série é convertida para este fuso e, em
# seguida, tem a marca de fuso descartada: o Plotly.js não interpreta deslocamento
# horário — desenha o instante recebido como está —, então os eixos precisam
# receber a hora local já resolvida. Troque as duas linhas para outra praça.
FUSO_EXIBICAO = 'America/Sao_Paulo'
ROTULO_FUSO = 'horário de Brasília'

MOEDAS_FIAT = {
    'usd': {'nome': 'Dólar (USD)', 'simbolo': 'US$'},
    'brl': {'nome': 'Real (BRL)', 'simbolo': 'R$'},
    'eur': {'nome': 'Euro (EUR)', 'simbolo': '€'},
}

PERIODOS = {
    '24 horas': 1,
    '7 dias': 7,
    '30 dias': 30,
    '90 dias': 90,
    '180 dias': 180,
    '1 ano': 365,
    'Máximo': 'max',
}

# Lista de reserva usada quando o endpoint /coins/markets está indisponível.
MOEDAS_PADRAO = {
    'bitcoin': 'Bitcoin (BTC)',
    'ethereum': 'Ethereum (ETH)',
    'solana': 'Solana (SOL)',
    'binancecoin': 'BNB (BNB)',
    'ripple': 'XRP (XRP)',
    'cardano': 'Cardano (ADA)',
    'dogecoin': 'Dogecoin (DOGE)',
    'chainlink': 'Chainlink (LINK)',
}

# --------------------------------------------------------------------------- #
# Paleta — ordem fixa, validada para daltonismo nos modos claro e escuro
# --------------------------------------------------------------------------- #
TEMAS = {
    'light': {
        'series': ['#2a78d6', '#eb6834', '#1baf7a', '#eda100',
                   '#e87ba4', '#008300', '#4a3aa7', '#e34948'],
        'texto': '#0b0b0b',
        'texto_secundario': '#52514e',
        'grade': 'rgba(11,11,11,0.10)',
        'superficie': '#ffffff',
        'alta': '#0ca30c',
        'baixa': '#d03b3b',
        'divergente': [[0.0, '#9c2a2a'], [0.25, '#e34948'], [0.5, '#f0efec'],
                       [0.75, '#5598e7'], [1.0, '#104281']],
    },
    'dark': {
        'series': ['#3987e5', '#d95926', '#199e70', '#c98500',
                   '#d55181', '#008300', '#9085e9', '#e66767'],
        'texto': '#ffffff',
        'texto_secundario': '#c3c2b7',
        'grade': 'rgba(255,255,255,0.12)',
        'superficie': '#1a1a19',
        'alta': '#0ca30c',
        'baixa': '#d03b3b',
        'divergente': [[0.0, '#9c2a2a'], [0.25, '#e66767'], [0.5, '#383835'],
                       [0.75, '#5598e7'], [1.0, '#104281']],
    },
}

FONTE = 'Source Sans Pro, -apple-system, Segoe UI, sans-serif'


def tema_ativo() -> dict:
    """Devolve a paleta correspondente ao tema atual do Streamlit."""
    tipo = None
    try:
        tipo = st.context.theme.type
    except Exception:
        pass
    if tipo not in ('light', 'dark'):
        tipo = st.get_option('theme.base') or 'light'
    return TEMAS.get(tipo, TEMAS['light'])


T = tema_ativo()


# --------------------------------------------------------------------------- #
# Acesso à API
# --------------------------------------------------------------------------- #
class ErroAPI(Exception):
    """Falha ao consultar a CoinGecko."""


def chave_api() -> str:
    """
    Chave opcional do plano Demo da CoinGecko.

    Sem chave a API pública limita as requisições e devolve HTTP 429 com
    facilidade. Defina `COINGECKO_API_KEY` em `.streamlit/secrets.toml` ou como
    variável de ambiente para elevar o limite.
    """
    try:
        das_secrets = st.secrets.get('COINGECKO_API_KEY', '')
    except Exception:
        das_secrets = ''
    return str(das_secrets or os.environ.get('COINGECKO_API_KEY', '')).strip()


def _requisitar(url: str, params: dict):
    """GET com retentativa simples para o limite de requisições (HTTP 429)."""
    chave = chave_api()
    cabecalhos = {'accept': 'application/json'}
    if chave:
        cabecalhos['x-cg-demo-api-key'] = chave

    ultimo_erro = ''
    for tentativa in range(3):
        try:
            resposta = requests.get(url, params=params, headers=cabecalhos, timeout=TIMEOUT)
        except requests.RequestException as erro:
            ultimo_erro = f'falha de conexão ({erro.__class__.__name__})'
        else:
            if resposta.status_code == 200:
                return resposta.json()
            if resposta.status_code == 429:
                ultimo_erro = ('limite de requisições da API gratuita atingido '
                               '(HTTP 429); aguarde cerca de um minuto ou '
                               'configure COINGECKO_API_KEY')
                time.sleep(2 * (tentativa + 1))
                continue
            if resposta.status_code == 404:
                raise ErroAPI('moeda não encontrada na CoinGecko (HTTP 404)')
            ultimo_erro = f'a API respondeu com HTTP {resposta.status_code}'
        time.sleep(1.5 * (tentativa + 1))
    raise ErroAPI(ultimo_erro or 'não foi possível obter os dados')


@st.cache_data(ttl=600, show_spinner=False)
def carregar_ranking(moeda_fiat: str, quantidade: int = 100) -> pd.DataFrame:
    """Top moedas por capitalização — alimenta os seletores e o contexto de mercado."""
    dados = _requisitar(
        f'{API}/coins/markets',
        {
            'vs_currency': moeda_fiat,
            'order': 'market_cap_desc',
            'per_page': quantidade,
            'page': 1,
            'sparkline': 'false',
            'price_change_percentage': '24h,7d,30d',
        },
    )
    df = pd.DataFrame(dados)
    if df.empty:
        raise ErroAPI('a API não retornou moedas')
    df['rotulo'] = df['name'] + ' (' + df['symbol'].str.upper() + ')'
    return df


@st.cache_data(ttl=600, show_spinner=False)
def carregar_historico(coin_id: str, moeda_fiat: str, dias) -> pd.DataFrame:
    """
    Série histórica de /coins/{id}/market_chart.

    Devolve um DataFrame com as colunas `preco`, `market_cap` e `volume`,
    indexado pelo tempo já convertido de UTC para FUSO_EXIBICAO.
    """
    dados = _requisitar(
        f'{API}/coins/{coin_id}/market_chart',
        {'vs_currency': moeda_fiat, 'days': dias},
    )

    def serie(pares: list, nome: str) -> pd.Series:
        quadro = pd.DataFrame(pares, columns=['ts', nome])
        quadro['data'] = (
            pd.to_datetime(quadro['ts'], unit='ms', utc=True)
            .dt.tz_convert(FUSO_EXIBICAO)
            .dt.tz_localize(None)
        )
        return quadro.set_index('data')[nome]

    df = pd.concat(
        [
            serie(dados.get('prices', []), 'preco'),
            serie(dados.get('market_caps', []), 'market_cap'),
            serie(dados.get('total_volumes', []), 'volume'),
        ],
        axis=1,
    ).sort_index()

    df = df[~df.index.duplicated(keep='last')].dropna(subset=['preco'])
    if df.empty:
        raise ErroAPI('a série histórica retornou vazia')
    return df


# --------------------------------------------------------------------------- #
# Formatação e métricas
# --------------------------------------------------------------------------- #
def formata_numero(valor: float, casas: int = 2) -> str:
    """Formata no padrão brasileiro: milhar com ponto, decimal com vírgula."""
    if valor is None or pd.isna(valor):
        return '—'
    return f'{valor:,.{casas}f}'.replace(',', '@').replace('.', ',').replace('@', '.')


def formata_preco(valor: float, simbolo: str) -> str:
    if valor is None or pd.isna(valor):
        return '—'
    casas = 2 if abs(valor) >= 1 else 6
    return f'{simbolo} {formata_numero(valor, casas)}'


def formata_compacto(valor: float, simbolo: str = '') -> str:
    """Abrevia grandezas grandes: mil, milhões, bilhões, trilhões."""
    if valor is None or pd.isna(valor):
        return '—'
    prefixo = f'{simbolo} ' if simbolo else ''
    for limite, unidade in ((1e12, 'tri'), (1e9, 'bi'), (1e6, 'mi'), (1e3, 'mil')):
        if abs(valor) >= limite:
            return f'{prefixo}{formata_numero(valor / limite)} {unidade}'
    return f'{prefixo}{formata_numero(valor)}'


def formata_percentual(valor: float, casas: int = 2, sinal: bool = False) -> str:
    if valor is None or pd.isna(valor):
        return '—'
    texto = f'{valor:+.{casas}f}' if sinal else f'{valor:.{casas}f}'
    return texto.replace('.', ',') + '%'


def granularidade(df: pd.DataFrame) -> tuple[float, str]:
    """Intervalo mediano entre observações, em horas, e seu rótulo legível."""
    if len(df) < 2:
        return 24.0, '1 dia'
    horas = float(df.index.to_series().diff().dt.total_seconds().median() / 3600)
    if horas < 0.2:
        return horas, '5 min'
    if horas < 1.5:
        return horas, '1 hora'
    if horas < 12:
        return horas, f'{horas:.0f} horas'
    return horas, '1 dia'


def regra_agregacao(df: pd.DataFrame) -> tuple[str, str]:
    """Regra de reamostragem das velas, conforme o tamanho da janela."""
    span = (df.index[-1] - df.index[0]).total_seconds() / 86400
    if span <= 2:
        return '1h', '1 hora'
    if span <= 10:
        return '4h', '4 horas'
    if span <= 120:
        return '1D', '1 dia'
    return '1W', '1 semana'


def calcular_indicadores(df: pd.DataFrame) -> dict:
    """KPIs do período selecionado."""
    preco = df['preco']
    horas, _ = granularidade(df)
    periodos_ano = (365 * 24 / horas) if horas else 365

    retornos = preco.pct_change().dropna()
    volatilidade = (float(retornos.std() * (periodos_ano ** 0.5) * 100)
                    if len(retornos) > 2 else float('nan'))
    drawdown = (preco / preco.cummax() - 1) * 100

    return {
        'preco_atual': float(preco.iloc[-1]),
        'preco_inicial': float(preco.iloc[0]),
        'variacao': float((preco.iloc[-1] / preco.iloc[0] - 1) * 100),
        'maxima': float(preco.max()),
        'minima': float(preco.min()),
        'data_maxima': preco.idxmax(),
        'data_minima': preco.idxmin(),
        'amplitude': float((preco.max() / preco.min() - 1) * 100),
        'volatilidade': volatilidade,
        'volume_medio': float(df['volume'].mean()),
        'volume_total': float(df['volume'].sum()),
        'market_cap': float(df['market_cap'].iloc[-1]),
        'variacao_market_cap': float((df['market_cap'].iloc[-1] / df['market_cap'].iloc[0] - 1) * 100),
        'drawdown': drawdown,
        'drawdown_max': float(drawdown.min()),
        'retornos': retornos * 100,
    }


# --------------------------------------------------------------------------- #
# Base visual dos gráficos
# --------------------------------------------------------------------------- #
def _transparencia(cor_hex: str, alfa: float) -> str:
    cor_hex = cor_hex.lstrip('#')
    r, g, b = (int(cor_hex[i:i + 2], 16) for i in (0, 2, 4))
    return f'rgba({r},{g},{b},{alfa})'


def aplicar_layout(fig: go.Figure, altura: int = 380, titulo: str | None = None,
                   legenda: bool = False) -> go.Figure:
    """Grade discreta, fundo transparente e tipografia consistente."""
    fig.update_layout(
        height=altura,
        template='none',
        margin=dict(l=10, r=10, t=56 if titulo else 18, b=10),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family=FONTE, size=13, color=T['texto_secundario']),
        hovermode='x unified',
        hoverlabel=dict(bgcolor=T['superficie'], bordercolor=T['grade'],
                        font=dict(family=FONTE, size=12, color=T['texto'])),
        showlegend=legenda,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0,
                    bgcolor='rgba(0,0,0,0)',
                    font=dict(size=12, color=T['texto_secundario'])),
    )
    if titulo:
        fig.update_layout(title=dict(text=titulo, x=0, xanchor='left', pad=dict(b=14),
                                     font=dict(family=FONTE, size=17, color=T['texto'])))
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=T['grade'],
                     ticks='outside', tickcolor=T['grade'], tickfont=dict(size=12))
    fig.update_yaxes(showgrid=True, gridcolor=T['grade'], gridwidth=1, zeroline=False,
                     linecolor='rgba(0,0,0,0)', tickfont=dict(size=12))
    return fig


# --------------------------------------------------------------------------- #
# Gráficos
# --------------------------------------------------------------------------- #
def grafico_preco(df: pd.DataFrame, simbolo: str, escala_log: bool,
                  rotulo_gran: str) -> go.Figure:
    """Série de preço isolada — uma única medida, sem legenda (o título a nomeia)."""
    fig = go.Figure(
        go.Scatter(
            x=df.index, y=df['preco'], name='Preço', mode='lines',
            line=dict(color=T['series'][0], width=2),
            fill='tozeroy', fillcolor=_transparencia(T['series'][0], 0.10),
            hovertemplate=f'{simbolo} %{{y:,.2f}}<extra>Preço</extra>',
        )
    )
    aplicar_layout(fig, altura=520,
                   titulo=f'Preço · observações a cada {rotulo_gran}')
    fig.update_yaxes(title_text=f'Preço ({simbolo})',
                     type='log' if escala_log else 'linear')
    return fig


def grafico_velas(df: pd.DataFrame, regra: str, rotulo: str, simbolo: str) -> go.Figure:
    """Candlestick derivado da reamostragem da série de preços."""
    ohlc = df['preco'].resample(regra).ohlc().dropna()
    fig = go.Figure(
        go.Candlestick(
            x=ohlc.index, open=ohlc['open'], high=ohlc['high'],
            low=ohlc['low'], close=ohlc['close'], name='Preço',
            increasing=dict(line=dict(color=T['alta'], width=1), fillcolor=T['alta']),
            decreasing=dict(line=dict(color=T['baixa'], width=1), fillcolor=T['baixa']),
        )
    )
    aplicar_layout(fig, altura=440, titulo=f'Velas · agregação de {rotulo}')
    fig.update_layout(xaxis_rangeslider_visible=False, hovermode='x')
    fig.update_yaxes(title_text=f'Preço ({simbolo})')
    return fig


def grafico_drawdown(drawdown: pd.Series) -> go.Figure:
    """Queda acumulada desde a máxima anterior."""
    fig = go.Figure(
        go.Scatter(
            x=drawdown.index, y=drawdown, mode='lines', name='Drawdown',
            line=dict(color=T['baixa'], width=2),
            fill='tozeroy', fillcolor=_transparencia(T['baixa'], 0.16),
            hovertemplate='%{y:.2f}%<extra>Drawdown</extra>',
        )
    )
    aplicar_layout(fig, altura=340, titulo='Drawdown — distância da máxima do período')
    fig.update_yaxes(title_text='Queda acumulada (%)', ticksuffix='%')
    return fig


def grafico_retornos(retornos: pd.Series, rotulo_gran: str) -> go.Figure:
    """Distribuição dos retornos por intervalo."""
    fig = go.Figure(
        go.Histogram(
            x=retornos, nbinsx=44, name='Retornos',
            marker=dict(color=_transparencia(T['series'][0], 0.75),
                        line=dict(color=T['superficie'], width=1)),
            hovertemplate='Faixa %{x}<br>%{y} ocorrências<extra></extra>',
        )
    )
    media = float(retornos.mean()) if len(retornos) else 0.0
    fig.add_vline(x=media, line=dict(color=T['texto_secundario'], width=2),
                  annotation_text=f'média {media:.2f}%',
                  annotation_font=dict(color=T['texto_secundario'], size=12))
    aplicar_layout(fig, altura=340,
                   titulo=f'Distribuição dos retornos por intervalo de {rotulo_gran}')
    fig.update_layout(hovermode='closest')
    fig.update_xaxes(title_text='Retorno (%)', ticksuffix='%')
    fig.update_yaxes(title_text='Frequência')
    return fig


def grafico_market_cap(df: pd.DataFrame, simbolo: str) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=df.index, y=df['market_cap'], mode='lines', name='Capitalização',
            line=dict(color=T['series'][6], width=2),
            fill='tozeroy', fillcolor=_transparencia(T['series'][6], 0.12),
            hovertemplate=f'{simbolo} %{{y:,.0f}}<extra>Capitalização</extra>',
        )
    )
    aplicar_layout(fig, altura=340, titulo='Capitalização de mercado')
    fig.update_yaxes(title_text=f'Capitalização ({simbolo})')
    return fig


def grafico_comparacao(series: dict) -> go.Figure:
    """Desempenho relativo com base 100 no início do período — um único eixo."""
    fig = go.Figure()
    for posicao, (nome, serie) in enumerate(series.items()):
        normalizada = serie / serie.iloc[0] * 100
        cor = T['series'][posicao % len(T['series'])]
        fig.add_trace(
            go.Scatter(
                x=normalizada.index, y=normalizada, mode='lines', name=nome,
                line=dict(color=cor, width=2),
                hovertemplate='%{y:.1f}<extra>' + nome + '</extra>',
            )
        )
        if len(series) <= 4:
            fig.add_annotation(
                x=normalizada.index[-1], y=float(normalizada.iloc[-1]),
                text=f'  {normalizada.iloc[-1]:.0f}', showarrow=False,
                xanchor='left', font=dict(color=cor, size=12),
            )
    fig.add_hline(y=100, line=dict(color=T['grade'], width=1))
    aplicar_layout(fig, altura=460, legenda=True,
                   titulo='Desempenho relativo (base 100 no início do período)')
    fig.update_yaxes(title_text='Índice (base 100)')
    fig.update_xaxes(domain=[0, 0.96] if len(series) <= 4 else [0, 1])
    return fig


def grafico_correlacao(matriz: pd.DataFrame) -> go.Figure:
    """Correlação dos retornos diários — escala divergente com meio neutro."""
    fig = go.Figure(
        go.Heatmap(
            z=matriz.values, x=list(matriz.columns), y=list(matriz.index),
            zmin=-1, zmax=1, colorscale=T['divergente'], xgap=2, ygap=2,
            texttemplate='%{z:.2f}', textfont=dict(family=FONTE, size=12),
            hovertemplate='%{y} × %{x}: %{z:.2f}<extra></extra>',
            colorbar=dict(title=dict(text='ρ', font=dict(color=T['texto_secundario'])),
                          tickfont=dict(color=T['texto_secundario']),
                          outlinewidth=0, thickness=12),
        )
    )
    aplicar_layout(fig, altura=440, titulo='Correlação dos retornos diários')
    fig.update_layout(hovermode='closest')
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False, autorange='reversed')
    return fig


# --------------------------------------------------------------------------- #
# Barra lateral — filtros
# --------------------------------------------------------------------------- #
st.sidebar.title('Filtros')

fiat = st.sidebar.selectbox(
    'Moeda de referência',
    options=list(MOEDAS_FIAT),
    format_func=lambda chave: MOEDAS_FIAT[chave]['nome'],
)
SIMBOLO = MOEDAS_FIAT[fiat]['simbolo']

try:
    ranking = carregar_ranking(fiat)
    catalogo = dict(zip(ranking['id'], ranking['rotulo']))
except ErroAPI as erro:
    st.sidebar.warning(f'Lista de moedas indisponível — {erro}. Usando catálogo local.')
    ranking = pd.DataFrame()
    catalogo = dict(MOEDAS_PADRAO)

ids = list(catalogo)
moeda = st.sidebar.selectbox(
    'Criptomoeda',
    options=ids,
    index=ids.index('bitcoin') if 'bitcoin' in ids else 0,
    format_func=lambda chave: catalogo.get(chave, chave),
)

periodo = st.sidebar.select_slider('Período', options=list(PERIODOS), value='90 dias')
dias = PERIODOS[periodo]

st.sidebar.subheader('Análise técnica')
escala_log = st.sidebar.toggle('Escala logarítmica no preço', value=False)

st.sidebar.subheader('Comparação')
padrao_comparacao = [m for m in [moeda, 'ethereum', 'solana'] if m in ids][:3]
comparadas = st.sidebar.multiselect(
    'Moedas confrontadas',
    options=ids,
    default=padrao_comparacao,
    format_func=lambda chave: catalogo.get(chave, chave),
    max_selections=MAX_COMPARACAO,
    help=f'Até {MAX_COMPARACAO} moedas — acima disso as cores deixam de ser distinguíveis.',
)

if st.sidebar.button('Atualizar dados', width='stretch'):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(
    'Dados: CoinGecko API · cache de 10 minutos · '
    + ('chave Demo ativa' if chave_api() else
       'sem chave (limite público) — defina COINGECKO_API_KEY para elevar o limite')
)


# --------------------------------------------------------------------------- #
# Carregamento da série principal
# --------------------------------------------------------------------------- #
with st.spinner('Consultando a CoinGecko…'):
    try:
        dados = carregar_historico(moeda, fiat, dias)
    except ErroAPI as erro:
        st.error(f'Não foi possível carregar {catalogo.get(moeda, moeda)} — {erro}.')
        st.stop()

kpis = calcular_indicadores(dados)
_, rotulo_gran = granularidade(dados)
regra, rotulo_regra = regra_agregacao(dados)
contexto = (ranking.set_index('id').loc[moeda].to_dict()
            if not ranking.empty and moeda in set(ranking['id']) else {})


# --------------------------------------------------------------------------- #
# Cabeçalho e KPIs
# --------------------------------------------------------------------------- #
cabecalho, atualizacao = st.columns([3, 1], vertical_alignment='center')
with cabecalho:
    st.title(f'{catalogo.get(moeda, moeda)} :chart_with_upwards_trend:')
    posicao_rank = (f' · #{contexto["market_cap_rank"]:.0f} em capitalização'
                    if contexto.get('market_cap_rank') else '')
    st.caption(
        f'Período: {periodo} · cotação em {MOEDAS_FIAT[fiat]["nome"]} · '
        f'{len(dados)} observações a cada {rotulo_gran}{posicao_rank}'
    )
with atualizacao:
    st.metric('Última leitura', dados.index[-1].strftime('%d/%m %H:%M'),
              help=f'Último ponto devolvido pela API, em {ROTULO_FUSO}.')

st.divider()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric('Preço atual', formata_preco(kpis['preco_atual'], SIMBOLO),
          f'{formata_percentual(kpis["variacao"], sinal=True)} no período', border=True)
k2.metric('Máxima do período', formata_preco(kpis['maxima'], SIMBOLO),
          kpis['data_maxima'].strftime('%d/%m/%Y'), delta_color='off', border=True)
k3.metric('Mínima do período', formata_preco(kpis['minima'], SIMBOLO),
          kpis['data_minima'].strftime('%d/%m/%Y'), delta_color='off', border=True)
k4.metric('Volatilidade anualizada', formata_percentual(kpis['volatilidade']),
          f'amplitude de {formata_percentual(kpis["amplitude"])}',
          delta_color='off', border=True)
k5.metric('Capitalização', formata_compacto(kpis['market_cap'], SIMBOLO),
          f'{formata_percentual(kpis["variacao_market_cap"], sinal=True)} no período',
          border=True)


# --------------------------------------------------------------------------- #
# Abas
# --------------------------------------------------------------------------- #
aba_visao, aba_tecnica, aba_comparacao, aba_dados = st.tabs(
    ['Visão geral', 'Análise técnica', 'Comparação', 'Dados brutos']
)

with aba_visao:
    st.plotly_chart(
        grafico_preco(dados, SIMBOLO, escala_log, rotulo_gran),
        width='stretch',
    )

    esquerda, direita = st.columns(2)
    with esquerda:
        st.plotly_chart(grafico_market_cap(dados, SIMBOLO), width='stretch')
    with direita:
        st.plotly_chart(grafico_retornos(kpis['retornos'], rotulo_gran),
                        width='stretch')

    v1, v2, v3, v4 = st.columns(4)
    v1.metric('Volume médio por intervalo', formata_compacto(kpis['volume_medio'], SIMBOLO),
              border=True)
    v2.metric('Volume acumulado', formata_compacto(kpis['volume_total'], SIMBOLO), border=True)
    v3.metric('Drawdown máximo', formata_percentual(kpis['drawdown_max']), border=True)
    if contexto.get('ath'):
        v4.metric('Máxima histórica', formata_preco(contexto['ath'], SIMBOLO),
                  f'{formata_percentual(contexto.get("ath_change_percentage") or 0, 1, sinal=True)} '
                  'de distância', border=True)
    else:
        v4.metric('Preço no início do período',
                  formata_preco(kpis['preco_inicial'], SIMBOLO), border=True)

with aba_tecnica:
    st.plotly_chart(grafico_velas(dados, regra, rotulo_regra, SIMBOLO),
                    width='stretch')
    st.plotly_chart(grafico_drawdown(kpis['drawdown']), width='stretch')

    retornos = kpis['retornos']
    positivos = float((retornos > 0).mean() * 100) if len(retornos) else float('nan')
    t1, t2, t3, t4 = st.columns(4)
    t1.metric('Intervalos em alta', formata_percentual(positivos, 1),
              f'de {len(retornos)} intervalos', delta_color='off', border=True)
    t2.metric('Melhor intervalo', formata_percentual(retornos.max()), border=True)
    t3.metric('Pior intervalo', formata_percentual(retornos.min()), border=True)
    t4.metric('Retorno médio', formata_percentual(retornos.mean(), 3),
              f'por intervalo de {rotulo_gran}', delta_color='off', border=True)

    st.caption(
        'As velas e os indicadores derivam da série de preços de `/market_chart`: '
        'a CoinGecko não devolve OHLC nesse endpoint, portanto abertura, máxima, '
        'mínima e fechamento vêm da reamostragem da própria série.'
    )

with aba_comparacao:
    if len(comparadas) < 2:
        st.info('Selecione ao menos duas moedas na barra lateral para comparar.')
    else:
        series = {}
        falhas = []
        barra = st.progress(0.0, text='Carregando séries…')
        for posicao, identificador in enumerate(comparadas, start=1):
            nome = catalogo.get(identificador, identificador)
            try:
                series[nome] = carregar_historico(identificador, fiat, dias)['preco']
            except ErroAPI as erro:
                falhas.append(f'{nome} ({erro})')
            barra.progress(posicao / len(comparadas), text='Carregando séries…')
        barra.empty()

        if falhas:
            st.warning('Algumas moedas não puderam ser carregadas — ' + ' · '.join(falhas))

        if len(series) >= 2:
            st.plotly_chart(grafico_comparacao(series), width='stretch')

            diarios = pd.DataFrame(
                {nome: serie.resample('1D').last() for nome, serie in series.items()}
            ).dropna(how='all').pct_change().dropna(how='all')

            esquerda, direita = st.columns(2)
            with esquerda:
                if len(diarios.dropna()) >= 3:
                    st.plotly_chart(grafico_correlacao(diarios.corr()),
                                    width='stretch')
                else:
                    st.info('O período é curto demais para calcular a correlação diária.')
            with direita:
                resumo = pd.DataFrame({
                    'Moeda': list(series),
                    'Preço atual': [formata_preco(s.iloc[-1], SIMBOLO) for s in series.values()],
                    'Variação no período (%)': [round((s.iloc[-1] / s.iloc[0] - 1) * 100, 2)
                                                for s in series.values()],
                    'Volatilidade diária (%)': [round(float(diarios[nome].std() * 100), 2)
                                                if nome in diarios else float('nan')
                                                for nome in series],
                }).sort_values('Variação no período (%)', ascending=False)
                st.dataframe(
                    resumo, hide_index=True, width='stretch', height=440,
                    column_config={
                        'Variação no período (%)': st.column_config.NumberColumn(format='%+.2f%%'),
                        'Volatilidade diária (%)': st.column_config.NumberColumn(format='%.2f%%'),
                    },
                )

with aba_dados:
    st.subheader('Série devolvida por `/market_chart`')
    tabela = dados.copy()
    tabela.index.name = f'Data ({ROTULO_FUSO})'
    tabela = tabela.rename(columns={
        'preco': f'Preço ({SIMBOLO})',
        'market_cap': f'Capitalização ({SIMBOLO})',
        'volume': f'Volume 24h ({SIMBOLO})',
    })
    st.dataframe(tabela.sort_index(ascending=False), width='stretch', height=420)

    coluna_download, coluna_info = st.columns([1, 2])
    with coluna_download:
        st.download_button(
            'Baixar CSV',
            data=tabela.to_csv().encode('utf-8-sig'),
            file_name=f'{moeda}_{fiat}_{periodo.replace(" ", "")}.csv',
            mime='text/csv',
            width='stretch',
        )
    with coluna_info:
        st.caption(
            f'`GET {API}/coins/{moeda}/market_chart?vs_currency={fiat}&days={dias}` · '
            f'{len(tabela)} linhas'
        )

    if not ranking.empty:
        st.subheader('Contexto de mercado — top 100 por capitalização')
        colunas = ['market_cap_rank', 'rotulo', 'current_price',
                   'price_change_percentage_24h', 'price_change_percentage_7d_in_currency',
                   'market_cap', 'total_volume']
        mercado = ranking[[c for c in colunas if c in ranking.columns]].rename(columns={
            'market_cap_rank': '#',
            'rotulo': 'Moeda',
            'current_price': f'Preço ({SIMBOLO})',
            'price_change_percentage_24h': '24h (%)',
            'price_change_percentage_7d_in_currency': '7d (%)',
            'market_cap': f'Capitalização ({SIMBOLO})',
            'total_volume': f'Volume 24h ({SIMBOLO})',
        })
        st.dataframe(
            mercado, hide_index=True, width='stretch', height=420,
            column_config={
                '24h (%)': st.column_config.NumberColumn(format='%+.2f%%'),
                '7d (%)': st.column_config.NumberColumn(format='%+.2f%%'),
            },
        )

st.divider()
st.caption(
    f'Fonte: CoinGecko API v3 · página gerada em '
    f'{datetime.now().strftime("%d/%m/%Y às %H:%M")} · as cotações têm caráter '
    'informativo e não constituem recomendação de investimento.'
)
