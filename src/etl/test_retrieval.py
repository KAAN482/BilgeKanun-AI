import chromadb
from sentence_transformers import SentenceTransformer
import os

# --- AYARLAR ---
CHROMA_PATH = os.path.join("data", "chroma_db")
COLLECTION_NAME = "kanunlar_db"

def test_search(query_text, n_results=3):
    print(f"\n🔎 SORU: '{query_text}'")
    print("-" * 50)

    # 1. Model ve Veritabanı Bağlantısı
    # Not: Modeli tekrar yüklüyoruz, normalde API'de bunu bir kere yükleyip hafızada tutacağız.
    embedding_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception as e:
        print(f"❌ Koleksiyon bulunamadı! Önce load_to_vector_db.py çalıştırılmalı. Hata: {e}")
        return

    # 2. Soruyu Vektöre Çevir
    query_vector = embedding_model.encode(query_text).tolist()

    # 3. Veritabanında En Yakın Vektörleri Ara
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=n_results,
        include=["documents", "metadatas", "distances"]
    )

    # 4. Sonuçları Yazdır
    if not results['documents']:
        print("❌ Hiç sonuç bulunamadı.")
        return

    for i in range(n_results):
        doc = results['documents'][0][i]
        meta = results['metadatas'][0][i]
        distance = results['distances'][0][i] # Düşük mesafe (0'a yakın) = Yüksek benzerlik

        # Skor (Distance'ı benzerlik skoruna çevirelim: 1 - distance mantığı kabaca)
        print(f"📄 SONUÇ {i+1} (Mesafe: {distance:.4f})")
        print(f"   📌 Kaynak: {meta['source']} - {meta['article']}")
        print(f"   📝 İçerik: {doc[:200]}...") # İlk 200 karakteri göster
        print("-" * 30)

if __name__ == "__main__":
    # Test Soruları
    test_search("Sera gazı emisyonları ile ilgili maddeler nelerdir?")
