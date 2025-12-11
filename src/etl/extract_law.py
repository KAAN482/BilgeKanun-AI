import time
import json
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# --- AYARLAR ---
BASE_URL = "https://www.mevzuat.gov.tr/"
OUTPUT_DIR = os.path.join("data", "raw")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def setup_driver():
    """Chrome sürücüsünü başlatır."""
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def clean_text(text):
    """Metindeki fazla boşlukları temizler."""
    return re.sub(r'\s+', ' ', text).strip()

def parse_law_detail(driver, law_url, law_title):
    """Kanun detay sayfasına gider ve tüm metni alır, sonra ayrıştırır."""
    try:
        print(f"   📄 Sayfa yükleniyor...")
        driver.get(law_url)

        # Sayfanın yüklenmesini bekle - body elementi her zaman var
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        # JavaScript render için bekle
        time.sleep(3)

        # IFRAME'İ BUL VE GEÇİŞ YAP
        try:
            print(f"   🔄 Iframe bekleniyor...")
            iframe = wait.until(EC.presence_of_element_located((By.ID, "mevzuatDetayIframe")))
            print(f"   ✓ Iframe bulundu, geçiş yapılıyor...")
            driver.switch_to.frame(iframe)
            time.sleep(2)  # Iframe içeriğinin yüklenmesi için bekle
            print(f"   ✓ Iframe içine geçildi")
        except Exception as e:
            print(f"   ⚠️ Iframe bulunamadı: {e}")

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Farklı içerik div'lerini dene (öncelik sırasına göre)
        content_div = None
        div_classes_to_try = [
            "WordSection1",
            "MevzuatMetin",
            "mevzuat-content",
            "kanun-metni"
        ]

        for cls in div_classes_to_try:
            content_div = soup.find("div", class_=cls)
            if content_div:
                print(f"   ✓ İçerik bulundu: {cls}")
                break

        # Eğer hala bulunamadıysa, id="contentPane" veya içinde çok paragraf olan div'i bul
        if not content_div:
            print(f"⚠️  Class ile bulunamadı, alternatif yöntemler deneniyor...")

            # ID ile dene
            content_div = soup.find("div", id="contentPane")
            if content_div:
                print(f"   ✓ contentPane bulundu")

            # Hala yoksa, en çok <p> içeren div'i al
            if not content_div:
                all_divs = soup.find_all("div")
                max_p_count = 0
                for div in all_divs:
                    p_count = len(div.find_all("p"))
                    if p_count > max_p_count:
                        max_p_count = p_count
                        content_div = div

                if content_div and max_p_count > 0:
                    print(f"   ✓ En çok paragraf içeren div bulundu ({max_p_count} paragraf)")

        if not content_div:
            print(f"⚠️  Uyarı: Hiçbir içerik div'i bulunamadı!")
            # HTML'i dosyaya kaydet (debug için)
            debug_file = os.path.join(OUTPUT_DIR, "debug_page.html")
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"   Debug için HTML kaydedildi: {debug_file}")
            return "", "", []

        print(f"   ✓ İçerik bulundu: {content_div.name}")

        # Tüm p etiketlerini al
        all_paragraphs = content_div.find_all("p")
        print(f"   ✓ {len(all_paragraphs)} paragraf bulundu")

        # Tüm metni satır satır topla
        lines = []
        for p in all_paragraphs:
            text = clean_text(p.get_text())
            if text:
                lines.append(text)

        if not lines:
            print(f"⚠️  Uyarı: Hiç metin bulunamadı!")
            return "", "", []

        print(f"   ✓ {len(lines)} satır metin çekildi")
        print(f"   İlk satır: {lines[0][:80]}...")

        # 1. BAŞLIK: "Kanun Numarası:" kısmına kadar olan büyük harfli kısım
        baslik_lines = []
        kanun_bilgileri_baslangic = -1

        for i, line in enumerate(lines):
            # "Kanun Numarası" veya "KANUN NUMARASI" bulundu mu?
            if re.search(r'Kanun\s+Numaras[ıi]', line, re.IGNORECASE):
                kanun_bilgileri_baslangic = i
                break
            # Satır çoğunlukla büyük harfse başlığa ekle
            upper_count = sum(1 for c in line if c.isupper())
            alpha_count = sum(1 for c in line if c.isalpha())
            if alpha_count > 0 and upper_count / alpha_count > 0.7:  # %70'i büyük harf
                baslik_lines.append(line)

        baslik = " ".join(baslik_lines).strip()
        print(f"   ✓ Başlık: {baslik[:60]}...")

        # 2. KANUN BİLGİLERİ: "Kanun Numarası"ndan "MADDE"ye kadar
        kanun_bilgileri_lines = []
        maddeler_baslangic = -1

        if kanun_bilgileri_baslangic != -1:
            for i in range(kanun_bilgileri_baslangic, len(lines)):
                line = lines[i]
                # MADDE ile başlayan satır mı?
                if re.match(r'^(MADDE|GEÇİCİ\s+MADDE)\s+\d+', line, re.IGNORECASE):
                    maddeler_baslangic = i
                    break
                kanun_bilgileri_lines.append(line)

        kanun_bilgileri = " ".join(kanun_bilgileri_lines).strip()
        print(f"   ✓ Kanun Bilgileri: {kanun_bilgileri[:80]}...")

        # 3. MADDELER: "MADDE X" ile başlayan tüm satırlar
        maddeler = []

        if maddeler_baslangic != -1:
            current_madde = None

            for i in range(maddeler_baslangic, len(lines)):
                line = lines[i]

                # Yeni madde başlangıcı mı?
                match = re.match(r'^(MADDE\s+\d+|GEÇİCİ\s+MADDE\s+\d+)', line, re.IGNORECASE)

                if match:
                    # Önceki maddeyi kaydet
                    if current_madde and current_madde["icerik"]:
                        maddeler.append(current_madde)

                    # Yeni madde başlat
                    madde_no = match.group(1).strip()
                    current_madde = {
                        "madde_no": madde_no,
                        "icerik": line
                    }
                else:
                    # Devam eden satırı ekle
                    if current_madde:
                        current_madde["icerik"] += " " + line

            # Son maddeyi ekle
            if current_madde and current_madde["icerik"]:
                maddeler.append(current_madde)

        print(f"   ✓ {len(maddeler)} madde bulundu")

        return baslik, kanun_bilgileri, maddeler

    except Exception as e:
        print(f"❌ Detay sayfası hatası ({law_url}): {e}")
        import traceback
        traceback.print_exc()
        return "", "", []

