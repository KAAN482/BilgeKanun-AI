import os
import google.generativeai as genai
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# 1. Ortam Değişkenlerini Yükle (.env dosyasından)
load_dotenv("key.env")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("❌ Hata: GOOGLE_API_KEY bulunamadı! .env dosyasını kontrol et.")

# Gemini Konfigürasyonu
genai.configure(api_key=GOOGLE_API_KEY)

# --- AYARLAR ---
CHROMA_PATH = os.path.join("data", "chroma_db")
COLLECTION_NAME = "kanunlar_db"
EMBEDDING_MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'

class LegalRAG:
    def __init__(self):
        print("🤖 RAG Sistemi Başlatılıyor...")

        # Embedding Modelini Yükle (Sorguları vektöre çevirmek için)
        print("   ↳ Embedding modeli yükleniyor...")
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

        # ChromaDB Bağlantısı
        print("   ↳ Vektör veritabanına bağlanılıyor...")
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.collection = self.chroma_client.get_collection(name=COLLECTION_NAME)

        # Gemini Modeli (Flash modeli hızlı ve ücretsiz tier için ideal)
        print("   ↳ Gemini 2.5 Flash hazırlanıyor...")
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def retrieve_documents(self, query, n_results=3):
        """Kullanıcının sorusuna en uygun kanun maddelerini bulur."""
        # Soruyu vektöre çevir
        query_vector = self.embedding_model.encode(query).tolist()

        # Veritabanında ara
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=n_results,
            include=["documents", "metadatas"]
        )

        return results

    def generate_answer(self, query):
        """Bulunan belgeleri kullanarak Gemini ile cevap üretir."""

        # 1. Alakalı Belgeleri Getir (Retrieval)
        search_results = self.retrieve_documents(query)

        docs = search_results['documents'][0]
        metadatas = search_results['metadatas'][0]

        # 2. Context (Bağlam) Oluştur
        context_text = ""
        for i, doc in enumerate(docs):
            source_info = f"{metadatas[i]['source']} - {metadatas[i]['article']}"
            context_text += f"KAYNAK {i+1} ({source_info}):\n{doc}\n\n"

        # 3. System Prompt (Yapay Zeka'ya Rol Verme)
        # Burası "Prompt Engineering" sanatının konuşturulduğu yerdir.
        system_prompt = f"""
Sen "BilgeKanun AI" adında uzman bir Türk Hukuku asistanısın.
Görevin: Kullanıcının sorusunu, SADECE aşağıda verilen kanun maddelerine (Context) dayanarak cevaplamaktır.

KURALLAR:
1. Sadece verilen bağlamdaki bilgiyi kullan. Bağlamda bilgi yoksa "Bu konuda veritabanımda bilgi bulunmuyor." de.
2. Cevap verirken mutlaka hangi kanun maddesine atıfta bulunduğunu belirt (Örn: "İş Kanunu Madde 24'e göre...").
3. Hukuki terimleri koru ama vatandaşa anlatır gibi açık ve net ol.
4. Asla kendi hayal gücünle kanun uydurma.

BAĞLAM (CONTEXT):
{context_text}

KULLANICI SORUSU:
{query}
"""
        # 4. Gemini'ye Gönder ve Cevabı Al
        response = self.model.generate_content(system_prompt)
        return response.text, metadatas

# --- TEST KISMI (Doğrudan çalıştırıldığında) ---
if __name__ == "__main__":
    rag = LegalRAG()

    while True:
        soru = input("\n⚖️  Hukuki Sorunuz (Çıkış için 'q'): ")
        if soru.lower() == 'q':
            break

        print("\n⏳ Düşünüyor ve araştırıyorum...")
        cevap, kaynaklar = rag.generate_answer(soru)

        print("\n" + "="*50)
        print("🤖 BİLGEKANUN AI CEVABI:")
        print("="*50)
        print(cevap)
        print("\n📚 KULLANILAN KAYNAKLAR:")
        for k in kaynaklar:
            print(f"- {k['source']} {k['article']}")
        print("="*50)