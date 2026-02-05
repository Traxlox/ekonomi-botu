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
    if not alicilar: 
        print("⚠️ Alıcı listesi boş, gönderim yapılmıyor.")
        return

    # --- MESAJ BÖLME ALGORİTMASI ---
    # Telegram limiti 4096 karakterdir. Biz 4000'de güvenli keselim.
    parcalar = []
    while len(mesaj) > 0:
        if len(mesaj) > 4000:
            # En son boşluktan kesmeye çalış ki kelime bölünmesin
            kesme_noktasi = mesaj[:4000].rfind(" ")
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
        
        for i, parca in enumerate(parcalar):
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                # İlk parçada başlık olsun, diğerlerinde devam yazsın
                final_text = parca if len(parcalar) == 1 else f"({i+1}/{len(parcalar)}) {parca}"
                
                payload = {"chat_id": kisi_id, "text": final_text, "disable_web_page_preview": True}
                response = requests.post(url, json=payload)
                
                if response.status_code == 200:
                    print(f"✅ Gönderildi -> {kisi_id} (Parça {i+1})")
                else:
                    print(f"❌ TELEGRAM REDDETTİ ({kisi_id}): {response.text}")
                    
                time.sleep(1) # Spam olmasın diye bekle
            except Exception as e:
                print(f"❌ Bağlantı Hatası ({kisi_id}): {e}")

def modelleri_sirala():
    print("🔍 Modeller taranıyor...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        if "error" in data: 
            print("⚠️ Google API Hatası: Liste alınamadı.")
            return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

        uygun_modeller = []
        for model in data.get('models', []):
            if 'generateContent' in model.get('supportedGenerationMethods', []):
                uygun_modeller.append(model['name'])
        
        def zeka_puani(model_adi):
            puan = 0
            if "pro" in model_adi: puan += 100
            if "flash" in model_adi: puan += 10
            if "1.5" in model_adi: puan += 20
            if "latest" in model_adi: puan += 50
            return puan

        uygun_modeller.sort(key=zeka_puani, reverse=True)
        print(f"📋 En Zeki Model: {uygun_modeller[0]}")
        return uygun_modeller
    except Exception as e:
        print(f"⚠️ Model seçimi hatası: {e}")
        return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

def haberi_detayli_oku(link):
    if not link: return ""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(link, headers=headers, timeout=5) # 5 saniye bekle
        if response.status_code != 200: return ""
        soup = BeautifulSoup(response.content, 'html.parser')
        paragraflar = soup.find_all('p')
        metin = ""
        for p in paragraflar:
            text = p.get_text().strip()
            if len(text) > 50 and "cookie" not in text.lower():
                metin += text + " "
        return metin[:2000] + "..." # 2000 karaktere kadar al
    except: return ""

def haberleri_cek():
    print("📡 Haberler taranıyor...")
    toplanan_metin = ""
    sayac = 0
    
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if not hasattr(feed, 'entries') or not feed.entries: 
                print(f"⚠️ Veri yok: {url}")
                continue
            
            # Her kaynaktan sadece en yeni 2 haberi al (Çok uzatmamak için)
            for entry in feed.entries[:2]: 
                sayac += 1
                baslik = entry.get("title", "")
                link = entry.get("link", "")
                
                print(f"   [{sayac}] İndiriliyor: {baslik[:30]}...")
                detayli_icerik = haberi_detayli_oku(link)
                
                if len(detayli_icerik) < 50:
                    icerik = entry.get("summary", entry.get("description", "Detay yok"))
                else:
                    icerik = detayli_icerik
                
                icerik = icerik.replace("<br>", " ").replace("<p>", "").replace("</p>", "")
                toplanan_metin += f"HABER: {baslik}\nİÇERİK: {icerik}\n---\n"
        except Exception as e:
            print(f"❌ RSS Hatası: {e}")
            continue
            
    print(f"✅ Toplam {sayac} haber toplandı. ({len(toplanan_metin)} karakter)")
    return toplanan_metin

def gemini_analiz_yap(haberler, model_listesi):
    headers = {'Content-Type': 'application/json'}
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
        api_model_ismi = model if model.startswith("models/") else f"models/{model}"
        print(f"🧠 Analiz deneniyor: {model} ...")
        url = f"https://generativelanguage.googleapis.com/v1beta/{api_model_ismi}:generateContent?key={API_KEY}"
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            if response.status_code == 200:
                text_sonuc = response.json()['candidates'][0]['content']['parts'][0]['text']
                imza = f"\n\n🤖 🧠 Beyin: {model.replace('models/', '')}"
                print("✅ Analiz başarıyla tamamlandı.")
                return text_sonuc + imza
            elif response.status_code == 429:
                print(f"⚠️ Kota Doldu ({model}), diğerine geçiliyor...")
            else:
                print(f"❌ Hata ({model}): {response.status_code} - {response.text[:100]}")
        except Exception as e:
            print(f"❌ Bağlantı hatası: {e}")
            continue

    return None

if __name__ == "__main__":
    print("🚀 Başlatılıyor...")
    
    if not API_KEY:
        print("❌ HATA: GOOGLE_API_KEY eksik.")
        sys.exit(1)
    if not ALICI_LISTESI:
        print("❌ HATA: Alıcı listesi eksik.")
        sys.exit(1)

    haberler = haberleri_cek()
    if not haberler or len(haberler) < 10:
        print("❌ HATA: Hiç haber toplanamadı veya çok kısa.")
        sys.exit(0)

    model_listesi = modelleri_sirala()
    sonuc = gemini_analiz_yap(haberler, model_listesi)
    
    if sonuc:
        telegrama_gonder(sonuc, ALICI_LISTESI)
    else:
        print("❌ KRİTİK: Analiz oluşturulamadı.")
