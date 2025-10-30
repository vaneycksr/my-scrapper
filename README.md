# 📈 My Scrapper

Scripts em **Python** para coletar informações de **ações** e **fundos imobiliários (FIIs)** diretamente do [Investidor10](https://investidor10.com.br).  
O projeto utiliza tanto a **API interna** (quando disponível via autenticação por cookie) quanto **scraping público** das páginas do site para obter dados de ativos que não estejam na sua carteira.

---

## 🧩 O que este projeto faz

### 🟦 `scrapper-acoes.py`
Coleta informações sobre **ações** listadas em `tickers.txt`.

**Retorna:**
- 🏷️ **Ticker**
- 💰 **Preço atual**
- 📊 **Preço médio** (da sua carteira Investidor10, se disponível)
- ⚖️ **Valor justo** (√(22,5 × LPA × VPA))
- 🟢 **Status:** “barato”, “justo” ou “caro”


### 🟩 `scrapper-fiis.py`
Coleta informações sobre **fundos imobiliários (FIIs)** listados em `fiis.txt`.

**Retorna:**
- 🏷️ **Ticker (FII)**
- 💰 **Preço atual**
- 📊 **Preço médio** (da carteira Investidor10, se disponível)
- 🧾 **P/VP**
- 🏢 **Tipo do fundo** (*tijolo, papel, fiagro, fof, etc.*) — exibido em minúsculas
- 🟢 **Status:** “barato”, “justo” ou “caro”, conforme regras por tipo

Regras principais para STATUS (P/VP):
- **Papel / Fundo / Fundos / Outro (fiagro)** → barato se P/VP < 1.02
- **Tijolo / Fundo misto / Misto** → barato se P/VP < 1.20

---

## ⚙️ Requisitos

Instale as dependências com:

```bash
pip install requests beautifulsoup4 python-dotenv
```

---

## 🔐 Configuração

Crie um arquivo `.env` na raiz do projeto com as variáveis:

```env
# ID da sua carteira no Investidor10 (obtido pela URL da carteira)
CARTEIRA_ID=123456

# Cookie da sua conta Investidor10 (NÃO compartilhe nem suba ao GitHub)
INVESTIDOR10_COOKIE=coloque_seu_cookie_aqui
```

> ⚠️ **Importante:** o arquivo `.env` **não deve** ser versionado. Adicione-o ao `.gitignore`:
>
> ```
> .env
> ```

---

## 📁 Estrutura do projeto

```
.
├── scrapper-acoes.py        # Script para ações
├── scrapper-fiis.py         # Script para FIIs
├── tickers.txt              # Lista de ações (ex: VALE3, ITUB4)
├── fiis.txt                 # Lista de FIIs (ex: HGLG11, MXRF11)
└── .env                     # Suas credenciais (não versionar)
```

---

## ▶️ Como executar

### Ações
```bash
python scrapper-acoes.py
```

### FIIs
```bash
python scrapper-fiis.py
```

Os resultados são exibidos em formato de tabela no terminal, com colunas alinhadas e cores indicando o status:
- 🟢 **barato**
- 🟡 **justo**
- 🔴 **caro**

Se os cookies estiverem ausentes ou inválidos, os scripts exibem a mensagem:

```
⚠️ Cookies inválidos/ausentes ou carteira não acessível — usando scraping público onde necessário.
```

E continuam funcionando via scraping público.

---

## 🖥️ Exemplo de saída

### Para ações

```
TICKER | PRECO_ATUAL | PRECO_MEDIO | VALOR_JUSTO | STATUS
----------------------------------------------------------
VALE3  | 58.59        | 57.09       | 82.31       | barato
ITUB4  | 38.21        | 30.14       | 41.56       | justo
BBAS3  | 52.80        | 53.20       | 49.00       | caro
```

### Para FIIs

```
⚠️ Cookies inválidos/ausentes ou carteira não acessível — usando scraping público onde necessário.

FII    | PRECO_ATUAL | PRECO_MEDIO | P/VP | TIPO        | STATUS
----------------------------------------------------------------
HGRU11 | 126.65      | 120.06      | 0.99 | fundo misto | barato
KISU11 | 6.73        | 7.22        | 0.85 | fof         | barato
RURA11 | 8.19        | 8.23        | 0.79 | fiagro      | barato
MXRF11 | 9.67        | 9.35        | 1.03 | papel       | caro
```

---

## 🧠 Como funciona

1. O script tenta acessar dados via **API autenticada** do Investidor10, usando o cookie do `.env`.
2. Se o cookie estiver inválido/ausente, exibe a mensagem de aviso e utiliza **scraping público** das páginas:
   - `/acoes/{ticker}` para ações
   - `/fiis/{ticker}` para FIIs
3. A extração de dados combina leitura direta da resposta JSON da API (quando disponível) e parsing do HTML público (BeautifulSoup) para obter preços, P/VP, LPA, VPA e tipo.

---

## 💡 Observações

- Não são armazenadas credenciais no repositório.
- O projeto depende da estrutura atual do Investidor10; alterações no site podem exigir ajustes no código.
- Uso destinado a análises pessoais.

