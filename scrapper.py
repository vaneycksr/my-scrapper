#!/usr/bin/env python3
# scrapper-acoes.py (versão corrigida)

import os
import re
import math
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

INVESTIDOR10_COOKIE = os.getenv("INVESTIDOR10_COOKIE")
CARTEIRA_ID = os.getenv("CARTEIRA_ID")
TICKERS_FILE = "tickers.txt"

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
if INVESTIDOR10_COOKIE:
    HEADERS["Cookie"] = INVESTIDOR10_COOKIE

# cores
COLORS = {"barato": "\033[32m", "caro": "\033[31m", "justo": "\033[33m", "-": "\033[0m"}
RESET = "\033[0m"

# ---------------- utilitários ----------------
def parse_brazilian_number(s):
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    s = re.sub(r'[^\d\-,\.]', '', s)
    # if both present, assume '.' thousands and ',' decimal
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        if ',' in s and '.' not in s:
            s = s.replace(',', '.')
    try:
        return float(s)
    except:
        return None

def safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

# ---------------- buscar na carteira ----------------
def get_acoes_da_carteira():
    if not INVESTIDOR10_COOKIE or not CARTEIRA_ID:
        return []
    url = f"https://investidor10.com.br/wallet/api/proxy/wallet-app/summary/actives/{CARTEIRA_ID}/Ticker"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            j = r.json()
            return j.get("data", [])
    except Exception:
        pass
    return []

# ---------------- scraping público da página da ação ----------------
def extract_price_from_text_by_ticker(text, ticker):
    """
    Try patterns that explicitly mention the ticker + R$ value (conservative).
    """
    # normalize spaces
    txt = re.sub(r'\s+', ' ', text)
    patterns = [
        rf'cot[aã]ção.*?\b{re.escape(ticker)}\b.*?R\$\s*([0-9\.,]+)',
        rf'\b{re.escape(ticker)}\b.*?R\$\s*([0-9\.,]+)',
        rf'{re.escape(ticker)}[:\s-]{{0,5}}R\$\s*([0-9\.,]+)',
    ]
    for pat in patterns:
        m = re.search(pat, txt, re.IGNORECASE)
        if m:
            # take last capturing group that's numeric
            groups = [g for g in m.groups() if g]
            for g in reversed(groups):
                v = parse_brazilian_number(g)
                if v is not None:
                    return v
    return None

def find_price_by_selectors(soup):
    # search elements with class names that hint price
    candidate_subs = ["price", "preco", "valor", "cotac", "last", "atual", "cotação", "cotacao"]
    for el in soup.find_all(attrs={"class": True}):
        cls = el.get("class")
        class_text = " ".join(cls).lower() if isinstance(cls, list) else str(cls).lower()
        if any(sub in class_text for sub in candidate_subs):
            txt = el.get_text(" ", strip=True)
            v = parse_brazilian_number(txt)
            if v is not None and v > 0:
                return v
    # look for strong tags near price-like numbers
    for tag in ("strong", "h1", "h2", "h3", "span", "div"):
        for el in soup.find_all(tag):
            txt = el.get_text(" ", strip=True)
            if re.search(r'R\$', txt) or re.search(r'\d+[.,]\d{2}', txt):
                v = parse_brazilian_number(txt)
                if v is not None and v > 0 and v < 10000:
                    return v
    return None

def extract_lpa_vpa_from_soup(soup):
    lpa = None
    vpa = None
    # strategy 1: look for exact labels in table rows or spans
    for label in soup.find_all(["span","td","th","strong","b"]):
        t = label.get_text(" ", strip=True).upper()
        if t == "LPA" or t.startswith("LPA " ) or t.startswith("LPA:"):
            # try next numeric sibling or next element
            nxt = label.find_next(["span","td","strong","b"])
            if nxt:
                lpa = parse_brazilian_number(nxt.get_text(" ", strip=True))
        if t == "VPA" or t.startswith("VPA ") or t.startswith("VPA:"):
            nxt = label.find_next(["span","td","strong","b"])
            if nxt:
                vpa = parse_brazilian_number(nxt.get_text(" ", strip=True))
    # strategy 2: look for "LPA: 1,23" pattern in full text
    full = soup.get_text(" ", strip=True)
    if lpa is None:
        m = re.search(r'LPA[:\s]*([0-9\.,]+)', full, re.IGNORECASE)
        if m:
            lpa = parse_brazilian_number(m.group(1))
    if vpa is None:
        m = re.search(r'VPA[:\s]*([0-9\.,]+)', full, re.IGNORECASE)
        if m:
            vpa = parse_brazilian_number(m.group(1))
    return lpa, vpa

