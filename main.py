import sys
import json
import time
import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

# --- AYARLAR ---
API_KEY = os.environ.get("GOOGLE_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

ALICI_LISTESI = ["1628808952", "1126701632"]


# --- KAYNAKLAR ---
RSS_URLS = [
    "https://tr.investing.com/rss/stock_Market.rss", 
    "http://feeds.reuters.com/reuters/businessNews", 
    "https://www.bloomberght.com/rss",                
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", 
    "https://tr.cointelegraph.com/rss"                
]

def telegrama_gonder(mesaj, alicilar):
    if not alicilar: return

    parcalar = []
    while len(mesaj) > 0:
        if len(mesaj) > 4000:
            kesme_noktasi = mesaj[:4000].rfind("\n")
            if kesme_noktasi == -1: kesme_noktasi = 4000
            parcalar.append(mesaj[:kesme_noktasi])
            mesaj = mesaj[kesme_noktasi:]
        else:
            parcalar.append(mesaj)
            mesaj = ""

    print(f"📤 Rapor {len(parcalar)} parça halinde gönderiliyor...")

    for kisi_id in alicilar:
        kisi_id = kisi_id.strip()
        if not kisi_id: continue
        
        for parca in parcalar:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                payload = {"chat_id": kisi_id, "text": parca, "disable_web_page_preview": True}
                requests.post(url, json=payload)
                time.sleep(1) 
            except: pass

def modelleri_sirala():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        if "error" in data: return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

        uygun_modeller = []
        for model in data.get('models', []):
            if 'generateContent' in model.get('supportedGenerationMethods', []):
                uygun_modeller.append(model['name'])
        
        def zeka_puani(model_adi):
            puan = 0
            if "pro" in model_adi: puan += 100
            if "latest" in model_adi: puan += 50
            if "flash" in model_adi: puan += 10
            return puan

        uygun_modeller.sort(key=zeka_puani, reverse=True)
        print(f"📋 Seçilen Model: {uygun_modeller[0]}")
        return uygun_modeller
    except: return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

def haberi_detayli_oku(link):
    if not link: return ""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        # Investing gibi siteler bazen yönlendirme yapar, allow_redirects=True önemli
        response = requests.get(link, headers=headers, timeout=5, allow_redirects=True)
        if response.status_code != 200: return ""
        soup = BeautifulSoup(response.content, 'html.parser')
        
        metin = " ".join([p.get_text().strip() for p in soup.find_all('p')])
        return metin[:1500]
    except: return ""

def haber_taze_mi(entry):
    """Haberin son 24 saat içinde yayınlanıp yayınlanmadığını kontrol eder."""
    try:
        if hasattr(entry, 'published_parsed'):
            haber_zamani = datetime.fromtimestamp(time.mktime(entry.published_parsed))
        elif hasattr(entry, 'updated_parsed'):
            haber_zamani = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
        else:
            # Tarih yoksa, güvenip almıyoruz (Eski olabilir)
            return False
        
        su_an = datetime.now()
        fark = su_an - haber_zamani
        
        # 24 saatten (1 gün) eskiyse alma
        if fark.days >= 1:
            return False
        return True
    except:
        return False # Hata varsa eski varsay

def haberleri_cek():
    print("📡 Haberler taranıyor (Sadece son 24 saat)...")
    toplanan_metin = ""
    sayac = 0
    
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if not hasattr(feed, 'entries') or not feed.entries: continue
            
            # Her kaynaktan en yeni 10 haberi kontrol et (Taze olanları alacağız)
            for entry in feed.entries[:10]: 
                # --- FİLTRE: BAYAT HABERLERİ AT ---
                if not haber_taze_mi(entry):
                    continue

                # Eğer limit dolduysa bu kaynaktan çık (Her kaynaktan max 2 taze haber)
                if sayac >= 2: break 

                baslik = entry.get("title", "")
                link = entry.get("link", "")
                
                print(f"   Taze Haber Bulundu: {baslik[:30]}...")
                detay = haberi_detayli_oku(link)
                
                icerik = detay if len(detay) > 50 else entry.get("summary", "")
                icerik = icerik.replace("<br>", " ").replace("<p>", "")
                
                toplanan_metin += f"HABER TARİHİ: BUGÜN/DÜN\nHABER: {baslik}\nİÇERİK: {icerik}\n---\n"
                sayac += 1
            sayac = 0 # Diğer kaynak için sayacı sıfırla
        except: continue
            
    return toplanan_metin

def gemini_analiz_yap(haberler, model_listesi):
    headers = {'Content-Type': 'application/json'}
    bugun = time.strftime("%d.%m.%Y")
    
    # --- GERÇEKLİK PROMPT ---
    prompt = f"""
    Sen Gerçek Zamanlı Piyasa Analistisin.
    BUGÜNÜN TARİHİ: {bugun}. (Bu tarihten sapma, gelecekten bahsetme).
    
    ELİNDEKİ HAM VERİ:
    {haberler}
    
    GÖREVİN:
    Sadece elindeki metinlerde geçen GERÇEK verileri kullan. Asla "2026", "Altın 5000$" gibi hayali senaryolar uretme. Metinde yazmıyorsa yazma.
    
    İSTENEN FORMAT (Kısa, Net, Maddeler Halinde):
    
    SIRKET HABERLERI (Bugün)
    - [ŞİRKET]: [Olay] -> [Sebep/Sonuç]
    
    YASAL VE ANLASMALAR
    - [ŞİRKET/ULKE]: [Detay]
    
    PIYASA HAREKETLERI
    - [VARLIK]: [Yön] -> [Sebep]
    
    RISKLER
    - [Risk Başlığı]: [Kısa Açıklama]
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in model_listesi:
        api_model_ismi = model if model.startswith("models/") else f"models/{model}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{api_model_ismi}:generateContent?key={API_KEY}"
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            if response.status_code == 200:
                print(f"✅ Analiz Başarılı ({model})")
                return response.json()['candidates'][0]['content']['parts'][0]['text']
            elif response.status_code == 429:
                print(f"⚠️ Kota Doldu ({model}), diğerine geçiliyor...")
                continue
        except: continue

    return None

if __name__ == "__main__":
    if not API_KEY or not ALICI_LISTESI:
        print("❌ Ayarlar eksik.")
        sys.exit(1)

    haberler = haberleri_cek()
    
    # Eğer hiç taze haber yoksa boş mesaj atmasın
    if not haberler: 
        print("❌ Hiç taze haber bulunamadı (Piyasalar sakin veya RSS hatası).")
        sys.exit(0)

    model_listesi = modelleri_sirala()
    sonuc = gemini_analiz_yap(haberler, model_listesi)
    
    if sonuc: telegrama_gonder(sonuc, ALICI_LISTESI)


