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

if not INVESTIDOR10_COOKIE or not CARTEIRA_ID:
    raise ValueError("Defina INVESTIDOR10_COOKIE e CARTEIRA_ID no arquivo .env")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
    "Cookie": INVESTIDOR10_COOKIE
}

# cores
COLORS = {"barato": "\033[32m", "caro": "\033[31m", "justo": "\033[33m", "-": "\033[0m"}
RESET = "\033[0m"

# ---------- utilitários ----------
def parse_brazilian_number(s):
    """Converte texto com formato brasileiro para float (aceita '1.234,56' ou '1234.56')."""
    if s is None:
        return None
    s = str(s)
    s = s.strip()
    if s == "":
        return None
    # remover tudo exceto dígitos, ponto e vírgula e sinal
    s = re.sub(r'[^\d\-,\.]', '', s)
    # se ambos '.' e ',' presentes: assumir '.' milhares e ',' decimal
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        # se só tem ',' -> decimal
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

# ---------- extração: P/VP (modo anterior, considerado estável) ----------
def extract_pvp_from_soup(soup):
    """
    Procura por 'P/VP' no HTML e tenta extrair o número próximo.
    Retorna float ou None.
    """
    # 1) procurar string 'P/VP' (caso comum)
    el = soup.find(string=re.compile(r'P\/?VP', re.I))
    if el:
        # tentar pegar próximo elemento numérico (strong/span etc)
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
    # 2) procurar no texto completo: "P/VP: 1,02" ou "P/VP 1.02"
    full = soup.get_text(" ", strip=True)
    m = re.search(r'P\/?VP[:\s]*([0-9\.,]+)', full, re.I)
    if m:
        return parse_brazilian_number(m.group(1))
    return None

# ---------- extração: preço adaptativo via frase com ticker ----------
def extract_price_by_sentence(soup, ticker):
    """
    Busca frases contendo o ticker seguidas de 'R$ <valor>'.
    Ex.: "A cotação hoje de HGLG11 é de R$ 159,60"
    Estratégias (em ordem):
      - procurar regex que contenha o ticker e R$
      - procurar 'cotação' + ticker + R$
      - procurar ticker seguido por R$
      - procurar padrões 'cotação hoje' + R$ (sem ticker) como fallback
    Retorna float ou None.
    """
    full = soup.get_text(" ", strip=True)
    if not full:
        return None
    # normalize spaces
    text = re.sub(r'\s+', ' ', full)

    # patterns to try (ticker inserted case-insensitive)
    patterns = [
        # "A cotação hoje de HGLG11 é de R$ 159,60"
        rf'cot[aã]ção.*?\b{re.escape(ticker)}\b.*?R\$\s*([0-9\.,]+)',
        # "HGLG11: R$ 159,60" or "HGLG11 é de R$ 159,60"
        rf'\b{re.escape(ticker)}\b.*?R\$\s*([0-9\.,]+)',
        # "cotação hoje ... R$ 159,60" (sem ticker)
        r'cot[aã]ção.*?R\$\s*([0-9\.,]+)',
        # any R$ number near mention of ticker within small window
        rf'({re.escape(ticker)}).{{0,40}}R\$\s*([0-9\.,]+)',
    ]

    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            # capture may be group 1 or 2 depending on pattern
            # find last group that matches a number
            for g in reversed(m.groups()):
                if g:
                    v = parse_brazilian_number(g)
                    if v is not None:
                        return v
    # fallback: any R$ number in page (less reliable)
    m = re.search(r'R\$\s*([0-9\.,]+)', text)
    if m:
        return parse_brazilian_number(m.group(1))
    return None

# ---------- extração: tipo a partir de articleBody ----------
def extract_tipo_from_articlebody(soup):
    """
    Tenta extrair 'articleBody' (meta name=articleBody ou JSON-LD) e dentro dele
    identificar palavras-chave do tipo do FII. Retorna lowercase string ou '-'.
    """
    # 1) meta name="articleBody"
    meta = soup.find("meta", attrs={"name": "articleBody"})
    if meta and meta.get("content"):
        body = meta.get("content")
        tipo = find_tipo_in_text(body)
        if tipo:
            return tipo

    # 2) JSON-LD search for articleBody
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            txt = script.string or ""
            m = re.search(r'"articleBody"\s*:\s*"(.*?)"', txt, re.DOTALL | re.IGNORECASE)
            if m:
                body = m.group(1)
                tipo = find_tipo_in_text(body)
                if tipo:
                    return tipo
        except:
            pass

    # 3) fallback: search in full page text for keywords
    full = soup.get_text(" ", strip=True)
    return find_tipo_in_text(full) or "-"

def find_tipo_in_text(text):
    if not text:
        return None
    t = text.lower()
    keywords = ["tijolo", "papel", "fundo misto", "fundos", "misto", "outro"]
    for kw in keywords:
        if kw in t:
            return kw
    return None

# ---------- busca pública por FII (página /fiis/{ticker}) ----------
def get_fii_from_page(ticker):
    url = f"https://investidor10.com.br/fiis/{ticker.lower()}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")

    # P/VP (extracted via previous stable method)
    pvp = extract_pvp_from_soup(soup)

    # price via sentence with ticker
    price = extract_price_by_sentence(soup, ticker)

    # tipo from articleBody
    tipo = extract_tipo_from_articlebody(soup)

    # debug if something missing
    if price is None or tipo in (None, "-") or pvp is None:
        # debug line (visible so you can paste here if still problematic)
        print(f"[debug] {ticker}: price={price}, pvp={pvp}, tipo={tipo}")

    return {"current_price": price, "p_vp": pvp, "fii_type": (tipo or "-")}

# ---------- carteira (endpoint) ----------
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

# ---------- status logic ----------
def definir_status(fii_type, p_vp_val):
    try:
        tipo = (fii_type or "-").strip().lower()
        pvp = safe_float(p_vp_val)
    except:
        return "-"
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
    # ler fiis.txt
    with open(FIIS_FILE, "r") as fh:
        fiis = [l.strip().upper() for l in fh if l.strip()]

    carteira = get_fiis_da_carteira()
    carteira_map = {f.get("ticker_name"): f for f in carteira}

    resultados = []
    for ticker in fiis:
        data = carteira_map.get(ticker)
        if data:
            # preferir dados da carteira para preço/avg
            current_val = safe_float(data.get("current_price"))
            avg_val = safe_float(data.get("avg_price"))
            pvp_val = safe_float(data.get("p_vp"))
            tipo = (data.get("fii_type") or "-").strip().lower()
        else:
            # raspar a página pública
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

    # imprimir tabela alinhada
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
