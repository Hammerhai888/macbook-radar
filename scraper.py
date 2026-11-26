import asyncio
import json
import os
import re
import hashlib
import requests
from playwright.async_api import async_playwright

# ==========================================
# 1. DEIN PUSH-KANAL (NTFY.SH)
# ==========================================
NTFY_TOPIC = "tobi_macbook_alarm_9941"  # <-- Prüfe, ob hier dein Kanalname steht!

# ==========================================
# 2. PREIS-LIMITS
# ==========================================
MAX_PREIS_CHF = 1000.00           # Reguläre Händler Schweiz
MAX_PREIS_GEBRAUCHT_CHF = 900.00  # Tutti.ch & Ricardo.ch (Sofort-Kaufen)
MAX_PREIS_EUR = 1090.00           # Reguläre Händler DE / AT (entspricht ca. 1000 CHF)
MIN_PREIS = 490.00                # Filtert günstiges Zubehör & Raten aus

CACHE_FILE = "seen_deals.json"
PARALLELE_TABS = 4

# ==========================================
# 3. AUSSCHLUSS-FILTER (ZUBEHÖR, DEFEKTE, ABGELAUFENE DEALS)
# ==========================================
BLACKLIST = [
    "hülle", "tasche", "sleeve", "case", "folie", "schutzfolie", "adapter",
    "netzteil", "kabel", "tastaturschutz", "aufkleber", "skin", "ständer",
    "hub", "dock", "docking", "display", "monitor", "applecare", "care+",
    "garantie", "versicherung", "schutzplan", "miete", "abo", "monatlich",
    "13\"", "13 zoll", "13.6", "14\"", "16\"", "pro 16", "pro 14", "ipad",
    "ersatzteil", "akku", "tastatur", "bildschirm", "reparatur", "uvp",
    "abgelaufen", "beendet", "ausverkauft", "nicht verfügbar", "nicht mehr verfügbar", "expired",
    "defekt", "bastler", "displaybruch", "wasserschaden", "icloud", "gesperrt",
    "intel", "2015", "2016", "2017", "2018", "2019", "2020"
]

