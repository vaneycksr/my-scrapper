#!/usr/bin/env python3
# scrapper-fiis.py
import os
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# carregar .env
load_dotenv()
INVESTIDOR10_COOKIE = os.getenv("INVESTIDOR10_COOKIE")
CARTEIRA_ID = os.getenv("CARTEIRA_ID")
FIIS_FILE = "fiis.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
}
if INVESTIDOR10_COOKIE:
    HEADERS["Cookie"] = INVESTIDOR10_COOKIE

# cores
COLORS = {"barato": "\033[32m", "caro": "\033[31m", "justo": "\033[33m", "-": "\033[0m"}
RESET = "\033[0m"

# ---------- utilitários ----------
def parse_brazilian_number(s):
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    s = re.sub(r'[^\d\-,\.]', '', s)
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
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

# ---------- extração ----------
def extract_pvp_from_soup(soup):
    el = soup.find(string=re.compile(r'P\/?VP', re.I))
    if el:
        try:
            parent = el.parent
            candidate = parent.find_next(["strong", "span", "b", "td", "div"])
            if candidate:
                val_txt = candidate.get_text(" ", strip=True)
                v = parse_brazilian_number(val_txt)
                if v is not None:
                    return v
        except:
            pass
    full = soup.get_text(" ", strip=True)
    m = re.search(r'P\/?VP[:\s]*([0-9\.,]+)', full, re.I)
    if m:
        return parse_brazilian_number(m.group(1))
    return None

def extract_price_by_sentence(soup, ticker):
    full = soup.get_text(" ", strip=True)
    if not full:
        return None
    text = re.sub(r'\s+', ' ', full)
    patterns = [
        rf'cot[aã]ção.*?\b{re.escape(ticker)}\b.*?R\$\s*([0-9\.,]+)',
        rf'\b{re.escape(ticker)}\b.*?R\$\s*([0-9\.,]+)',
        r'cot[aã]ção.*?R\$\s*([0-9\.,]+)',
        rf'({re.escape(ticker)}).{{0,40}}R\$\s*([0-9\.,]+)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            for g in reversed(m.groups()):
                if g:
                    v = parse_brazilian_number(g)
                    if v is not None:
                        return v
    m = re.search(r'R\$\s*([0-9\.,]+)', text)
    if m:
        return parse_brazilian_number(m.group(1))
    return None

def extract_tipo_from_articlebody(soup):
    meta = soup.find("meta", attrs={"name": "articleBody"})
    if meta and meta.get("content"):
        tipo = find_tipo_in_text(meta["content"])
        if tipo:
            return tipo
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            txt = script.string or ""
            m = re.search(r'"articleBody"\s*:\s*"(.*?)"', txt, re.DOTALL | re.IGNORECASE)
            if m:
                tipo = find_tipo_in_text(m.group(1))
                if tipo:
                    return tipo
        except:
            pass
    full = soup.get_text(" ", strip=True)
    return find_tipo_in_text(full) or "-"

def find_tipo_in_text(text):
    if not text:
        return None
    t = text.lower()
    for kw in ["tijolo", "papel", "fundo misto", "fundos", "misto", "outro"]:
        if kw in t:
            return kw
    return None

def get_fii_from_page(ticker):
    url = f"https://investidor10.com.br/fiis/{ticker.lower()}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    pvp = extract_pvp_from_soup(soup)
    price = extract_price_by_sentence(soup, ticker)
    tipo = extract_tipo_from_articlebody(soup)
    if price is None or tipo in (None, "-") or pvp is None:
        print(f"[debug] {ticker}: price={price}, pvp={pvp}, tipo={tipo}")
    return {"current_price": price, "p_vp": pvp, "fii_type": (tipo or "-")}

def get_fiis_da_carteira():
    url = f"https://investidor10.com.br/wallet/api/proxy/wallet-app/summary/actives/{CARTEIRA_ID}/Fii"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("data", [])
    except Exception:
        pass
    return []

def definir_status(fii_type, p_vp_val):
    tipo = (fii_type or "-").strip().lower()
    pvp = safe_float(p_vp_val)
    if pvp is None:
        return "-"
    if tipo in ["papel", "outro"]:
        if pvp < 1.02:
            return "barato"
        elif abs(pvp - 1.02) < 1e-6:
            return "justo"
        else:
            return "caro"
    if tipo in ["tijolo", "fundo misto", "fundos", "fundo", "misto"]:
        if pvp < 1.20:
            return "barato"
        elif abs(pvp - 1.20) < 1e-6:
            return "justo"
        else:
            return "caro"
    return "-"

# ---------- main ----------
def main():
    with open(FIIS_FILE, "r") as fh:
        fiis = [l.strip().upper() for l in fh if l.strip()]

    carteira = get_fiis_da_carteira()
    if not carteira:
        print("⚠️ Cookies inválidos/ausentes ou carteira não acessível — usando scraping público onde necessário.\n")

    carteira_map = {f.get("ticker_name"): f for f in carteira}
    resultados = []
    for ticker in fiis:
        data = carteira_map.get(ticker)
        if data:
            current_val = safe_float(data.get("current_price"))
            avg_val = safe_float(data.get("avg_price"))
            pvp_val = safe_float(data.get("p_vp"))
            tipo = (data.get("fii_type") or "-").strip().lower()
        else:
            scraped = get_fii_from_page(ticker) or {}
            current_val = safe_float(scraped.get("current_price"))
            avg_val = None
            pvp_val = safe_float(scraped.get("p_vp"))
            tipo = (scraped.get("fii_type") or "-").strip().lower()

        preco_atual = f"{current_val:.2f}" if current_val is not None else "-"
        preco_medio = f"{avg_val:.2f}" if avg_val is not None else "-"
        pvp_str = f"{pvp_val:.2f}" if pvp_val is not None else "-"
        status = definir_status(tipo, pvp_val)

        resultados.append({
            "FII": ticker,
            "PRECO_ATUAL": preco_atual,
            "PRECO_MEDIO": preco_medio,
            "P/VP": pvp_str,
            "TIPO": tipo,
            "STATUS": status
        })

    header = ["FII", "PRECO_ATUAL", "PRECO_MEDIO", "P/VP", "TIPO", "STATUS"]
    col_w = {h: max(len(h), max(len(str(r[h])) for r in resultados)) for h in header}
    head_line = " | ".join(h.ljust(col_w[h]) for h in header)
    print(head_line)
    print("-" * len(head_line))
    for r in resultados:
        st = r["STATUS"]
        colored = f"{COLORS.get(st,'')}{st}{RESET}"
        print(" | ".join([
            str(r["FII"]).ljust(col_w["FII"]),
            str(r["PRECO_ATUAL"]).ljust(col_w["PRECO_ATUAL"]),
            str(r["PRECO_MEDIO"]).ljust(col_w["PRECO_MEDIO"]),
            str(r["P/VP"]).ljust(col_w["P/VP"]),
            str(r["TIPO"]).ljust(col_w["TIPO"]),
            colored.ljust(col_w["STATUS"] + len(COLORS.get(st,'')) + len(RESET))
        ]))

if __name__ == "__main__":
    main()
