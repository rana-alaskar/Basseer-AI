
# 🛡️ بصير AI – الحارس الدلالي | Basseer AI – Semantic Guardian

**نظام ذكي للكشف التلقائي عن التناقضات المنطقية والدلالية في بيانات الاستبيانات الحكومية**
**An intelligent system for automatically detecting logical and semantic contradictions in government survey data**

> مسار التحدي: المعالجة الذكية والتصنيف الآلي المدعوم بالذكاء الاصطناعي
> Track: AI-Driven Intelligent Processing and Automated Classification

---

## 📋 نظرة عامة | Overview

**بصير AI** نظام إثبات مفهوم (POC) يوفر طبقة تحقق ذكية متعددة المستويات لضمان جودة بيانات
المسوحات الإحصائية، عبر الجمع بين محرك قواعد منطقي وتحليل دلالي مدعوم بنموذج لغوي كبير (LLM).

**Basseer AI** is a proof-of-concept (POC) system that provides a multi-layer intelligent
validation pipeline to ensure the quality of survey data, combining a deterministic rule
engine with LLM-powered semantic analysis.

### كيف يعمل؟ | How it works
1. **محرك القواعد المنطقية | Rule Engine** — تحقق فوري من التعارضات الواضحة (العمر مقابل الخبرة،
   التعليم مقابل الوظيفة، الدخل مقابل الوظيفة...) | Instant checks for clear inconsistencies
   (age vs. experience, education vs. job title, income vs. job, etc.)
2. **طبقة LLM | LLM Layer** — تحليل دلالي عميق باستخدام Few-Shot Prompting بالعربية، مع
   fallback تلقائي عند عدم توفر مفتاح API | Deep semantic analysis via Arabic few-shot
   prompting, with automatic fallback when no API key is configured
3. **محرك التوصيات | Recommendation Engine** — توليد توصيات مبنية على البيانات المخزّنة
   (أسئلة يجب إعادة صياغتها، مناطق أو باحثين ميدانيين بحاجة لمراجعة) | Data-driven
   recommendations (questions to rephrase, regions/enumerators needing review)
4. **درجة الثقة | Confidence Score** — نموذج تسجيل مركّب يجمع نتائج القواعد وLLM في درجة واحدة
   من 0–100 | A composite scoring model combining rule-based and LLM findings into a single
   0–100 confidence score

---

## ✨ الميزات الرئيسية | Key Features

- ✅ تحقق فوري (`/validate`) وتحقق مع تخزين (`/ingest`) عبر REST API
  Instant validation and store-and-validate endpoints via a REST API
- ✅ رفع ملفات CSV للتحقق الجماعي من حتى 6000 سجل دفعة واحدة (`/upload_csv`)
  Bulk CSV upload for validating up to 6,000 records at once
- ✅ لوحة مراقبة تفاعلية (Streamlit) بثلاث تبويبات: إدخال الاستبيان، الباحث الميداني،
  لوحة الجهة المشرفة
  Interactive Streamlit dashboard with three tabs: Survey Entry, Field Researcher, and
  Supervising Authority views
- ✅ خريطة حرارية تفاعلية حسب المنطقة أو الباحث الميداني بأربعة مقاييس (عدد التناقضات،
  نسبة التعارض، متوسط الثقة، معدل اختلاف LLM)
  Interactive heatmap by region or enumerator with four metrics (conflict count, conflict
  rate, average confidence, LLM disagreement rate)
- ✅ سير عمل مراجعة ميدانية (تحديث حالة كل سجل: قيد المراجعة/مؤكد/يحتاج تصحيح)
  Field-review workflow with per-record status tracking
- ✅ توصيات مجمّعة تلقائيًا لتحسين تصميم الاستبيان وتدريب الباحثين
  Auto-generated recommendations for survey design and enumerator training
- ✅ واجهة برمجية موثّقة تلقائيًا عبر Swagger (`/docs`)
  Auto-generated API documentation via Swagger
- ✅ مجموعة اختبارات آلية (22 اختبار) لمحرك القواعد والتسجيل
  Automated test suite (22 tests) covering the rule engine and scoring logic

---

## 🛠️ التقنيات المستخدمة | Tech Stack

| الطبقة \| Layer | التقنية \| Technology |
|---|---|
| Backend | Python, FastAPI, Uvicorn |
| Database | SQLite (via SQLAlchemy ORM) |
| Dashboard | Streamlit, Plotly |
| Data handling | Pandas |
| LLM Provider | **Groq API — Llama 3.3 70B Versatile** |
| Testing | Pytest |

