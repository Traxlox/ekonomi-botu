import sys
import json
import time
import os
import requests
import feedparser

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
    print(f"📤 Rapor {len(alicilar)} kişiye gönderiliyor...")
    for kisi_id in alicilar:
        kisi_id = kisi_id.strip()
        if not kisi_id: continue
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": kisi_id, "text": mesaj, "disable_web_page_preview": True}
            requests.post(url, json=payload)
            print(f"✅ Gönderildi -> {kisi_id}")
        except Exception as e:
            print(f"❌ Hata ({kisi_id}): {e}")

def modelleri_sirala():
    """Zeka sırasına göre modelleri dizer."""
    print("🔍 Modeller taranıyor...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    pro_modeller = []
    flash_modeller = []
    try:
        response = requests.get(url)
        data = response.json()
        if "error" in data: return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

        for model in data.get('models', []):
            isim = model['name']
            if 'generateContent' in model.get('supportedGenerationMethods', []):
                if 'pro' in isim: pro_modeller.append(isim)
                elif 'flash' in isim: flash_modeller.append(isim)
        
        pro_modeller.sort(key=lambda x: 'latest' in x, reverse=True)
        return pro_modeller + flash_modeller
    except: return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

def haberleri_cek():
    print("📡 Haberler taranıyor...")
    toplanan_metin = ""
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if not hasattr(feed, 'entries') or not feed.entries: continue
            # En yeni 4 haberi al
            for entry in feed.entries[:4]: 
                baslik = entry.get("title", "")
                ozet = entry.get("summary", entry.get("description", ""))
                # Linki de veriye ekleyelim ki AI gerekirse baksın (Gelecekte scrape için)
                link = entry.get("link", "")
                
                ozet = ozet.replace("<br>", " ").replace("<p>", "").replace("</p>", "")
                toplanan_metin += f"HABER: {baslik}\nÖZET: {ozet}\nKAYNAK: {link}\n---\n"
        except: continue
    return toplanan_metin

def gemini_analiz_yap(haberler, model_listesi):
    headers = {'Content-Type': 'application/json'}
    
    # Prompt'u biraz daha zorlayalım
    prompt = f"""
    Sen Üst Düzey Piyasa İstihbaratçısısın.
    
    ELİNDEKİ HAM VERİ:
    {haberler}
    
    GÖREV:
    Bu verilerden, sanki şirketin yönetim kuruluna sunum yapıyormuş gibi DERİNLEMESİNE detay çıkar.
    
    KURALLAR:
    1. Yüzeysel olma. "Yükseldi" deme, metinde varsa NEDEN yükseldiğini bul.
    2. Eğer metinde detay yoksa, "Detaylar raporda belirtilmemiş" diye dürüstçe not düş.
    3. CEO isimleri, anlaşma tutarları (Milyar $), yüzdelik değişimleri mutlaka yaz.
    4. İngilizce haberleri Türkçeye çevir.
    
    FORMAT:
    KÜRESEL İSTİHBARAT RAPORU ({time.strftime("%d.%m.%Y")})
    
    📢 Şirket & CEO Hareketleri
    - [Şirket]: [Olay ve Detay]
    
    ⚖️ Anlaşmalar & Davalar
    - [Detay]
    
    📉📈 Piyasa Tepkileri (Sebepleriyle)
    - [Hisse]: [Hareket ve Sebebi]
    
    ⚠️ Kritik Risk Notları
    - [Risk]
    """

    data = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in model_listesi:
        print(f"🧠 Deneniyor: {model} ...")
        api_model_ismi = model if model.startswith("models/") else f"models/{model}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{api_model_ismi}:generateContent?key={API_KEY}"
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            if response.status_code == 200:
                metin = response.json()['candidates'][0]['content']['parts'][0]['text']
                
                # --- İMZA EKLEME KISMI ---
                # Model ismini temizle (models/ başlığını at)
                kisa_isim = model.replace("models/", "")
                imza = f"\n\n🤖 🧠 Analiz Eden Model: {kisa_isim}"
                return metin + imza
                
            elif response.status_code == 429: continue
            else: continue
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
