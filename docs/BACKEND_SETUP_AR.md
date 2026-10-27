# NEURA AI — النسخة المصححة

هذه نسخة منفصلة من أرشيف المشروع، مهيأة لـ Linux + Web + llama-cpp-python/Vulkan. لا تتضمن الأوزان أو ملفات الأسرار أو البيئة القديمة. لم تُستبدل ملفات مشروعك الأصلي.

## التشغيل باستخدام البيئة الموجودة على جهازك

فك الضغط ثم افتح الطرفية داخل مجلد `NEURA_AI_Repaired` ونفّذ الأمر التالي؛ يعمل من bash وfish:

```sh
env NEURA_PYTHON='/path/to/existing/venv/bin/python' ./start-neura.sh
```

افتح `http://127.0.0.1:8000/`. الواجهة وAPI من الأصل نفسه. يعمل الخادم في الطرفية؛ أوقفه بـ Ctrl+C. لا يقتل السكربت عمليات أخرى ولا يثبت حزمًا عند كل تشغيل. يمكن استخدام `neura-launcher.py` كواجهة تشغيل صغيرة، مع تعيين `NEURA_PYTHON` نفسه عند الحاجة.

مسار النماذج يُكتشف من `../neura AI/Neura_Package/models`، ثم من مجلد Downloads المعروف. لتحديد مسار آخر:

```sh
env NEURA_MODELS_DIR='/absolute/path/to/models' NEURA_PYTHON='/path/to/venv/bin/python' ./start-neura.sh
```

ملفات `.env` لا تُقرأ تلقائيًا؛ صدّر المتغيرات المطلوبة من الطرفية. لا تشغّل أكثر من worker، ولا تشغّل خوادم LLM موازية مع هذه النسخة.

## النماذج المسجلة

| المستوى | النموذج الفعلي |
|---|---|
| FAST | Gemma 3 4B IT؛ اسم الملف المحلي ما زال gemma-4-E4B |
| DAILY | Qwen3.5 9B Q4_K_M |
| EXPERT | نموذج Qwen3.5 9B مجتمعي مقطّر؛ ليس Claude من Anthropic |
| CODER | النموذج المقطّر نفسه مؤقتًا |
| VISION | Qwen3VL 8B مع mmproj-Qwen3VL-8B-Instruct-F16.gguf |

Qwen3.8 معطّل لعدم وجود ملفه. Qwen2.5-Coder-14B معطّل لأن ملفه ترافقه علامة تنزيل `.aria2`. لا تحذف العلامة لتجاوز الفحص؛ أكمل التنزيل وتحقق من المصدر والبصمة أولًا، ثم عدّل `enabled` وربط CODER في YAML. Embeddings محفوظة خارج التسجيل النشط إلى أن توجد ميزة RAG تستخدمها. بصمات السجل تصف الملفات المحلية وقت التدقيق ولا تثبت مصدرها أو ترخيصها.

## الاستخدام

- الوضع «تلقائي» يختار المستوى حسب الطلب. الأزرار الأخرى تثبت اختيارك، ويظهر النموذج الذي استجاب فعليًا.
- أرفق صورة ثم أرسل وصف المطلوب؛ تستخدم الصور المضمّنة مسار Vision. تُرفض روابط الصور البعيدة. وجود صورة في سجل المحادثة يبقي المحادثة بحاجة إلى نموذج Vision.
- تُحفظ الردود المكتملة في Vault محلي حقيقي. «الجلسات المحفوظة» تستعيد المحادثة أو تحذفها. حفظ المحادثة لا يفعّل تلقائيًا ذاكرة معرفة أو Embeddings.
- «إنشاء ملفات من الطلب» يستدعي Task Invoice صريحًا. الطلب البرمجي العادي يظل محادثة ولا يبدأ سلسلة مشاريع تلقائيًا. الملفات الناتجة تمر بفحص الصياغة والمتطلبات الساكنة، ولا تُشغّل تلقائيًا.
- `/route` يختار فقط ولا يولّد ردًا. `/v1/chat/completions` يدعم سجل system/user/assistant، وضبط التوليد وبث التوكنات الفعلي.
- تنفيذ Terminal وGit وإرسال البريد غير مفعّل. الأدوات المنفذة: `search_web` عند تثبيت ddgs، و`draft_email` التي تعيد مسودة فقط. `/skills` يعلن هذا السجل المحدود، ولا توجد منظومة وكلاء مستقلة.

## API والطرفية

كل عملية كتابة، وقراءة الجلسات، تتطلب `X-Neura-Token`. يولّد الخادم الرمز في `~/.local/share/neura-ai/.api-token` بصلاحية 0600، ويمرره للواجهة محليًا. لا تُدرجه في URL أو السجلات. هذه حماية لخادم loopback وليست نشرًا متعدد المستخدمين.

