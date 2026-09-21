# Dashboard Cripto — CoinGecko

Painel interativo de mercado de criptomoedas construído em **Streamlit**, com
gráficos em **Plotly**, tratamento de dados em **pandas** e consumo da API
pública da CoinGecko via **requests**.

Toda a série histórica vem de um único endpoint:

```
GET https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency={moeda}&days={dias}
```

que devolve três séries temporais — preço, capitalização de mercado e volume
negociado em 24 h. O endpoint `/coins/markets` é usado apenas como apoio, para
listar as 100 maiores moedas nos seletores e mostrar o contexto de mercado.

---

## Sumário

- [Funcionalidades](#funcionalidades)
- [Instalação](#instalação)
- [Execução local](#execução-local)
- [Deploy no Streamlit Community Cloud](#deploy-no-streamlit-community-cloud)
- [Chave de API (opcional, mas recomendada)](#chave-de-api-opcional-mas-recomendada)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Como as métricas são calculadas](#como-as-métricas-são-calculadas)
- [Decisões de visualização](#decisões-de-visualização)
- [Cache e limites da API](#cache-e-limites-da-api)
- [Solução de problemas](#solução-de-problemas)
- [Aviso](#aviso)

---

## Funcionalidades

### Filtros (barra lateral)

| Filtro | Opções |
|---|---|
| Moeda de referência | Dólar (USD), Real (BRL), Euro (EUR) |
| Criptomoeda | As 100 maiores por capitalização; catálogo local de reserva se a API falhar |
| Período | 24 horas, 7, 30, 90, 180 dias, 1 ano e histórico máximo |
| Escala logarítmica | Aplicada ao eixo de preço |
| Comparação | Até 8 moedas confrontadas simultaneamente |
| Atualizar dados | Limpa o cache e recarrega tudo da API |

### Indicadores no topo

Preço atual com variação no período, máxima e mínima datadas, volatilidade
anualizada e capitalização de mercado com sua variação.

### Abas

- **Visão geral** — série de preço, capitalização de mercado ao longo do tempo,
  distribuição dos retornos e indicadores de volume médio e acumulado, drawdown
  máximo e máxima histórica.
- **Análise técnica** — candlestick reamostrado da série de preços, curva de
  drawdown e estatísticas de intervalos em alta, melhor e pior intervalo e
  retorno médio.
- **Comparação** — desempenho relativo em base 100, matriz de correlação dos
  retornos diários e tabela com preço, variação e volatilidade de cada moeda.
- **Dados brutos** — série completa em tabela, download em CSV e ranking das 100
  maiores moedas por capitalização.

### Outros

- Paleta adaptada automaticamente ao tema claro ou escuro do Streamlit.
- Cores validadas para daltonismo, com legendas e rótulos diretos — a cor nunca
  é o único portador de significado.
- Erros de rede e de limite de requisições tratados com mensagem legível, sem
  traceback na tela.

---

## Instalação

Requisitos: **Python 3.9 ou superior** (testado em 3.13).

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Versões usadas no desenvolvimento:

| Biblioteca | Versão |
|---|---|
| streamlit | 1.57.0 |
| pandas | 2.3.2 |
| plotly | 6.7.0 |
| requests | 2.34.2 |

> **Streamlit 1.46 ou superior é necessário.** O app usa `width='stretch'`,
> `st.metric(border=True)`, `st.columns(vertical_alignment=...)` e
> `st.context.theme`, introduzidos nessas versões.


---

## Execução local

```bash
streamlit run dashboard.py
```

O navegador abre em `http://localhost:8501`.

Para expor na rede local ou em outra porta:

```bash
streamlit run dashboard.py --server.port 8502 --server.address 0.0.0.0
```

---

## Deploy no Streamlit Community Cloud

1. Acesse [share.streamlit.io](https://share.streamlit.io) e entre com a conta do
   GitHub que hospeda este repositório.
2. Clique em **Create app** → **Deploy a public app from GitHub**.
3. Preencha:
   - **Repository:** `<seu-usuário>/crypto-dashboard-streamlit`
   - **Branch:** `main`
   - **Main file path:** `dashboard.py`
4. Opcional, em **Advanced settings** → **Secrets**, cole a chave da API no mesmo
   formato do arquivo de exemplo:

   ```toml
   COINGECKO_API_KEY = "CG-sua-chave-aqui"
   ```

   Sem isso o painel funciona, mas fica sujeito ao limite público da CoinGecko —
   e um app publicado, acessado por várias pessoas, atinge esse limite bem mais
   rápido que o uso local.
5. **Deploy**. A primeira construção instala o `requirements.txt` e leva alguns
   minutos; depois cada `git push` na branch `main` republica o app
   automaticamente.

Para ajustar segredos depois, use **Manage app** → **Settings** → **Secrets**: a
alteração reinicia o app sozinha, sem novo commit.

---

## Chave de API (opcional, mas recomendada)

A API pública da CoinGecko permite poucas requisições por minuto e responde com
**HTTP 429** quando o limite é atingido. Uma chave gratuita do plano *Demo*
([coingecko.com/en/api/pricing](https://www.coingecko.com/en/api/pricing))
eleva esse limite.

O dashboard lê a chave de duas fontes, nesta ordem:

1. `.streamlit/secrets.toml`:

   ```toml
   COINGECKO_API_KEY = "CG-sua-chave-aqui"
   ```

2. Variável de ambiente:

   ```bash
   # Windows PowerShell
   $env:COINGECKO_API_KEY = "CG-sua-chave-aqui"
   # Linux / macOS
   export COINGECKO_API_KEY="CG-sua-chave-aqui"
   ```

Quando há chave, ela é enviada no cabeçalho `x-cg-demo-api-key` e a barra
lateral exibe "chave Demo ativa". Sem chave o painel continua funcionando, apenas
com o limite público.

> `secrets.toml` já está no `.gitignore` deste repositório. Use
> `.streamlit/secrets.toml.example` como modelo e nunca versione a chave.

---

## Estrutura do projeto

```
.
├── dashboard.py                 o painel inteiro
├── requirements.txt             dependências do deploy
├── README.md
├── .gitignore
└── .streamlit/
    └── secrets.toml.example     modelo da chave de API (copie para secrets.toml)
```

Todo o painel vive em um único módulo, `dashboard.py`, organizado em seções:

```
dashboard.py
├── Configuração da página      set_page_config, constantes, períodos, moedas
├── Paleta                      cores para tema claro e escuro; tema_ativo()
├── Acesso à API                ErroAPI, chave_api(), _requisitar()
│                               carregar_ranking(), carregar_historico()
├── Formatação e métricas       formata_*, granularidade(), regra_agregacao(),
│                               calcular_indicadores()
├── Base visual                 aplicar_layout(), _transparencia()
├── Gráficos                    grafico_preco(), grafico_velas(),
│                               grafico_drawdown(), grafico_retornos(),
│                               grafico_market_cap(), grafico_comparacao(),
│                               grafico_correlacao()
├── Barra lateral               filtros
└── Layout                      cabeçalho, KPIs e as quatro abas
```

As duas funções de rede são decoradas com `@st.cache_data(ttl=600)`: cada
combinação de moeda, referência e período é buscada uma única vez a cada dez
minutos.

---

## Como as métricas são calculadas

A granularidade da série muda conforme o período pedido — a CoinGecko devolve
pontos de 5 minutos para 1 dia, de 1 hora até 90 dias e diários acima disso. O
dashboard detecta o intervalo mediano entre observações e adapta os cálculos.

| Métrica | Definição |
|---|---|
| Variação no período | `último preço ÷ primeiro preço − 1` |
| Volatilidade anualizada | Desvio-padrão dos retornos por intervalo × √(intervalos por ano) |
| Amplitude | `máxima ÷ mínima − 1` no período |
| Drawdown | `preço ÷ máxima acumulada − 1`, em cada ponto |
| Drawdown máximo | Menor valor da série de drawdown |
| Intervalos em alta | Proporção de intervalos com retorno positivo |
| Correlação | Correlação de Pearson dos retornos diários entre as moedas comparadas |
| Desempenho relativo | Preço normalizado para 100 no início do período |

**Sobre o fuso horário:** a CoinGecko devolve os timestamps em UTC. A série é
convertida para `America/Sao_Paulo` e, em seguida, tem a marca de fuso
descartada — o Plotly.js não interpreta deslocamento horário, ele desenha o
instante exatamente como o recebe, então os eixos precisam receber a hora local
já resolvida. Eixos, rótulos, indicadores e a tabela de dados brutos mostram
portanto o horário de Brasília. Para outra praça, altere as constantes
`FUSO_EXIBICAO` e `ROTULO_FUSO` no topo de `dashboard.py`.

**Sobre o candlestick:** o endpoint `/market_chart` não devolve OHLC. Abertura,
máxima, mínima e fechamento são derivados da reamostragem da própria série de
preços — 1 hora, 4 horas, 1 dia ou 1 semana, conforme o tamanho da janela. Os
valores são fiéis aos pontos recebidos, mas não equivalem às velas oficiais de
uma corretora.

---

## Decisões de visualização

Escolhas deliberadas, caso você venha a estender o painel:

- **Uma medida por gráfico.** O gráfico principal mostra apenas o preço; a
  capitalização tem gráfico próprio e o volume aparece nos indicadores e na
  tabela de dados brutos. Empilhar duas escalas no mesmo eixo vertical sugeriria
  uma correlação que o alinhamento arbitrário das escalas inventa.
- **Sem legenda para uma série só.** Onde há uma única medida, o título a nomeia
  e a caixa de legenda seria ruído.
- **Comparação normalizada.** Moedas de preços muito diferentes só são
  comparáveis em um eixo único quando indexadas a uma base comum — daí a base
  100.
- **Cor por identidade, em ordem fixa.** Cada série recebe a cor da sua posição,
  e o limite de 8 moedas existe porque acima disso as cores deixam de ser
  distinguíveis. Verde e vermelho aparecem apenas onde significam alta e baixa.
- **Escala divergente na correlação.** Dois polos opostos com cinza neutro no
  meio, e o valor numérico impresso em cada célula.
- **Grade discreta.** Linhas finas, sem tracejado, e rótulos diretos apenas onde
  ajudam — nunca um número sobre cada ponto.

---

## Cache e limites da API

- Cada consulta fica em cache por **10 minutos** (`ttl=600`).
- Requisições que recebem HTTP 429 são repetidas até **3 vezes**, com espera
  crescente.
- A aba de comparação faz uma requisição por moeda selecionada; com muitas
  moedas e sem chave de API, o limite público é atingido rapidamente.
- O botão **Atualizar dados** limpa todo o cache e refaz as consultas.

---

## Solução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| "limite de requisições da API gratuita atingido (HTTP 429)" | Consultas demais em pouco tempo | Aguarde cerca de um minuto ou configure `COINGECKO_API_KEY` |
| "Lista de moedas indisponível" na barra lateral | `/coins/markets` falhou | O painel segue com o catálogo local de 8 moedas; tente atualizar depois |
| "falha de conexão" | Sem internet ou proxy bloqueando | Verifique a rede e o acesso a `api.coingecko.com` |
| "O período é curto demais para calcular a correlação diária" | Menos de três dias na janela | Selecione 7 dias ou mais |
| Horários fora do seu relógio | `FUSO_EXIBICAO` aponta para outro fuso | Ajuste `FUSO_EXIBICAO` e `ROTULO_FUSO` no topo de `dashboard.py` |
| `AttributeError` em `width` ou `border` | Streamlit anterior à 1.46 | `pip install --upgrade streamlit` |

---

## Aviso

Os dados são fornecidos pela [CoinGecko](https://www.coingecko.com) e têm
caráter informativo. Este painel não constitui recomendação de investimento.
