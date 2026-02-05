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

# --- ŞİRKET VE HİSSE ODAKLI KAYNAKLAR ---
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
            # Link önizlemesini kapattım ki rapor daha temiz dursun
            payload = {"chat_id": kisi_id, "text": mesaj, "disable_web_page_preview": True}
            requests.post(url, json=payload)
            print(f"✅ Gönderildi -> {kisi_id}")
        except Exception as e:
            print(f"❌ Hata ({kisi_id}): {e}")

def modelleri_sirala():
    """Google'daki tüm modelleri çeker ve en akıllıdan (Pro) en hızlıya (Flash) doğru sıralar."""
    print("🔍 Google'ın beyin takımı taranıyor...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if "error" in data:
            # Liste alamazsak manuel bir liste döndür (Güvenlik ağı)
            return ["models/gemini-1.5-pro", "models/gemini-1.5-flash", "models/gemini-pro"]

        uygun_modeller = []
        for model in data.get('models', []):
            if 'generateContent' in model.get('supportedGenerationMethods', []):
                uygun_modeller.append(model['name'])
        
        # --- ZEKA SIRALAMASI ALGORİTMASI ---
        # Her modele bir puan veriyoruz. Puanı yüksek olan listenin başına geçer.
        def zeka_puani(model_adi):
            puan = 0
            if "pro" in model_adi: puan += 100       # Pro modeller en zeki (Öncelik 1)
            if "flash" in model_adi: puan += 50      # Flash modeller hızlı (Öncelik 2)
            if "1.5" in model_adi: puan += 20        # Yeni sürüm daha iyidir
            if "latest" in model_adi: puan += 10     # En güncel sürüm daha iyidir
            if "002" in model_adi: puan += 5         # Versiyon 2
            return puan

        # Listeyi puana göre (büyükten küçüğe) sırala
        uygun_modeller.sort(key=zeka_puani, reverse=True)
        
        print(f"📋 Bulunan Modeller (Sıralı):")
        for m in uygun_modeller[:3]: print(f"   -> {m}") # İlk 3 tanesini ekrana bas
        
        return uygun_modeller

    except:
        return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

def haberleri_cek():
    print("📡 Haberler taranıyor...")
    toplanan_metin = ""
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if not hasattr(feed, 'entries') or not feed.entries: continue
            
            # Her kaynaktan en yeni 4 haberi al
            for entry in feed.entries[:4]: 
                baslik = entry.get("title", "")
                ozet = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "") # Linki de alalım
                
                ozet = ozet.replace("<br>", " ").replace("<p>", "").replace("</p>", "")
                toplanan_metin += f"HABER: {baslik}\nÖZET: {ozet}\nLINK: {link}\n---\n"
        except: continue
    return toplanan_metin

def gemini_analiz_yap(haberler, model_listesi):
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    Sen 'Kurumsal İstihbarat Uzmanısın'. Görevin genel piyasa yorumu yapmak DEĞİL, haberlerin içindeki SOMUT ŞİRKET HAREKETLERİNİ avlamaktır.
    
    ELİNDEKİ HAM VERİ:
    {haberler}
    
    GÖREVİN:
    Bu haberlerin içinden şu detayları bul ve raporla:
    1. CEO/Yönetici Değişiklikleri (Kim geldi, kim gitti?)
    2. Birleşme & Satın Alma (M&A) (Hangi şirket kimi alıyor?)
    3. Yeni Anlaşmalar/Kontratlar (Kim kiminle iş yapıyor?)
    4. Yasal Süreçler/Davalar (Hangi şirkete dava açıldı?)
    
    Eğer bu detaylar yoksa, piyasadaki en sert hareketi yapan hisseyi sebebiyle yaz.
    
    RAPOR FORMATI (Tam olarak bu şablona uy):
    
    🌍 KÜRESEL ŞİRKET & PİYASA İSTİHBARATI ({time.strftime("%d.%m.%Y")})
    
    📢 Şirket Haberleri & Anlaşmalar
    - [Şirket Adı]: [Olayın özeti - Örn: Apple, yeni CEO olarak X'i atadı.]
    
    ⚖️ Yasal & Regülasyon
    - [Detaylı, somut bilgi]
    
    📉📈 Öne Çıkan Hisse Hareketleri
    - [Şirket]: [Neden yükseldi/düştü?]
    
    ⚠️ Kritik Riskler
    - [Sadece somut riskler]

    KURALLAR:
    - ASLA "Piyasalar dalgalı" gibi boş laflar etme. İsim ver, rakam ver.
    - İngilizce haberleri kusursuz Türkçeye çevir.
    - Emojileri sadece başlıkta kullan.
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}

    # --- AKILLI DÖNGÜ ---
    # Listeyi sırayla dene. Biri hata verirse diğerine geç.
    for model in model_listesi:
        # Model ismini API formatına uygun hale getir
        api_model_ismi = model if model.startswith("models/") else f"models/{model}"
        
        print(f"🧠 Deneniyor: {model} ...")
        url = f"https://generativelanguage.googleapis.com/v1beta/{api_model_ismi}:generateContent?key={API_KEY}"
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            
            # 1. BAŞARILI DURUM
            if response.status_code == 200:
                text_sonuc = response.json()['candidates'][0]['content']['parts'][0]['text']
                
                # Raporun altına hangi modelin çalıştığını imza olarak ekle
                imza = f"\n\n🤖 🧠 Analiz Eden Model: {model.replace('models/', '')}"
                print(f"✅ BAŞARILI! ({model})")
                return text_sonuc + imza
            
            # 2. KOTA DOLDU (429) -> Sıradakine geç
            elif response.status_code == 429:
                print(f"⚠️ KOTA DOLDU ({model}). Sıradaki modele geçiliyor...")
                continue 
            
            # 3. DİĞER HATALAR -> Sıradakine geç
            else:
                print(f"❌ Model Hatası ({model}): {response.status_code}. Sıradakine geçiliyor...")
                continue

        except Exception as e:
            print(f"❌ Bağlantı hatası: {e}. Sıradakine geçiliyor...")
            continue

    return None # Hiçbir model çalışmazsa

if __name__ == "__main__":
    if not API_KEY or not ALICI_LISTESI:
        print("❌ Ayarlar eksik (GitHub Secrets kontrol et).")
        sys.exit(1)

    haberler = haberleri_cek()
    if not haberler:
        print("❌ Haber bulunamadı.")
        sys.exit(0)

    # 1. Google'dan tüm modelleri al ve sırala
    model_listesi = modelleri_sirala()
    
    # 2. Sırayla dene (Failover sistemi)
    sonuc = gemini_analiz_yap(haberler, model_listesi)
    
    if sonuc:
        telegrama_gonder(sonuc, ALICI_LISTESI)
    else:
        print("❌ KRİTİK HATA: Hiçbir model çalışmadı (Tüm kotalar dolu olabilir).")
