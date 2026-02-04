import sys
import json
import time
import os
import requests
import feedparser

# GitHub Actions'da .env dosyası olmadığı için load_dotenv'e gerek yok.
# Şifreleri direkt sistemin hafızasından (Environment Variables) okuyacak.

# --- AYARLAR ---
API_KEY = os.environ.get("GOOGLE_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# ID'leri virgülle ayrılmış tek bir metin olarak alacağız: "112233,445566"
ALICILAR_STR = os.environ.get("TELEGRAM_ALICILAR") 
ALICI_LISTESI = ALICILAR_STR.split(",") if ALICILAR_STR else []

# --- KAYNAKLAR ---
RSS_URLS = [
    "https://tr.investing.com/rss/news_1.rss",
    "https://tr.investing.com/rss/news_25.rss",
    "https://tr.investing.com/rss/news_301.rss",
    "https://www.bloomberght.com/rss",
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
]

def telegrama_gonder(mesaj, alicilar):
    if not alicilar: 
        print("⚠️ Alıcı listesi boş.")
        return
    print(f"📤 Rapor {len(alicilar)} kişiye gönderiliyor...")
    for kisi_id in alicilar:
        kisi_id = kisi_id.strip() # Boşlukları temizle
        if not kisi_id: continue
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": kisi_id, "text": mesaj}
        try:
            requests.post(url, json=payload)
            print(f"✅ Gönderildi -> {kisi_id}")
        except Exception as e:
            print(f"❌ Hata ({kisi_id}): {e}")

def calisan_modeli_bul():
    print("🔍 Google model deposu taranıyor...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        if "error" in data: return None
        
        # Öncelik: Flash (Hızlı) -> Pro (Zeki)
        for model in data.get('models', []):
            if 'flash' in model['name'] and 'generateContent' in model.get('supportedGenerationMethods', []):
                return model['name']
        return "models/gemini-1.5-flash"
    except: return "models/gemini-1.5-flash"

def haberleri_cek():
    print("📡 Haberler taranıyor...")
    toplanan_metin = ""
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if not hasattr(feed, 'entries') or not feed.entries: continue
            for entry in feed.entries[:2]: 
                baslik = entry.get("title", "")
                ozet = entry.get("summary", entry.get("description", ""))
                ozet = ozet.replace("<br>", " ").replace("<p>", "").replace("</p>", "")
                toplanan_metin += f"- {baslik}: {ozet}\n"
        except: continue
    return toplanan_metin

def geminiye_sor(metin, model_ismi):
    if not model_ismi.startswith("models/"): model_ismi = f"models/{model_ismi}"
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_ismi}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    Sen kıdemli bir analistsin. Haberleri yorumla.
    HABERLER: {metin}
    KURALLAR: İsim kullanma. Somut veriler ver. Emojisiz, kurumsal dil.
    
    ŞABLON:
    KÜRESEL PİYASA BÜLTENİ ({time.strftime("%d.%m.%Y")})
    
    Piyasa Görünümü
    - Analiz
    Riskler
    - Riskler
    Fırsatlar
    - Fırsatlar
    """
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, headers=headers, data=json.dumps(data))
        if r.status_code == 200: return r.json()['candidates'][0]['content']['parts'][0]['text']
    except: pass
    return None

if __name__ == "__main__":
    if not API_KEY or not ALICI_LISTESI:
        print("❌ Ayarlar eksik (GitHub Secrets kontrol et).")
        sys.exit(1)

    model = calisan_modeli_bul()
    haberler = haberleri_cek()
    if model and haberler:
        print("🧠 Analiz yapılıyor...")
        sonuc = geminiye_sor(haberler, model)
        if sonuc: telegrama_gonder(sonuc, ALICI_LISTESI)