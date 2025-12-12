import json
import os
import chromadb
from sentence_transformers import SentenceTransformer

# --- AYARLAR ---
JSON_PATH = os.path.join("data", "raw", "kanunlar_selenium.json")
CHROMA_PATH = os.path.join("data", "chroma_db") # Veritabanının kaydedileceği klasör
COLLECTION_NAME = "kanunlar_db"

def load_data():
    """JSON dosyasını okur."""
    if not os.path.exists(JSON_PATH):
        print(f"❌ Hata: {JSON_PATH} bulunamadı. Önce veri çekme işlemini yapın.")
        return []

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def create_vector_db():
    print("📥 Veri yükleniyor...")
    laws = load_data()
    if not laws: return

    # 1. Embedding Modelini Başlat (Türkçe destekli güçlü, hafif bir model)
    # İlk çalıştırışta modeli internetten indirecektir (yaklaşık 400MB)
    print("🧠 Embedding modeli yükleniyor (sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)...")
    embedding_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')

    # 2. ChromaDB İstemcisini Başlat (Persistent = veriyi diske kaydeder)
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # Koleksiyonu oluştur (Varsa silip tekrar oluşturuyoruz temiz kurulum için)
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"🗑️  Eski koleksiyon silindi: {COLLECTION_NAME}")
    except:
        pass

    collection = client.create_collection(name=COLLECTION_NAME)

    # 3. Veriyi Hazırla ve Yükle
    print("⚙️  Veriler vektörleştirilip veritabanına işleniyor...")

    documents = [] # Metnin kendisi
    metadatas = [] # Kaynak bilgisi (Hangi kanun, kaçıncı madde)
    ids = []       # Benzersiz ID
    embeddings = [] # Vektör sayısal karşılığı

    count = 0
    for law in laws:
        kanun_adi = law.get("kanun_adi", "Bilinmiyor")

        for madde in law.get("maddeler", []):
            madde_no = madde.get("madde_no", "")
            icerik = madde.get("icerik", "")

            # İçerik çok kısaysa (örn: "Mülga") atla
            if len(icerik) < 10:
                continue

            # Model için metin: "İş Kanunu Madde 1: Bu kanunun amacı..." formatında olursa daha iyi anlar
            combined_text = f"{kanun_adi} - {madde_no}: {icerik}"

            documents.append(icerik)
            metadatas.append({
                "source": kanun_adi,
                "article": madde_no,
                "url": law.get("url", "")
            })
            ids.append(f"{kanun_adi}_{madde_no}_{count}")  # Unique ID

            # Manuel embedding (Opsiyonel: Chroma kendi de yapabilir ama biz kontrol bizde olsun istiyoruz)
            # Bu adımda model metni [0.12, -0.45, ...] şeklinde sayılara çevirir.
            vector = embedding_model.encode(combined_text).tolist()
            embeddings.append(vector)

            count += 1

            # Batch işlemi: Her 50 maddede bir veritabanına yaz (RAM şişmesin)
            if len(documents) >= 50:
                collection.add(
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                    ids=ids
                )
                print(f"   -> {count} madde işlendi...")
                documents, metadatas, ids, embeddings = [], [], [], []

    # Kalanları ekle
    if documents:
        collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )

    print(f"✅ Başarılı! Toplam {count} madde vektör veritabanına kaydedildi.")
    print(f"📂 Veritabanı konumu: {CHROMA_PATH}")

if __name__ == "__main__":
    create_vector_db()