# ==========================================
# 4. ALLE 49 QUELLEN (CH, DE, AT)
# ==========================================
TARGETS = [
    # --- SCHWEIZ: Kleinanzeigen & Gebraucht (Limit: 900 CHF) ---
    {"name": "Tutti.ch (Suche: Air 15)", "currency": "CHF", "max_price": MAX_PREIS_GEBRAUCHT_CHF, "url": "https://www.tutti.ch/de/q/MacBook+Air+15"},
    {"name": "Tutti.ch (Suche: Air 15.3)", "currency": "CHF", "max_price": MAX_PREIS_GEBRAUCHT_CHF, "url": "https://www.tutti.ch/de/q/MacBook+Air+15.3"},
    {"name": "Ricardo.ch (Sofort-Kaufen)", "currency": "CHF", "max_price": MAX_PREIS_GEBRAUCHT_CHF, "url": "https://www.ricardo.ch/de/s/MacBook%20Air/?offer_type=fixed_price"},

    # --- SCHWEIZ: Preisvergleiche & Deal-Communities (Limit: 1000 CHF) ---
    {"name": "Toppreise.ch (Alle CH-Shops)", "currency": "CHF", "url": "https://www.toppreise.ch/produktsuche?q=macbook%20air%2015"},
    {"name": "Preispirat.ch (CH-Schnäppchen)", "currency": "CHF", "url": "https://www.preispirat.ch/?s=MacBook+Air+15"},
    {"name": "Dealbunny.ch", "currency": "CHF", "url": "https://www.dealbunny.ch/?s=MacBook+Air+15"},

    # --- SCHWEIZ: Grosse Händler & Elektronikmärkte (Limit: 1000 CHF) ---
    {"name": "Digitec.ch", "currency": "CHF", "url": "https://www.digitec.ch/de/search?q=MacBook+Air+15"},
    {"name": "Galaxus.ch", "currency": "CHF", "url": "https://www.galaxus.ch/de/search?q=MacBook+Air+15"},
    {"name": "Brack.ch", "currency": "CHF", "url": "https://www.brack.ch/search?query=MacBook+Air+15"},
    {"name": "Interdiscount.ch", "currency": "CHF", "url": "https://www.interdiscount.ch/de/search?text=MacBook+Air+15"},
    {"name": "MediaMarkt.ch", "currency": "CHF", "url": "https://www.mediamarkt.ch/de/search.html?query=MacBook+Air+15"},
    {"name": "Fust.ch", "currency": "CHF", "url": "https://www.fust.ch/search?text=MacBook+Air+15"},
    {"name": "Manor.ch", "currency": "CHF", "url": "https://www.manor.ch/de/search?q=MacBook+Air+15"},
    {"name": "Fnac.ch", "currency": "CHF", "url": "https://www.fr.fnac.ch/SearchResult/ResultList.aspx?Search=MacBook+Air+15"},
    {"name": "Migros / Melectronics", "currency": "CHF", "url": "https://www.migros.ch/de/search?query=MacBook+Air+15"},
    {"name": "Coop / Microspot", "currency": "CHF", "url": "https://www.coop.ch/de/search/?text=MacBook+Air+15"},

    # --- SCHWEIZ: Apple Reseller, IT-Shops & Refurbished (Limit: 1000 CHF) ---
    {"name": "Apple Refurbished CH", "currency": "CHF", "url": "https://www.apple.com/ch-de/shop/refurbished/mac/macbook-air"},
    {"name": "DQ Solutions (Apple Premium)", "currency": "CHF", "url": "https://www.dq-solutions.ch/de/search?q=MacBook+Air+15"},
    {"name": "DataQuest.ch", "currency": "CHF", "url": "https://www.dataquest.ch/search?q=MacBook+Air+15"},
    {"name": "HeinigerAG.ch", "currency": "CHF", "url": "https://www.heinigerag.ch/de/search?q=MacBook+Air+15"},
    {"name": "Techmania.ch", "currency": "CHF", "url": "https://www.techmania.ch/de/search?q=MacBook+Air+15"},
    {"name": "ARP.ch", "currency": "CHF", "url": "https://www.arp.ch/search?q=MacBook+Air+15"},
    {"name": "PC-Ostschweiz.ch", "currency": "CHF", "url": "https://www.pc-ostschweiz.ch/de/search?q=MacBook+Air+15"},
    {"name": "Conrad.ch", "currency": "CHF", "url": "https://www.conrad.ch/de/search.html?search=MacBook%20Air%2015"},
    {"name": "Revendo.ch (Refurbished)", "currency": "CHF", "url": "https://revendo.ch/de/kaufen/macbook/?q=MacBook+Air+15"},
    {"name": "BackMarket.ch (Refurbished)", "currency": "CHF", "url": "https://www.backmarket.ch/de-ch/search?q=MacBook+Air+15"},

    # --- DEUTSCHLAND: Preisvergleiche & Schnäppchen-Portale (Limit: 1090 EUR) ---
    {"name": "Geizhals.de (Alle DE-Shops)", "currency": "EUR", "url": "https://geizhals.de/?fs=MacBook+Air+15&hloc=de"},
    {"name": "idealo.de (Alle DE-Shops)", "currency": "EUR", "url": "https://www.idealo.de/preisvergleich/MainSearchProductCategory.html?q=MacBook+Air+15"},
    {"name": "mydealz.de (DE-Schnäppchen)", "currency": "EUR", "url": "https://www.mydealz.de/search?q=MacBook+Air+15&hide_expired=true"},
    {"name": "DealDoktor.de", "currency": "EUR", "url": "https://www.dealdoktor.de/?s=MacBook+Air+15"},
    {"name": "MyTopDeals.net", "currency": "EUR", "url": "https://www.mytopdeals.net/?s=MacBook+Air+15"},
    {"name": "Preisjaeger.at", "currency": "EUR", "url": "https://www.preisjaeger.at/search?q=MacBook+Air+15&hide_expired=true"},

    # --- DEUTSCHLAND: Grosse Händler & Elektronikketten (Limit: 1090 EUR) ---
    {"name": "Amazon.de", "currency": "EUR", "url": "https://www.amazon.de/s?k=MacBook+Air+15"},
    {"name": "MediaMarkt.de", "currency": "EUR", "url": "https://www.mediamarkt.de/de/search.html?query=MacBook+Air+15"},
    {"name": "Saturn.de", "currency": "EUR", "url": "https://www.saturn.de/de/search.html?query=MacBook+Air+15"},
    {"name": "Cyberport.de", "currency": "EUR", "url": "https://www.cyberport.de/tools/search-results.html?q=MacBook+Air+15"},
    {"name": "Notebooksbilliger.de", "currency": "EUR", "url": "https://www.notebooksbilliger.de/suche?q=MacBook+Air+15"},
    {"name": "OTTO.de", "currency": "EUR", "url": "https://www.otto.de/technik/apple/macbook-air/?bildschirmgroesse=15-zoll"},
    {"name": "Computeruniverse.net", "currency": "EUR", "url": "https://www.computeruniverse.net/de/search?query=MacBook+Air+15"},
    {"name": "Alternate.de", "currency": "EUR", "url": "https://www.alternate.de/listing.xhtml?q=MacBook+Air+15"},
    {"name": "Alza.de", "currency": "EUR", "url": "https://www.alza.de/search.htm?exps=MacBook%20Air%2015"},
    {"name": "Euronics.de", "currency": "EUR", "url": "https://www.euronics.de/search?sSearch=MacBook+Air+15"},
    {"name": "Expert.de", "currency": "EUR", "url": "https://www.expert.de/shop/suche?q=MacBook+Air+15"},
    {"name": "Conrad.de", "currency": "EUR", "url": "https://www.conrad.de/de/search.html?search=MacBook%20Air%2015"},
    {"name": "Galaxus.de", "currency": "EUR", "url": "https://www.galaxus.de/de/search?q=MacBook+Air+15"},
    {"name": "Comspot.de (Apple Reseller)", "currency": "EUR", "url": "https://www.comspot.de/search?sSearch=MacBook+Air+15"},
    {"name": "MacTrade.de", "currency": "EUR", "url": "https://www.mactrade.de/catalogsearch/result/?q=MacBook+Air+15"},
    {"name": "Apple Refurbished DE", "currency": "EUR", "url": "https://www.apple.com/de/shop/refurbished/mac/macbook-air"},
    {"name": "BackMarket.de (Refurbished)", "currency": "EUR", "url": "https://www.backmarket.de/de-de/search?q=MacBook+Air+15"},

    # --- ÖSTERREICH: MediaMarkt & Preisvergleich (Limit: 1090 EUR) ---
    {"name": "MediaMarkt.at", "currency": "EUR", "url": "https://www.mediamarkt.at/de/search.html?query=MacBook+Air+15"},
    {"name": "Geizhals.at (AT-Shops)", "currency": "EUR", "url": "https://geizhals.at/?fs=MacBook+Air+15&hloc=at"},
]

