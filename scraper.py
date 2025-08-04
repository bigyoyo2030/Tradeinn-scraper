import csv
import json
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor, as_completed

# === CONFIG ===
STORES = ['runnerinn', 'trekkinn', 'dressinn']
REQUIRED_IN_URL = ['shoes', 'refurbished']
THREADS = 5
MAX_SITEMAP_PAGES = 10  # per store

# === SELENIUM DRIVER ===
def init_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)

# === FETCH PAGINATED SITEMAP ===
def get_all_sitemap_urls(store, max_pages=MAX_SITEMAP_PAGES):
    urls = []
    for i in range(1, max_pages + 1):
        sitemap_url = f"https://www.tradeinn.com/{store}/sitemaps/sitemap_productos_{i}_eng_{store}.xml"
        try:
            resp = requests.get(sitemap_url, timeout=10)
            if resp.status_code != 200:
                break
            soup = BeautifulSoup(resp.content, "lxml-xml")
            page_urls = [
                loc.text for loc in soup.find_all("loc")
                if all(kw in loc.text.lower() for kw in REQUIRED_IN_URL)
            ]
            print(f"  ✔️ {store} sitemap page {i}: {len(page_urls)} matching URLs")
            urls.extend([(store, url) for url in page_urls])
        except Exception as e:
            print(f"  ❌ Failed loading sitemap {i} for {store}: {e}")
            break
    return urls

# === SCRAPE PRODUCT PAGE ===
def process_url(store, url):
    driver = init_driver()
    try:
        driver.get(url)
        time.sleep(0.1)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        title = soup.title.text.strip() if soup.title else ""

        sizes = []
        sel = soup.find('select', {'id': 'talla2'})
        if sel:
            for opt in sel.find_all('option'):
                t = opt.text
                if '44' in t or '45' in t:
                    sizes.append(t.strip())

        print(f"✔️ {store.upper()} | {url}")
        return {
            "store": store,
            "url": url,
            "title": title,
            "sizes": "; ".join(sizes) if sizes else "N/A",
            "has_size": bool(sizes)
        }

    except Exception as e:
        print(f"❌ Error on {store.upper()} | {url} — {e}")
        return None
    finally:
        driver.quit()

# === MAIN ===
def main():
    all_urls = []
    for store in STORES:
        urls = get_all_sitemap_urls(store, max_pages=MAX_SITEMAP_PAGES)
        all_urls.extend(urls)

    print(f"\n🔎 Total URLs to process: {len(all_urls)}\n")

    found = []
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = [executor.submit(process_url, store, url) for store, url in all_urls]
        for future in as_completed(futures):
            result = future.result()
            if result:
                found.append(result)

    print(f"\n✅ Collected {len(found)} valid refurbished shoes (some with sizes, some without)")

    # Print only those with sizes 44/45
    found_with_sizes = [f for f in found if f["has_size"]]
    print(f"\n🔍 Found size 44/45 for {len(found_with_sizes)} products:")
    for f in found_with_sizes:
        print(f["store"].upper(), f["url"], "→", f["sizes"])

    # Save full results
    with open("refurbished_shoes_all_stores.csv", "w", newline='', encoding='utf-8') as fcsv:
        writer = csv.DictWriter(fcsv, fieldnames=["store", "url", "title", "sizes"])
        writer.writeheader()
        for f in found:
            writer.writerow({k: f[k] for k in ["store", "url", "title", "sizes"]})

    # Summary per store
    print("\n📊 Summary per store:")
    for store in STORES:
        total = len([f for f in found if f['store'] == store])
        sized = len([f for f in found if f['store'] == store and f['has_size']])
        print(f" - {store.upper()}: {total} total, {sized} with 44/45")

if __name__ == "__main__":
    main()