العميل التالي يقرأ الرمز محليًا ولا يحمّل نموذجًا آخر:

```sh
/path/to/venv/bin/python tools/neura_client.py 'ما عاصمة فرنسا؟' --tier fast --stream
/path/to/venv/bin/python tools/neura_client.py 'Create main.py with add(a,b) returning a+b' --project --required-file main.py --python-symbol add
```

المسارات الرئيسية: `/health`, `/stats`, `/route`, `/v1/chat/completions`, `/projects`, `/vault/save`, `/vault/sessions`, `/tool/call`, `/skills`, `/stt`, `/tts`. التوثيق التفاعلي في `/docs`؛ استخدم العميل أو الواجهة للمسارات التي تتطلب الرمز.

## بيئة جديدة

اعتماديات Backend منفصلة عن محرك الاستدلال والميزات الاختيارية. يثبت ملف `constraints-tested.txt` الإصدارات التي اجتازت اختبارات البيئة النظيفة:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements-backend.txt
env CMAKE_ARGS='-DGGML_VULKAN=ON' .venv/bin/python -m pip install -r requirements-inference.txt
```

بناء محرك Vulkan يتطلب أدوات البناء وترويسات Vulkan المناسبة لنظامك. النسخة المثبتة الموجودة على جهازك اجتازت اختبار GPU؛ إعادة بناء المحرك من الصفر ليست ضمن اختبار تثبيت حزم Backend. عند غياب GPU لا يوجد سقوط صامت إلى CPU؛ اختره صراحةً بواسطة `NEURA_N_GPU_LAYERS=0` إذا أردت ذلك.

`requirements-optional.txt` يحتوي Telegram والبحث الشبكي. البحث وTelegram يتصلان بالإنترنت؛ نص Telegram يمر بخدمة Telegram. ملفات Windows/Flet محفوظة للتاريخ ولم تُعد هذه النسخة اختبارًا لتوافق Windows. `requirements-windows-legacy.txt` ليس بديلًا عن متطلبات Linux.

## الصوت

ملفا `whisper-large-v3.bin` و`kokoro-v1_0.pth` وحدهما لا يكفيان لتشغيل الصوت. لا تنزّل النسخة أوزانًا أو تعتمد خدمات صوت سحابية تلقائيًا.

- STT: يحتاج `whisper-cli` من whisper.cpp وffmpeg وملف GGML المحلي. اضبط `NEURA_WHISPER_CLI` و`NEURA_WHISPER_MODEL` عند الحاجة. الحد 20 MB ودقيقتان، واللغات ar/en/auto.
- TTS: المحوّل الحالي يدعم Piper CLI وصوت ONNX وJSON محليين، عبر `NEURA_PIPER_CLI`, `NEURA_PIPER_MODEL`, `NEURA_PIPER_LANG`. لا يدّعي دعم ملف Kokoro منفردًا.
- عندما تنقص المتطلبات تعيد API حالة 501، ويتعطل زر التسجيل. قد يستخدم زر النطق صوتًا محليًا مثبتًا في المتصفح إن وُجد؛ لا توجد إحالة سحابية.

## التحقق

```sh
/path/to/venv/bin/python -m pytest -q
/path/to/venv/bin/python tools/audit_models.py --sha256 --output model-inventory.json
/path/to/venv/bin/python tools/model_smoke.py --tier fast --output smoke-fast.json
/path/to/venv/bin/python tools/evaluate_models.py acceptance-daily.json
```

الاختبارات الافتراضية لا تتصل بالشبكة ولا تحتاج GPU أو أوزانًا أو Telegram فعليًا. اختبارات العتاد منفصلة ويجب تشغيلها بعد إيقاف خادم Neura حتى لا تتكرر إقامة الأوزان. نتائج المراجعة المرفقة تذكر ما تم اختباره فعلًا وما بقي غير متاح.

البث والإلغاء لهما مهلة محددة. الإلغاء تعاوني بين خطوات التوليد؛ تحميل النموذج أو تقييم native جارٍ قد ينتهي لاحقًا، ويبقى القفل ممسوكًا حتى ينتهي لمنع تبديل نموذج قيد الاستخدام. قياسات GPU المفقودة تظهر كغير معروفة، وتقديرات VRAM معلّمة ولا تُعد ضمان تخصيص.

قوالب المحادثة تعتمد Metadata المحلية وواجهة chat الرسمية: [توثيق llama-cpp-python](https://llama-cpp-python.readthedocs.io/en/latest/). تنسيق الواجهة CSS مبني مسبقًا محليًا؛ إعادة بنائه اختيارية بـ `npm ci && npm run build:css` وفق إعداد Tailwind 3.4.17: [توثيق Tailwind](https://v3.tailwindcss.com/docs/installation). لا تحتاج Node لتشغيل الواجهة.