# ==========================================
# 5. PROGRAMM-LOGIK
# ==========================================
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_cache(cache_set):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(cache_set), f, indent=2)

def send_push(shop, title, price, currency, url):
    msg = f"{title}\nPreis: {price:.2f} {currency} ({shop})"
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=msg.encode("utf-8"),
            headers={
                "Title": f"MacBook Air 15\": {price:.0f} {currency} ({shop})".encode("utf-8"),
                "Click": url,
                "Tags": "rotating_light,laptop"
            },
            timeout=10
        )
        print(f"[PUSH] {msg}")
    except Exception as e:
        print(f"[PUSH FEHLER] {e}")

def parse_price(text):
    cleaned_text = re.sub(r"\b\d+\s*(?:GB|TB|MHz|GHz|Core|W)\b", "", text, flags=re.I)
    cleaned_text = re.sub(r"\(\s*202\d\s*\)", "", cleaned_text)

    pattern = r"(?:(?:CHF|EUR|€|Fr\.?)\s*(\d{1,4}['’.,]?\d{2,3}(?:[.,]\d{2}|[.,]-)?)|(\d{1,4}['’.,]?\d{2,3}(?:[.,]\d{2}|[.,]-)?)\s*(?:CHF|EUR|€|Fr\.?))"
    matches = re.findall(pattern, cleaned_text, flags=re.I)

    prices = []
    for m1, m2 in matches:
        raw_num = m1 or m2
        clean = raw_num.replace("'", "").replace("’", "").replace(".-", ".00").replace(",-", ".00")
        if "," in clean and "." in clean:
            if clean.rfind(",") > clean.rfind("."):
                clean = clean.replace(".", "").replace(",", ".")
            else:
                clean = clean.replace(",", "")
        elif "," in clean:
            clean = clean.replace(",", ".")
        elif clean.count(".") == 1 and len(clean.split(".")[1]) == 3:
            clean = clean.replace(".", "")
        try:
            val = float(clean)
            if MIN_PREIS <= val <= 3500:
                prices.append(val)
        except ValueError:
            continue
    return min(prices) if prices else None

