import sys
import json
import time
import os
import requests
import feedparser
from bs4 import BeautifulSoup

# --- AYARLAR ---
API_KEY = os.environ.get("GOOGLE_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ALICILAR_STR = os.environ.get("TELEGRAM_ALICILAR") 
ALICI_LISTESI = ALICILAR_STR.split(",") if ALICILAR_STR else []

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

    # Mesaj çok uzunsa bölme işlemi (4000 karakter sınırı)
    parcalar = []
    while len(mesaj) > 0:
        if len(mesaj) > 4000:
            kesme_noktasi = mesaj[:4000].rfind("\n") # Satır sonundan böl
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
                # disable_web_page_preview=True: Link önizlemesi yapıp ekranı kirletmesin
                payload = {"chat_id": kisi_id, "text": parca, "disable_web_page_preview": True}
                requests.post(url, json=payload)
                time.sleep(1) 
            except: pass

def modelleri_sirala():
    # Google'dan modelleri çekip en zekisini başa koyar
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        if "error" in data: return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

        uygun_modeller = []
        for model in data.get('models', []):
            if 'generateContent' in model.get('supportedGenerationMethods', []):
                uygun_modeller.append(model['name'])
        
        # Zeka Puanlaması: Pro > Latest > Flash
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
    # Linke gidip içeriği okur (Scraping)
    if not link: return ""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(link, headers=headers, timeout=4)
        if response.status_code != 200: return ""
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Sadece paragrafları al
        metin = " ".join([p.get_text().strip() for p in soup.find_all('p')])
        return metin[:1500] # Çok uzun verip boğmayalım, ilk 1500 karakter yeter
    except: return ""

def haberleri_cek():
    print("📡 Haberler taranıyor...")
    toplanan_metin = ""
    
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if not hasattr(feed, 'entries') or not feed.entries: continue
            
            # Her kaynaktan en yeni 2 haberi al
            for entry in feed.entries[:2]: 
                baslik = entry.get("title", "")
                link = entry.get("link", "")
                
                print(f"   Okunuyor: {baslik[:30]}...")
                detay = haberi_detayli_oku(link)
                
                # Eğer site boş döndüyse özeti kullan
                icerik = detay if len(detay) > 50 else entry.get("summary", "")
                icerik = icerik.replace("<br>", " ").replace("<p>", "")
                
                toplanan_metin += f"HABER: {baslik}\nİÇERİK: {icerik}\n---\n"
        except: continue
            
    return toplanan_metin

def gemini_analiz_yap(haberler, model_listesi):
    headers = {'Content-Type': 'application/json'}
    
    # --- YENİ "SNIPER" PROMPT ---
    prompt = f"""
    Sen "Özet Odaklı Piyasa İstihbaratçısısın". Uzun yazı YASAK.
    
    ELİNDEKİ HAM VERİ:
    {haberler}
    
    GÖREVİN:
    Haberleri tara ve sadece SOMUT ŞİRKET/VARLIK hareketlerini tek cümlelik maddelerle yaz.
    
    KURALLAR:
    1. Giriş/Çıkış cümlesi, tarih, imza, "Bu rapor..." gibi şeyler ASLA yazma.
    2. Kalın yazı (** **) kullanma. Sadece düz metin.
    3. Her maddeyi "-" ile başlat.
    4. Her madde en fazla 20 kelime olsun. Kısa, öz, net.
    5. CEO ismi, Para miktarı veya Yüzdelik değişim varsa yaz, yoksa uzatma.
    
    İSTENEN FORMAT (Aynen bunu uygula):
    
    SIRKET HABERLERI
    - [ŞİRKET ADI]: [Ne oldu?] -> [Sonuç/Sebep]
    - [ŞİRKET ADI]: [Ne oldu?] -> [Sonuç/Sebep]
    
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
                # İmza eklemiyoruz, direkt metni döndürüyoruz
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
    if not haberler: sys.exit(0)

    model_listesi = modelleri_sirala()
    sonuc = gemini_analiz_yap(haberler, model_listesi)
    
    if sonuc: telegrama_gonder(sonuc, ALICI_LISTESI)