def main():
    driver = setup_driver()
    all_laws_data = []

    try:
        print(f"🌍 Siteye gidiliyor: {BASE_URL}")
        driver.get(BASE_URL + "#kanunlar")

        wait = WebDriverWait(driver, 15)

        print("🖱️  'Tüm Kanunlar' butonuna tıklanıyor...")
        try:
            show_all_btn = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, ".btn.btn-secondary.text-light.float-right.ml-1")
            ))
            show_all_btn.click()
        except:
            print("⚠️  Buton CSS ile bulunamadı, alternatif XPath deneniyor...")
            show_all_btn = driver.find_element(By.XPATH, "//a[contains(text(),'Tümüne Git')]")
            show_all_btn.click()

        print("⏳ Tablo yükleniyor...")
        time.sleep(3)

        law_links = driver.find_elements(By.CSS_SELECTOR, "a.ml-1")
        print(f"📋 Bu sayfada {len(law_links)} kanun bulundu. İlk 3 tanesi çekilecek.")

        target_urls = []
        for link in law_links[:3]:
            url = link.get_attribute("href")
            title = link.text.split('\n')[0].strip()
            if url:
                target_urls.append({"title": title, "url": url})

        # Her bir kanunun detayına git
        for idx, item in enumerate(target_urls, 1):
            print(f"\n{'='*60}")
            print(f"[{idx}/{len(target_urls)}] İşleniyor: {item['title']}")
            print(f"{'='*60}")

            baslik, kanun_bilgileri, maddeler = parse_law_detail(driver, item['url'], item['title'])

            law_record = {
                "kanun_adi": baslik if baslik else item['title'],
                "kanun_bilgileri": kanun_bilgileri,
                "url": item['url'],
                "maddeler": maddeler
            }
            all_laws_data.append(law_record)

            print(f"✓ Tamamlandı!")
            time.sleep(2)

        # Kaydet
        output_file = os.path.join(OUTPUT_DIR, "kanunlar_selenium.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_laws_data, f, ensure_ascii=False, indent=2)

        print(f"\n{'='*60}")
        print(f"✅ İşlem Tamam! Veriler kaydedildi: {output_file}")
        print(f"📊 Toplam {len(all_laws_data)} kanun işlendi.")

        # Özet göster
        for law in all_laws_data:
            print(f"\n📌 {law['kanun_adi'][:60]}...")
            print(f"   - Madde sayısı: {len(law['maddeler'])}")

    except Exception as e:
        print(f"❌ Genel Hata: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == "__main__":
    main()