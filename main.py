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
    "https://tr.investing.com/rss/stock_Market.rss", # Hisse Senedi Piyasası
    "http://feeds.reuters.com/reuters/businessNews", # Reuters Business (Dünyanın en iyisi)
    "https://www.bloomberght.com/rss",               # Bloomberg HT (Yerel Şirketler)
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", # CNBC Teknoloji
    "https://tr.cointelegraph.com/rss"               # Kripto Kurumsal
]

def telegrama_gonder(mesaj, alicilar):
    if not alicilar: return
    print(f"📤 Rapor {len(alicilar)} kişiye gönderiliyor...")
    for kisi_id in alicilar:
        kisi_id = kisi_id.strip()
        if not kisi_id: continue
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": kisi_id, "text": mesaj}
            requests.post(url, json=payload)
            print(f"✅ Gönderildi -> {kisi_id}")
        except Exception as e:
            print(f"❌ Hata ({kisi_id}): {e}")

def modelleri_sirala():
    """Modelleri zeka sırasına göre dizer: Önce PRO, sonra FLASH."""
    print("🔍 Modeller taranıyor ve sıralanıyor...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    
    pro_modeller = []
    flash_modeller = []
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if "error" in data:
            print("⚠️ Model listesi alınamadı, varsayılanlar kullanılacak.")
            return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

        for model in data.get('models', []):
            isim = model['name']
            yetenekler = model.get('supportedGenerationMethods', [])
            
            if 'generateContent' in yetenekler:
                # Modelleri sınıflandır
                if 'pro' in isim:
                    pro_modeller.append(isim)
                elif 'flash' in isim:
                    flash_modeller.append(isim)
        
        # LİSTEYİ BİRLEŞTİR: Önce Zekiler (Pro), Sonra Hızlılar (Flash)
        # 'latest' olanları listenin en başına alalım
        pro_modeller.sort(key=lambda x: 'latest' in x, reverse=True)
        flash_modeller.sort(key=lambda x: 'latest' in x, reverse=True)
        
        sirali_liste = pro_modeller + flash_modeller
        print(f"📋 Kullanılacak Sıralama: {len(sirali_liste)} model bulundu.")
        return sirali_liste

    except:
        return ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]

def haberleri_cek():
    print("📡 Haberler taranıyor...")
    toplanan_metin = ""
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            if not hasattr(feed, 'entries') or not feed.entries: continue
            # Her kaynaktan en yeni 3 haberi al
            for entry in feed.entries[:3]: 
                baslik = entry.get("title", "")
                ozet = entry.get("summary", entry.get("description", ""))
                ozet = ozet.replace("<br>", " ").replace("<p>", "").replace("</p>", "")
                toplanan_metin += f"- {baslik}: {ozet}\n"
        except: continue
    return toplanan_metin

def gemini_analiz_yap(haberler, model_listesi):
    """Listeki modelleri sırayla dener. Biri hata verirse diğerine geçer."""
    
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
    
    Eğer bu detaylar yoksa, o zaman piyasadaki en sert hareketi yapan hisseyi sebebeiyle yaz.
    
    RAPOR FORMATI (Tam olarak bu şablona uy):
    
    KÜRESEL ŞİRKET & PİYASA İSTİHBARATI ({time.strftime("%d.%m.%Y")})
    
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

    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}]}

    # DÖNGÜ BAŞLIYOR: Modelleri sırayla dene
    for model in model_listesi:
        print(f"🧠 Deneniyor: {model} ...")
        
        # Model ismini düzelt (models/ ekle)
        api_model_ismi = model if model.startswith("models/") else f"models/{model}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{api_model_ismi}:generateContent?key={API_KEY}"
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            
            # Eğer BAŞARILI (200) ise sonucu döndür ve döngüyü bitir
            if response.status_code == 200:
                print(f"✅ BAŞARILI! Analizi yapan model: {model}")
                return response.json()['candidates'][0]['content']['parts'][0]['text']
            
            # Eğer KOTA DOLDU (429) ise uyarı ver ve sıradakine geç
            elif response.status_code == 429:
                print(f"⚠️ KOTA DOLDU ({model}). Sıradaki modele geçiliyor...")
                continue # Döngünün başına dön, sonraki modeli al
            
            # Başka bir hataysa (örn: 500)
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

    # 1. Haberleri Çek
    haberler = haberleri_cek()
    if not haberler:
        print("❌ Haber bulunamadı.")
        sys.exit(0)

    # 2. Modelleri Sırala (Zekiden > Hızlıya)
    model_listesi = modelleri_sirala()
    
    # 3. Analiz Yap (Sırayla dener)
    sonuc = gemini_analiz_yap(haberler, model_listesi)
    
    if sonuc:
        telegrama_gonder(sonuc, ALICI_LISTESI)
    else:
        print("❌ HİÇBİR MODEL ÇALIŞMADI. Tüm kotalar dolmuş olabilir.")
        # Opsiyonel: Hata durumunda telegrama bilgi atabilirsin
        # telegrama_gonder("⚠️ Sistem Hatası: Tüm yapay zeka modelleri meşgul veya kota dolu.", ALICI_LISTESI)
