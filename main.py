import sys
import json
import time
import os
import requests
import feedparser
from bs4 import BeautifulSoup # Haber içeriğini okumak için gerekli

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
    print("🔍 Modeller taranıyor...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        if "error" in data: return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

        uygun_modeller = []
        for model in data.get('models', []):
            if 'generateContent' in model.get('supportedGenerationMethods', []):
                uygun_modeller.append(model['name'])
        
        # Zeka Puanı: Pro > 1.5 > Flash
        def zeka_puani(model_adi):
            puan = 0
            if "pro" in model_adi: puan += 100
            if "flash" in model_adi: puan += 10 # Flash'ı sona atalım ki detaylı analiz yapsın
            if "1.5" in model_adi: puan += 20
            if "latest" in model_adi: puan += 50 # Latest versiyonlar genelde daha iyidir
            return puan

        uygun_modeller.sort(key=zeka_puani, reverse=True)
        print(f"📋 En Zeki Model Seçildi: {uygun_modeller[0]}")
        return uygun_modeller
    except: return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

def haberi_detayli_oku(link):
    """Linke gider, siteye girer ve metni çeker."""
    if not link: return ""
    
    # Kendimizi tarayıcı gibi tanıtıyoruz (Yoksa site bizi engeller)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        # Siteye git (3 saniye bekle, açılmazsa vazgeç)
        response = requests.get(link, headers=headers, timeout=3)
        if response.status_code != 200: return ""
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Paragrafları bul (<p> etiketleri)
        paragraflar = soup.find_all('p')
        metin = ""
        for p in paragraflar:
            text = p.get_text().strip()
            # Çok kısa veya reklam içeren satırları atla
            if len(text) > 50 and "cookie" not in text.lower():
                metin += text + " "
                
        # Çok uzunsa kes (Yapay zekayı boğmayalım)
        return metin[:1500] + "..." # İlk 1500 karakter yeterli
    except:
        return ""

def haberleri_cek():
    print("📡 Haberler taranıyor ve İÇERİKLERİ OKUNUYOR (Bu biraz sürebilir)...")
    toplanan_metin = ""
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if not hasattr(feed, 'entries') or not feed.entries: continue
            
            # Her kaynaktan sadece en yeni 2 haberi al (Çünkü içerik okumak yavaştır)
            for entry in feed.entries[:2]: 
                baslik = entry.get("title", "")
                link = entry.get("link", "")
                
                # --- KRİTİK NOKTA: SİTEYE GİT VE OKU ---
                print(f"   Downloading: {baslik[:30]}...")
                detayli_icerik = haberi_detayli_oku(link)
                
                # Eğer site içeriği vermediyse özeti kullan
                if len(detayli_icerik) < 100:
                    icerik = entry.get("summary", entry.get("description", "Detay yok"))
                else:
                    icerik = detayli_icerik
                
                icerik = icerik.replace("<br>", " ").replace("<p>", "").replace("</p>", "")
                toplanan_metin += f"HABER: {baslik}\nİÇERİK: {icerik}\n---\n"
        except: continue
    return toplanan_metin

def gemini_analiz_yap(haberler, model_listesi):
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    Sen Dünyanın En İyi Araştırmacı Gazetecisisin.
    
    ELİNDEKİ VERİ (Bu veriler haber sitelerinden senin için özel olarak kazındı):
    {haberler}
    
    GÖREVİN:
    Bu metinlerin içindeki en ufak detayı bile kaçırmadan, isim, rakam ve tarih vererek raporla.
    
    RAPOR FORMATI:
    🌍 KÜRESEL DERİN İSTİHBARAT ({time.strftime("%d.%m.%Y")})
    
    1️⃣ Şirketlerin İç Dünyası (CEO, Birleşme, Kararlar)
    - [Şirket]: [Detaylı Olay. Kim ne dedi? Kaç para?]
    
    2️⃣ Yasal & Politik Hamleler
    - [Detay]
    
    3️⃣ Piyasa Hareketleri ve Gerçek Sebepleri
    - [Hisse]: [Neden?]
    
    4️⃣ Riskler (Somut Verilerle)
    - [Risk]

    ÖNEMLİ: 
    - Asla yüzeysel olma. "Yükseldi" deme, "Bilanço beklentisiyle %5 yükseldi" de.
    - Metinde detay yoksa dürüstçe "Kaynak metinde detay bulunamadı" de, uydurma.
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in model_listesi:
        # API ismini düzelt
        api_model_ismi = model if model.startswith("models/") else f"models/{model}"
        print(f"🧠 Analiz Başlıyor: {model} ...")
        url = f"https://generativelanguage.googleapis.com/v1beta/{api_model_ismi}:generateContent?key={API_KEY}"
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            if response.status_code == 200:
                text_sonuc = response.json()['candidates'][0]['content']['parts'][0]['text']
                imza = f"\n\n🤖 🧠 Beyin: {model.replace('models/', '')}"
                print(f"✅ Analiz Bitti!")
                return text_sonuc + imza
            elif response.status_code == 429:
                print(f"⚠️ Kota Doldu ({model}), diğerine geçiliyor...")
                continue
            else:
                print(f"❌ Hata ({model}): {response.status_code}")
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