def get_acao_publica(ticker):
    url = f"https://investidor10.com.br/acoes/{ticker.lower()}"
    try:
        r = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=10)
    except Exception:
        return {}
    if r.status_code != 200:
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    full_text = soup.get_text(" ", strip=True)

    # 1) try to extract price by explicit sentence with ticker
    price = extract_price_from_text_by_ticker(full_text, ticker)
    # 2) if not found, try selectors (class names etc)
    if price is None:
        price = find_price_by_selectors(soup)
    # 3) do NOT use aggressive fallback to first R$ in page; only as last resort:
    if price is None:
        m = re.search(r'R\$\s*([0-9\.,]+)', full_text)
        if m:
            cand = parse_brazilian_number(m.group(1))
            # accept only if within reasonable FII/stock range:
            if cand is not None and 0 < cand < 10000:
                price = cand

    lpa, vpa = extract_lpa_vpa_from_soup(soup)

    # debug when missing important parts
    if price is None or (lpa is None and vpa is None):
        print(f"[debug] {ticker}: price={price}, lpa={lpa}, vpa={vpa}")

    return {"preco_atual": price, "lpa": lpa, "vpa": vpa}

# ---------------- cálculo e status ----------------
def calcular_valor_justo(lpa, vpa):
    if lpa is None or vpa is None:
        return None
    try:
        return math.sqrt(22.5 * float(lpa) * float(vpa))
    except Exception:
        return None

def definir_status(preco_atual, valor_justo):
    if preco_atual is None or valor_justo is None:
        return "-"
    try:
        preco = float(preco_atual)
        justo = float(valor_justo)
    except:
        return "-"
    # tolerance 2% for "justo"
    if abs(preco - justo) / justo <= 0.02:
        return "justo"
    elif preco < justo:
        return "barato"
    else:
        return "caro"

# ---------------- main ----------------
def main():
    # read tickers
    with open(TICKERS_FILE, "r") as f:
        tickers = [l.strip().upper() for l in f if l.strip()]

    # try to get carteira data (may be empty if cookie invalid)
    carteira = get_acoes_da_carteira()
    carteira_map = {a.get("ticker_name"): a for a in carteira} if carteira else {}

    if not INVESTIDOR10_COOKIE or not carteira:
        print("⚠️ Cookies inválidos/ausentes ou carteira não acessível — usando scraping público onde necessário.\n")

    resultados = []
    for ticker in tickers:
        # defaults
        preco_atual = None
        preco_medio = None
        lpa = None
        vpa = None

        # if present in carteira and carteira has values, use them for prices/avg
        if ticker in carteira_map:
            ac = carteira_map[ticker]
            preco_atual = safe_float(ac.get("current_price"))
            preco_medio = safe_float(ac.get("avg_price"))
            # some endpoints might include lpa/vpa, but often not; try to read if present
            lpa = safe_float(ac.get("lpa")) or None
            vpa = safe_float(ac.get("vpa")) or None

        # If missing critical public fields, scrape from public page
        if preco_atual is None or lpa is None or vpa is None:
            public = get_acao_publica(ticker)
            # only overwrite if public returns something
            if public.get("preco_atual") is not None:
                preco_atual = public.get("preco_atual")
            if public.get("lpa") is not None:
                lpa = public.get("lpa")
            if public.get("vpa") is not None:
                vpa = public.get("vpa")

        valor_justo = calcular_valor_justo(lpa, vpa)
        status = definir_status(preco_atual, valor_justo)

        resultados.append({
            "TICKER": ticker,
            "PRECO_ATUAL": f"{preco_atual:.2f}" if preco_atual is not None else "-",
            "PRECO_MEDIO": f"{preco_medio:.2f}" if preco_medio is not None else "-",
            "VALOR_JUSTO": f"{valor_justo:.2f}" if valor_justo is not None else "-",
            "STATUS": status
        })

    # print table aligned
    header = ["TICKER", "PRECO_ATUAL", "PRECO_MEDIO", "VALOR_JUSTO", "STATUS"]
    col_w = {h: max(len(h), max(len(str(r[h])) for r in resultados)) for h in header}
    head = " | ".join(h.ljust(col_w[h]) for h in header)
    print(head)
    print("-" * len(head))
    for r in resultados:
        st = r["STATUS"]
        colored = f"{COLORS.get(st,'')}{st}{RESET}" if st != "-" else "-"
        print(" | ".join([
            str(r["TICKER"]).ljust(col_w["TICKER"]),
            str(r["PRECO_ATUAL"]).ljust(col_w["PRECO_ATUAL"]),
            str(r["PRECO_MEDIO"]).ljust(col_w["PRECO_MEDIO"]),
            str(r["VALOR_JUSTO"]).ljust(col_w["VALOR_JUSTO"]),
            (colored if colored != "-" else "-").ljust(col_w["STATUS"] + (len(COLORS.get(st,'')) + len(RESET) if st!="- " else 0))
        ]))

if __name__ == "__main__":
    main()