def is_valid_macbook(text):
    t = text.lower()
    if "macbook" not in t or "air" not in t:
        return False
    if "15" not in t:
        return False
    if any(bad in t for bad in BLACKLIST):
        return False
    return True

async def scan_target(semaphore, context, target, seen_cache):
    async with semaphore:
        page = await context.new_page()
        currency = target["currency"]
        default_limit = MAX_PREIS_CHF if currency == "CHF" else MAX_PREIS_EUR
        max_limit = target.get("max_price", default_limit)
        hits = 0

        try:
            await page.goto(target["url"], wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4000)

            cards = await page.locator("a, article, li, div").filter(
                has_text=re.compile(r"MacBook\s+Air", re.I)
            ).all()

            for card in cards[:75]:
                try:
                    raw_text = await card.inner_text(timeout=350)
                    if len(raw_text) > 380 or len(raw_text) < 20:
                        continue
                    if not is_valid_macbook(raw_text):
                        continue

                    price = parse_price(raw_text)
                    if price and price <= max_limit:
                        lines = [l.strip() for l in raw_text.splitlines() if "macbook" in l.lower()]
                        title = lines[0][:90] if lines else "Apple MacBook Air 15 Zoll"

                        href = await card.get_attribute("href")
                        if not href:
                            sub_link = card.locator("a").first
                            if await sub_link.count() > 0:
                                href = await sub_link.get_attribute("href")

                        full_url = target["url"]
                        if href:
                            if href.startswith("http"):
                                full_url = href
                            elif href.startswith("/"):
                                base = "/".join(target["url"].split("/")[:3])
                                full_url = base + href

                        deal_hash = hashlib.md5(f"{target['name']}_{int(price)}_{title[:35]}".encode()).hexdigest()
                        if deal_hash not in seen_cache:
                            seen_cache.add(deal_hash)
                            send_push(target["name"], title, price, currency, full_url)
                            hits += 1
                except Exception:
                    continue

            print(f"[OK] {target['name']}: {hits} neue Treffer (Limit: {max_limit} {currency})")

        except Exception as e:
            print(f"[ÜBERSPRUNGEN] {target['name']}: {str(e).splitlines()[0]}")
        finally:
            await page.close()

async def main():
    seen_cache = load_cache()
    semaphore = asyncio.Semaphore(PARALLELE_TABS)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="de-CH",
            viewport={"width": 1366, "height": 900}
        )

        await context.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda route: route.abort())

        tasks = [scan_target(semaphore, context, target, seen_cache) for target in TARGETS]
        await asyncio.gather(*tasks)

        await browser.close()
    save_cache(seen_cache)

if __name__ == "__main__":
    asyncio.run(main())
