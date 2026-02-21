import os
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# === Configuração ===
load_dotenv()
INVESTIDOR10_COOKIE = os.getenv("INVESTIDOR10_COOKIE")
CARTEIRA_ID = os.getenv("CARTEIRA_ID")
FIIS_FILE = "fiis.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
}
if INVESTIDOR10_COOKIE:
    HEADERS["Cookie"] = INVESTIDOR10_COOKIE

COLORS = {"barato": "\033[32m", "caro": "\033[31m", "justo": "\033[33m", "-": "\033[0m"}
RESET = "\033[0m"


# === Funções auxiliares ===
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


# === Extração de informações da página ===
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
    if tipo in ["papel", "outro", "fundos", "fundo"]:
        if pvp < 1.02:
            return "barato"
        elif abs(pvp - 1.02) < 1e-6:
            return "justo"
        else:
            return "caro"
    if tipo in ["tijolo", "fundo misto", "misto"]:
        if pvp < 1.20:
            return "barato"
        elif abs(pvp - 1.20) < 1e-6:
            return "justo"
        else:
            return "caro"
    return "-"


# === Cálculo do Dividend Yield Mensal da Carteira ===
def calcular_dividend_yield_mensal(carteira):
    valor_total = 0.0
    renda_anual_total = 0.0
    total_atual = 0.0

    for fii in carteira:
        # saldo = safe_float(fii.get("equity_total"))
        saldo = safe_float(fii.get("quantity")) * safe_float(fii.get("avg_price"))
        yoc = safe_float(fii.get("yoc"))  # DY anual (%)
        total = safe_float(fii.get("equity_total"))  # valor atual do ativo

        if saldo is None or yoc is None:
            continue

        total_atual += total
        # print (total)

        valor_total += saldo
        renda_anual_total += saldo * (yoc / 100)

    if valor_total == 0:
        return None
   
    return {
        "valor_total": total_atual,
        "renda_anual": renda_anual_total,
        "renda_mensal": renda_anual_total / 12,
        "dy_mensal": (renda_anual_total / total_atual) / 12
    }


# === Main ===
def main():
    with open(FIIS_FILE, "r") as fh:
        fiis = [l.strip().upper() for l in fh if l.strip()]

    carteira = get_fiis_da_carteira()
    resumo_dy = calcular_dividend_yield_mensal(carteira)

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

        tipo_exibicao = "fof" if tipo == "fundos" else "fiagro" if tipo == "outro" else tipo

        resultados.append({
            "FII": ticker,
            "PRECO_ATUAL": f"{current_val:.2f}" if current_val is not None else "-",
            "PRECO_MEDIO": f"{avg_val:.2f}" if avg_val is not None else "-",
            "P/VP": f"{pvp_val:.2f}" if pvp_val is not None else "-",
            "TIPO": tipo_exibicao,
            "STATUS": definir_status(tipo, pvp_val)
        })

    header = ["FII", "PRECO_ATUAL", "PRECO_MEDIO", "P/VP", "TIPO", "STATUS"]
    col_w = {h: max(len(h), max(len(str(r[h])) for r in resultados)) for h in header}
    print(" | ".join(h.ljust(col_w[h]) for h in header))
    print("-" * sum(col_w.values()))

    for r in resultados:
        st = r["STATUS"]
        print(" | ".join([
            r["FII"].ljust(col_w["FII"]),
            r["PRECO_ATUAL"].ljust(col_w["PRECO_ATUAL"]),
            r["PRECO_MEDIO"].ljust(col_w["PRECO_MEDIO"]),
            r["P/VP"].ljust(col_w["P/VP"]),
            r["TIPO"].ljust(col_w["TIPO"]),
            f"{COLORS.get(st,'')}{st}{RESET}".ljust(col_w["STATUS"])
        ]))

    if resumo_dy:
        print("\n📊 RESUMO DA CARTEIRA (FIIs)")
        print(f"Valor total investido : R$ {resumo_dy['valor_total']:.2f}")
        print(f"Renda anual estimada  : R$ {resumo_dy['renda_anual']:.2f}")
        print(f"Renda mensal estimada : R$ {resumo_dy['renda_mensal']:.2f}")
        print(f"Dividend Yield mensal : {resumo_dy['dy_mensal'] * 100:.2f}%")


if __name__ == "__main__":
    main()
