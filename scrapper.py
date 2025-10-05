import os
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import math

# Cores ANSI para terminal
COLORS = {
    "barato": "\033[32m",  # verde
    "caro": "\033[31m",    # vermelho
    "justo": "\033[33m",   # amarelo
    "-": "\033[0m"         # sem cor
}
RESET_COLOR = "\033[0m"

# Carregar variáveis do arquivo .env
load_dotenv()

CARTEIRA_ID = os.getenv("CARTEIRA_ID")
COOKIE = os.getenv("INVESTIDOR10_COOKIE")

if not COOKIE:
    raise ValueError("Erro: Defina INVESTIDOR10_COOKIE no arquivo .env")
if not CARTEIRA_ID:
    raise ValueError("Erro: Defina CARTEIRA_ID no arquivo .env")

TICKERS_FILE = "tickers.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Cookie": COOKIE
}

def get_acoes_da_carteira():
    url = f"https://investidor10.com.br/wallet/api/proxy/wallet-app/summary/actives/{CARTEIRA_ID}/Ticker"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"Erro ao buscar ativos da carteira: {resp.status_code}")
        return []
    try:
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        print(f"Erro ao processar resposta da carteira: {e}")
        return []

def get_vpa_lpa_preco(ticker):
    url = f"https://investidor10.com.br/acoes/{ticker}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"Erro ao acessar página de {ticker}: {resp.status_code}")
        return None, None, None

    soup = BeautifulSoup(resp.text, "html.parser")
    vpa, lpa, preco_atual = None, None, None

    for span in soup.find_all("span"):
        if span.text.strip() == "VPA":
            next_span = span.find_next("span")
            if next_span:
                vpa = next_span.text.strip().replace(",", ".")
        elif span.text.strip() == "LPA":
            next_span = span.find_next("span")
            if next_span:
                lpa = next_span.text.strip().replace(",", ".")
    
    preco_span = soup.find("h2", class_="lh-4 mb-0 fw-700")
    if preco_span:
        preco_atual = preco_span.text.strip().replace("R$", "").replace(",", ".").strip()

    return vpa, lpa, preco_atual

def calcular_valor_justo(lpa, vpa):
    try:
        lpa = float(lpa)
        vpa = float(vpa)
        return round(math.sqrt(22.5 * lpa * vpa), 2)
    except (TypeError, ValueError):
        return None

def definir_status(preco_atual, valor_justo):
    try:
        preco = float(preco_atual)
        justo = float(valor_justo)
        if abs(preco - justo) / justo < 0.02:  # diferença menor que 2%
            return "justo"
        elif preco < justo:
            return "barato"
        else:
            return "caro"
    except:
        return "-"

def main():
    with open(TICKERS_FILE, "r") as f:
        tickers_busca = [line.strip().upper() for line in f if line.strip()]

    todas_acoes = get_acoes_da_carteira()
    carteira_dict = {acao.get("ticker_name"): acao for acao in todas_acoes}

    resultados = []
    for ticker in tickers_busca:
        preco_medio = "-"
        preco_atual = "-"
        valor_justo = "-"
        status = "-"

        if ticker in carteira_dict:
            acao = carteira_dict[ticker]
            preco_medio = f"{acao.get('avg_price'):.2f}" if acao.get("avg_price") is not None else "-"

        vpa, lpa, preco_site = get_vpa_lpa_preco(ticker)
        if preco_site:
            preco_atual = preco_site
        elif ticker in carteira_dict:
            preco_atual = f"{carteira_dict[ticker].get('current_price'):.2f}" if carteira_dict[ticker].get("current_price") else "-"

        valor_justo_calc = calcular_valor_justo(lpa, vpa)
        if valor_justo_calc:
            valor_justo = f"{valor_justo_calc:.2f}"

        status = definir_status(preco_atual, valor_justo) if preco_atual != "-" and valor_justo != "-" else "-"

        resultados.append({
            "TICKER": ticker,
            "PRECO_ATUAL": preco_atual,
            "PRECO_MEDIO": preco_medio,
            "VALOR_JUSTO": valor_justo,
            "STATUS": status
        })

    # Impressão formatada
    header = ["TICKER", "PRECO_ATUAL", "PRECO_MEDIO", "VALOR_JUSTO", "STATUS"]
    col_widths = {h: max(len(h), max(len(str(r[h])) for r in resultados)) for h in header}

    header_line = " | ".join(h.ljust(col_widths[h]) for h in header)
    print(header_line)
    print("-" * len(header_line))

    for r in resultados:
        status_colored = f"{COLORS.get(r['STATUS'], '')}{r['STATUS']}{RESET_COLOR}"
        line = " | ".join([
            str(r["TICKER"]).ljust(col_widths["TICKER"]),
            str(r["PRECO_ATUAL"]).ljust(col_widths["PRECO_ATUAL"]),
            str(r["PRECO_MEDIO"]).ljust(col_widths["PRECO_MEDIO"]),
            str(r["VALOR_JUSTO"]).ljust(col_widths["VALOR_JUSTO"]),
            status_colored.ljust(col_widths["STATUS"] + len(COLORS.get(r['STATUS'], '')) + len(RESET_COLOR))
        ])
        print(line)

if __name__ == "__main__":
    main()