> النظام مبني ليدعم عدة مزودي LLM اختياريًا (OpenAI, Anthropic, Gemini, Groq) عبر متغيرات
> البيئة، إلا أن **الإعداد الفعلي في النسخة النهائية يستخدم Groq مع نموذج Llama 3.3 70B
> Versatile**. عند عدم توفر مفتاح API، يعمل النظام تلقائيًا في وضع القواعد فقط (offline)
> بدون توقف.
>
> The system's LLM layer is provider-agnostic and can optionally connect to OpenAI,
> Anthropic, or Gemini via environment variables, but **the final configured setup uses
> Groq with the Llama 3.3 70B Versatile model**. If no API key is set, the system
> automatically falls back to rule-based validation only, with no downtime.

---

## 🏗️ هيكل المشروع | Project Structure

```
basseer-ai/
├── backend/
│   ├── main.py                      # FastAPI app and all endpoints
│   └── validators/
│       ├── rules.py                 # Deterministic rule engine
│       ├── semantic_mock.py         # Offline semantic fallback
│       ├── llm_layer.py             # LLM integration (Groq/OpenAI/Anthropic/Gemini)
│       └── scoring.py               # Confidence score calculation
├── services/
│   └── pipeline.py                  # Validation pipeline orchestrator
├── dashboard/
│   └── app.py                       # Streamlit dashboard (3 tabs)
├── storage/
│   ├── db.py                        # SQLite session/engine setup
│   └── models.py                    # SQLAlchemy models
├── scripts/
│   ├── generate_dataset.py          # Generates the 100-record sample dataset
│   ├── generate_demo_csvs.py        # Generates the demo CSV files
│   ├── ingest_dataset.py            # Ingests sample data via the API
│   ├── run.sh                       # One-command startup (Linux/Mac)
│   └── run_windows.ps1              # One-command startup (Windows)
├── data/
│   ├── anonymized_sample_100.csv    # Generated sample dataset (100 records)
│   └── demo/                        # Ready-made CSV files for the bulk-upload demo
│       ├── demo_clean.csv
│       ├── demo_flagged.csv
│       ├── demo_mixed.csv
│       ├── demo_fast.csv
│       ├── large_demo_5000.csv
│       └── survey_template.csv
├── docs/
│   ├── ARCHITECTURE_BRIEF.md
│   ├── POC_DEMO_SCRIPT.md
│   └── JUDGES_DEMO.md
├── tests/
│   └── test_core.py                 # 22 unit tests
├── .env.example
└── requirements.txt
```

> ملاحظة: قاعدة البيانات (`data/basseer.db`) تُنشأ تلقائيًا عند أول تشغيل ولا تُرفع إلى
> المستودع، وكذلك ملف `.env` (يحتوي على مفاتيح خاصة) ومجلدات `__pycache__`.
>
> Note: the SQLite database (`data/basseer.db`) is created automatically on first run and
> is not committed to the repository, along with the `.env` file (contains private keys)
> and `__pycache__` directories.

---

## 🚀 التشغيل السريع | Quick Start

### المتطلبات | Requirements
- Python 3.10+
- pip

### الخطوات | Steps

```bash
# 1. Clone the repository
git clone <YOUR_GITHUB_REPO_URL>
cd basseer-ai

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
# .\venv\Scripts\Activate.ps1   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and set LLM_PROVIDER / LLM_API_KEY (or leave as "offline" to skip LLM)

# 5. Generate the sample dataset
python scripts/generate_dataset.py

# 6. Run the backend API
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# 7. In a new terminal, ingest the sample data
python scripts/ingest_dataset.py

# 8. Run the dashboard
streamlit run dashboard/app.py --server.port 8501
```

Or use the all-in-one startup script:
```bash
bash scripts/run.sh          # Linux/Mac
.\scripts\run_windows.ps1    # Windows
```

### الوصول | Access
- **API:** http://127.0.0.1:8000
- **API Docs (Swagger):** http://127.0.0.1:8000/docs
- **Dashboard:** http://127.0.0.1:8501

---

## ⚙️ إعداد مزود LLM | LLM Configuration

يمكن ضبط مزود LLM إما من داخل التطبيق (شاشة إعداد تظهر تلقائيًا عند أول تشغيل، أو من
"⚙️ إعدادات النظام" بالشريط الجانبي)، أو مباشرة عبر `.env`:

The LLM provider can be configured either from within the app (a setup prompt appears on
first run, or via "⚙️ System Settings" in the sidebar), or directly in `.env`:

```env
LLM_PROVIDER=groq
LLM_API_KEY=your-groq-api-key
LLM_MODEL=llama-3.3-70b-versatile
```

بدون مفتاح صالح، يعمل النظام تلقائيًا بوضع القواعد فقط (`offline`) دون أي انقطاع.
Without a valid key, the system runs in rule-based (`offline`) mode with no interruption.

---

## 📡 واجهات API الرئيسية | Main API Endpoints

| Endpoint | Method | الوصف \| Description |
|----------|--------|-------|
| `/validate` | POST | تحقق فوري بدون تخزين \| Validate a record without storing it |
| `/ingest` | POST | تحقق + تخزين \| Validate and store a record |
| `/upload_csv` | POST | تحقق جماعي من ملف CSV (حتى 6000 سجل) \| Bulk CSV validation (up to 6,000 rows) |
| `/stats` | GET | إحصائيات جودة البيانات \| Data quality statistics |
| `/heatmap` | GET | بيانات الخريطة الحرارية \| Heatmap data |
| `/cell_detail` | GET | تفاصيل خلية محددة \| Details for a specific heatmap cell |
| `/field_researcher` | GET | سجلات بحاجة لمراجعة ميدانية \| Records pending field review |
| `/review` | POST | تحديث حالة مراجعة سجل \| Update a record's review status |
| `/recommendations` | GET | التوصيات المجمّعة \| Aggregated recommendations |
| `/download_template` / `/download_demo_files` | GET | تحميل قالب/ملفات تجريبية \| Download template/demo CSV files |
| `/llm_settings` | GET/POST | عرض/تحديث إعدادات LLM \| View/update LLM configuration |
| `/health` | GET | صحة النظام وإحصائيات LLM \| System health and LLM usage stats |

### مثال استجابة `/validate` | Sample `/validate` response
```json
{
  "confidence_score": 72,
  "confidence_label": "Medium confidence",
  "confidence_reason_en": "Mismatch between age and years of experience",
  "detected_by": "hybrid",
  "llm_used": true,
  "latency_ms": 430
}
```

---

## 🗺️ الخريطة الحرارية | Heatmap

تدعم أربعة مقاييس قابلة للتبديل: العدد، نسبة التعارض، متوسط الثقة، ومعدل اختلاف نتائج
القواعد عن LLM — بمحورين ممكنين: المنطقة أو الباحث الميداني. عند النقر على خلية تظهر
تفاصيل الأخطاء وأكثر القواعد انتهاكًا والتوصية المقترحة.

Supports four switchable metrics: conflict count, conflict rate, average confidence, and
rule-vs-LLM disagreement rate — grouped by either region or enumerator. Clicking a cell
reveals detailed error counts, top violated rules, and a suggested recommendation.

---

## 🧪 الاختبارات | Testing

```bash
pytest tests/test_core.py -v
```

يغطي ملف الاختبارات (22 اختبارًا) محرك القواعد ونموذج درجة الثقة.
The test suite (22 tests) covers the rule engine and the confidence scoring model.

---

## 📊 بيانات العرض | Sample Data

يتضمن المشروع مجموعة بيانات مولّدة عشوائيًا (100 سجل) لأغراض العرض، بالإضافة إلى ملفات CSV
جاهزة في `data/demo/` (بيانات نظيفة، بيانات بها تعارضات، بيانات مختلطة، ومجموعة كبيرة من
5000 سجل) لاختبار ميزة الرفع الجماعي. **لا تحتوي البيانات على أي معلومات شخصية حقيقية.**

The project includes a synthetically generated dataset (100 records) for demo purposes,
plus ready-made CSV files in `data/demo/` (clean, flagged, mixed, and a 5,000-row large
dataset) for testing the bulk-upload feature. **No real personal data is included.**

---

## 📖 المزيد | Further Reading

- [سيناريو العرض للجنة التحكيم \| Judges Demo Script](docs/JUDGES_DEMO.md)
- [سيناريو عرض المشروع \| POC Demo Script](docs/POC_DEMO_SCRIPT.md)
- [الهيكل المعماري \| Architecture Brief](docs/ARCHITECTURE_BRIEF.md)

---
