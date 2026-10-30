# Neura 0.4.7 — إصلاح المراجعة المستقلة ودليل القبول الحالي

تاريخ الجولة: 2026-10-30، Asia/Riyadh. **القبول الكلي `FAILED`، كود الخروج `1`؛ ليست البنود الـ109 مكتملة.** أُصلحت أسباب F1–F4 في المسارات القائمة، واجتازت فحوص الانحدار الحالية. التجارب الفعلية كشفت ثلاثة إخفاقات جودة يجب إبقاؤها مفتوحة: EXPERT العام لم يكمل الخطة، وصورة الأحمر/الأزرق أخفقت في الواجهة، وتعديل الوضع الداكن استبدل رابط Login السابق. الأخير مسجل ضد بندين؛ عدد حالات FAIL في المصفوفة لا يساوي عدد الحوادث المستقلة.

الجولة المرجعية `20261030T150309_b1faac38`. ملفا `MATRIX.csv` و`results.json` يسجلان التنفيذ والدليل لكل ID، و`REPORT_AR.md` يعرضهما بالعربية. [مصفوفة المصدر الحالية](VERIFICATION_MATRIX_0.4.7.csv) و[دليل إعادة الفحوص](REVIEW_047_VERIFICATION_AR.md) موجودان في المستودع. روابط `artifacts/` و`logs/` و`screenshots/` في نسخة التقرير داخل الأدلة تشير إلى ملفات الجولة؛ ليست مواقع خارجية. تقرير0.4.6 وأرشيفاه محفوظة بأسمائها وبصماتها الأصلية، ولم يُستبدل دليلها التاريخي بنتائج جديدة.

## النسخة والنطاق

| الحقل | الواقع المختبر |
|---|---|
| checkout | `/home/foxlinux/Documents/Codex/2026-10-27/files-mentioned-by-the-user-neura/work/neura-workspace-v2` |
| baseline | `69a0cc0eeea4dbc143ed7072fca8a256d80f7cc0`، `VERSION=0.4.6`، clean قبل العمل؛ الفرع السابق `verify/full-catalog-20261030` |
| فرع الإصلاح | `fix/review-046-routing-plans-preview-updater` |
| commit التنفيذ | `15d309c`؛ هوية لقطة التسليم الكاملة بعد ملفات التقرير في `results.json::source_after` |
| النسخة | `VERSION=0.4.7`؛ الحزمة المحلية `neura-ai-bin 0.4.7-1 x86_64` |
| المثبت على النظام | `neura-ai-bin 0.4.5-1`، `/opt/neura-ai/app`؛ لم أُجر تثبيتًا أو تحديثًا إداريًا |
| الهدف | `work/review-047-final-package/opt/neura-ai/app`، مستخرج من الحزمة النهائية؛ الاختبارات تستورد هذا الهدف، وليس checkout بدلًا منه |
| النظام | CachyOS، Linux x86_64، KDE/Wayland؛ التفاصيل الحالية في `artifacts/static.json` |
| Runtime | Python3.14.8، pytest9.2.0، PySide6 6.12.0، llama-cpp-python0.3.36، FastAPI0.151.0، Pydantic2.12.5 |
| النموذج الفعلي | llama.cpp CPU صراحة، `n_ctx=4096`، `dedicated_coder=True`؛ لا تجربة Vulkan/GPU في هذه الجولة |
| الواجهة | IAB بأصول الحزمة الحالية وخلفيتها الحقيقية؛ Qt offscreen بمحاكيات معلنة في فحوص مستقلة، sandbox مفعّل |
| سطح المكتب | قبول GIO الحقيقي لطلبات Discord/Brave/YouTube؛ ظهور النوافذ وتحميل الصفحات غير مرصودين |
| الحدود | لا push أو release أو AUR، لا رسالة Telegram/بريد، لا تشغيل Python مولّد أو تثبيت اعتمادياته، لا تعديل بيانات المستخدم أو أوزانه |

تغييرات0.4.7 كانت غير committed عند البناء والاختبار، ثم حُفظت محليًا في commit التنفيذ. مقارنة الملفات تثبت تطابق **102 ملف runtime** مع الهدف المختبر؛ إضافة التقرير والـCSV لاحقًا لا تغيّر runtime. `results.json` يحتفظ بهوية المصدر والتغييرات عند بدء الجولة وبعدها، وملف patch يبين الفرق عن baseline. ليست هذه تجربة تثبيت المستخدم الحالية.

بصمة runtime `neura-ai-0.4.7-linux-x86_64.tar.zst`: `f76d95b089f99269a3904d1e85b0d31a392db5632905259140937e84020aa35d`. بصمة حزمة Arch: `358ba988a291fe5e75c783687780a5142a0c62a070943d043e18198db3b9c5b3`. بقية البصمات في `artifacts/package-SHA256SUMS.txt` وبصمات التسليم الخارجية.

## ما أُصلح من المراجعة

| finding / IDs | المسار وكيف يعمل | الدليل الحالي والقيد |
|---|---|---|
| F1 — `N049 N042 N066 N054` | `src/core/chat_dispatch.py::project_intent/active_edit_intent/dispatch` تتعرف على لعبة/كود/سكربت وإضافات برمجية عربية وإنجليزية. طلب المشروع يسبق الرد العام، ويعيد استعمال `ProjectJobs`. الإضافة إلى المشروع الحالي تقرأ مصدره الفعلي عبر `_edit_current`؛ غياب هدف حالي فريد يعيد اختيارًا دون job. بقيت حواجز النفي والشرح والاقتباس والطلب المكرر وdirty والعمل النشط. | العبارات الست المحددة أدناه أُدخلت من composer، لكل منها job واحدة. اختبارات contract تشمل النفي والشرح والاقتباسات واختيار الهدف. قواعد التوجيه محدودة وليست فهمًا لكل صياغة طبيعية. نجاح التوجيه لا يضمن أن التعديل حافظ على كل السلوك. |
| F2 — `N006 N041 N042` | `src/core/invoice_orchestrator.py::ImplementationPlan/plan_completion/inspect_plan/require_plan` تعرّف JSON بخطوات3–6 وأسماء ملفات آمنة. تحتاج نهاية `stop` والملفات المطلوبة قبل coder، بحد أقصاه768 رمزًا. تسجل نتيجة الخطة قبل الرفض في workspace والمسار legacy. فشل الخطة ينتهي بصدق ويحفظ last-good؛ لا retry تلقائي. | خطة `length` الاصطناعية لم تصل coder في المسارين؛ خطة سليمة تتقدم، وخطة تعديل فاشلة أبقت المراجعة السابقة. تجربة حقيقية منفصلة أعادت JSON كاملًا ثم `main.py` دون تشغيله. اختبار EXPERT النصي الأصلي بقي فاشلًا؛ العقد الجديد لا يمحو ذلك الإخفاق. |
| F3 — `N050 N055 N056` | `src/core/project_store.py::preview_snapshot` تربط metadata والـmanifest وملف `.neura/revisions/{expected_revision}.json` تحت حد التخزين، ثم `src/core/project_preview.py::issue` يصدر capability للبايتات نفسها. لا قراءة ثانية غير محمية لـlatest. اللقطة المصدرة لا تتغير مع commit لاحق. | اختبار interleaving القديم، وكاتب فعلي في thread أخرى، وتغير/ثبات قائمة الأصول، وقراءة HTTP من مستهلكين embedded/full. إما اللقطة الصحيحة أو conflict؛ لا revision1 ببايتات revision2. تجربة UI الحالية عرضت العنوان المحفوظ نفسه في المضمنة والكاملة عند revision4. هذا إصلاح اتساق مراجعات، وليس ادعاء أن المراجعة أثبتت privilege escape. |
| F4 — `N026` | `web/workspace.js::prepareUpdate/checkUpdate/releaseUpdate` ترفض dirty/saving/opening/active job/chat busy وتجمّد واجهة جاهزة مؤقتًا. `MainWindow.prepare_update` تقرأ الحالة، و`BackendService.prepare_update` يحجز admission عبر API مصادق مرتبط بالـinstance. `ProjectJobs.prepare_update` ترفض queued/running/native work؛ `NeuraLoop.exclusive` يمنع inference جديدًا بعد الحجز. تُراجع UI مرة أخرى قبل `stop`. الإلغاء أثناء الحجز لا يترك reservation عالقة؛ فشل المصادقة يستعيد الخدمة والتفضيلات والملفات. | 6 سيناريوهات Qt offscreen حالية نجحت، منها dirty، وjob خارج المشروع المعروض، والإلغاء أثناء prepare، والتعديل المتأخر، والإيقاف عند الخمول فقط، والاسترداد. نتيجة Polkit/installer كانت stub صريحة؛ لا `pkexec/pacman` حقيقي، ولذلك `N026` جزئي. يوجد تأجيل واضح حتى يحفظ المستخدم العمل أو ينتظر المهمة/يلغيها؛ لا حفظ إجباري أو قتل inference للتحديث. |

اختبار ملكية `.desktop` في `tests/security/test_desktop_skills.py` صار يحدد المالك غير الموثوق صراحة بدل الاعتماد على UID الذي يشغّل pytest. أربع حالات owner/mode مستقلة تؤكد قبول root0644 ورفض non-root وgroup/world-writable. **لم يُضعف فحص الثقة الإنتاجي.** المجموعة الكاملة أُجريت كـ`foxlinux` على Python3.14؛ لم أكرر المجموعة كلها كـUID0 أو Python3.12.

## الرحلات الفعلية من المحادثة

| الطلب الدقيق | النتيجة المرصودة |
|---|---|
| `برمج لي لعبة XO` | مشروع `لعبة XO`، ملفا `game.py` و`index.html`، انتقال تلقائي خلال البث ثم مراجعة1. نُقرت خليتان في HTML فظهرت X وO. لم يُختبر الفوز/التعادل أو يُشغّل game.py. |
| `برمج لي موقع للcv` | مشروع `موقع السيرة الذاتية`، `index.html` محفوظ، معاينة فعلية، كود يسار ومعاينة يمين افتراضيًا. بيانات John Doe أمثلة مولدة وليست CV شخصية. |
| `أضف زر تسجيل دخول` | تعديل CV نفسه إلى مراجعة2؛ ظهر رابط `Login` مع `href="#"`. ليس تسجيل دخول حقيقيًا أو backend مصادقة. |
| `أضف الوضع الداكن إلى هذا المشروع` | CV نفسه إلى مراجعة3؛ التبديل غيّر خلفية body من `rgb(244,244,249)` إلى `rgb(51,51,51)`. لكنه استبدل رابط Login بـToggle Dark Mode وأبقى النص أسود؛ **فشل الحفاظ على السلوك والتباين** موثق، ولم أعد توليده للحصول على نجاح. |
| `برمج لي لعبة ثعبان باستخدام Python` | مشروع مستقل و`main.py` محفوظ، AST صالح، تعليمات Python دون معاينة ويب زائفة. لم أشغّل turtle أو اللعبة. |
| `اكتب لي كود Python لحساب المصروفات` | مشروع مستقل و`main.py` فيه `calculate_expenses`؛ حفظ وفحص ساكن، دون تشغيل. |

التسلسل الكامل وIDs والملفات والمراحل في `artifacts/composer-journeys.json` و`all-jobs.json` و`projects-saved.json`. job الأصلية لكل طلب واحدة؛ login/dark يعدلان project ID نفسه. أثناء XO عُدنا إلى المحادثة ثم الدرج مع استمرار التوليد. الحفظ/الفحص الناجحان لا يعنيان أن المولد استوفى كل شرط سلوكي.

أُجري تعديل يدوي مملوك للاختبار على عنوان CV إلى `Curriculum Vitae — QA saved revision`. بقي النص dirty بعد swap والعودة للمحادثة وإعادة الفتح، ثم صار revision4 عند الحفظ وتغيرت المعاينة فعليًا. الكاملة استخدمت URL نفسها. أعيدت `BackendService` فعلًا ثم أعيد فتح CV من الدرج؛ بقيت ملفات المشاريع الثمانية ومراجعاتها وتفضيل swap وسجل Neura. ليس هذا ادعاء استعادة unsaved draft بعد crash أو تجربة أيقونة KDE.

اختبار480px أعطى `scrollWidth=480` ومصدر LTR وتبويبي الكود/المعاينة قابلين للاستخدام؛ اختُبر1280px أيضًا. قد تبقى أثناء بدء مشروع جديد رسالة نجاح أو تسمية مراجعة من المشروع السابق حتى تتحدث الحالة؛ ظهر ذلك في صور التوليد. هذا قيد عرض باقٍ، منفصل عن F3 الذي يربط بايتات snapshot الصحيحة.

## ما تعمل عليه المزايا المكتملة في نطاقها المختبر

| IDs | المسار ومسار الطلب والبيانات | الدليل والحد |
|---|---|---|
| `N001 N003 N004 N005 N007 N008 N012 N014` | Qt/الويب → FastAPI/Pydantic → router → `NeuraLoop` → backend/template للوزن المختار. `capability_messages` تدمج system مع التاريخ؛ manager يحتفظ بنموذج كبير واحد، والإلغاء تعاوني حتى يعود native. | imports من target، GGUF محلي، تطابق routed/actual في tiers المختبرة، FAST/DAILY عربي/إنجليزي/مختلط، history QA742، SSE قبل النهاية، إلغاء حافظ على last-good واسترداد، overflow سياق مرفوض. لا قياس GPU أو إثبات provenance للناشر بمجرد hash محلي. |
| `N041 N043 N044 N049 N050 N051 N052` | `WorkspaceRequest/ProjectJobs/InvoiceOrchestrator/FileStream/ProjectStore` تحفظ الطلب والقيود والمراحل، تبث seq/job/project/draft، تتحقق من المسارات والتكرارات والمراجع والنحو ثم commit ومراجع ملفات. تخزين مستقل لكل stable ID. | ملفات النماذج الفعلية ولقطات التوليد؛ حالات HTML/CSS/JS/SVG والتجزئة والمراجع والصفر والمسارات الخبيثة في contract. fixture الأربع ملفات الحالي **مضبوط وليس ناتج نموذج**؛ الموقع الحقيقي الحالي يستعمل CSS/JS مضمنين. لا يُشغّل Python أو build. |
| `N053 N055 N056 N057 N060 N061 N062 N063 N098` | `workspace.js` يحتفظ بالمحرر والتفضيل في `/workspace/preferences`؛ drawer قرب composer، لا Projects/Skills دائمتين. `markdown.js` يهرب محتوى الدردشة. preview أصل منفصل وcapability وCSP وsandbox دون same-origin/Qt bridge. API الخاص يحمي token وHost/Origin. | UI فعلي وQt منفصلان، save/swap/reopen/full، وعزل browser embedded/full ضد parent/storage/bridge/tool/API/vault/private/metadata/beacon بآثار صفر. HTTP: missing token/Origin403 وHost400. هذا نطاق اختبارات محدد وليس ضمانًا ضد كل ثغرة. إعدادات إتاحة المهارات والأذونات بقيت في Settings. |
| `N058 N059` | `ProjectStore._canonical/get/summary/answer` تشتق الغرض واللغات والأدوار والentry/preview/validation/revisions من الملفات. قراءة metadata أو الحفظ تعيد hashes؛ لا watcher دائم. أسئلة التعريف/اللغات تمر دون نموذج؛ التعديل يقرأ الملفات الفعلية. | fixture عدائي اختبر تغيرًا بنفس الحجم وmtime وإضافة/حذف/rename وأصلًا مكسورًا، وعودة current بعد الإصلاح. عداد requests بقي8→8 في instance الاختبار نفسه. قياس tokenizer دون نموذج شمل30 سؤالًا: مشاريع QA المحفوظة، وfixtures عدائية، وكبيرة مضبوطة منفصلة. الملخص156–212 token، full24–14292؛ **الملخص قد يكون أغلى من مصدر صغير**. fixture الكبيرة4290–14292 مقابل165–181، وأسئلة metadata الحتمية نفسها0 model tokens. ليست هذه أرقام توفير لكل مشروع مستقبلي. |
| `N066 N068 N069 N072` | chat dispatch قبل LLM → `ApplicationTargets/DesktopSkills` → trusted GIO؛ URLs مرمزة للبحث العام/YouTube. history في `skill_history` بحد100 محاولة، API آخر50 وrecent آخر10 تطبيقات أطلقها Neura بنجاح. | سبع حالات API حقيقية، تشمل معرفة الاسم دون فتح وDiscord follow-up وBrave/YouTube، وsame-ID retry مطابق بلا تنفيذ جديد. history بقي بعد restart. فتح نتائج البحث ليس قراءتها أو تحققًا من محتواها؛ التاريخ يخص Neura فقط. نافذة Brave/Discord غير مرصودة، لذلك `N067 N071` غير مغلقين. |
| `N033 N104` | `ConversationVault` يحفظ session SQLite وCRUD؛ `SafeActions.draft_email` يرجع مسودة محلية فقط. | جلستان مستقلتان وقراءة من instance تخزين جديدة وحذف QA فقط؛ مسودة لعنوان `.invalid` دون إرسال. history المحادثات ليس long-term memory أو RAG. |
| `N023 N029 N099` | launcher وruntime وأصول محلية وCI/build موجودة؛ package reader وdecompressor يتحققان من المرشح. |102ملف runtime مطابق،55endpoint، بناء محلي، `pacman -Qip` و`zstd -t` exit0. CI YAML فُحص محليًا، ولم يُشغّل workflow بعيد. ليس تثبيتًا نظيفًا أو تحديثًا إداريًا أو قبول one-click على KDE. |

التفسير في الجدول يصف النطاق المكتمل؛ تفاصيل المسارات والدليل والأجزاء المتبقية لكل البنود الـ109 في المصفوفة. `N054` صار جزئيًا بسبب التراجع السلوكي الفعلي، رغم نجاح حراس الحفظ والتعارض والتعديل اليدوي.

## نتائج النموذج والرؤية الحالية

اختبار EXPERT الأصلي أبقي كما كان: `خطط لموقع سيرة ذاتية ثابت بثلاث خطوات مرقمة. بدون cloud وبدون تثبيت أي شيء.`، temperature0، max_tokens768، ومعيار ثلاث خطوات مكتملة. عاد HTML طويلًا و`finish_reason=length` بعد نحو94.69ثانية، ففشل. لم أرفع السقف أو أبدل معيار النجاح أو أكرر العينة. FAST/DAILY الستة نجحت في معاييرها المحددة، ولا يثبت ذلك جودة كل سؤال.

تجربة `plan=true` الجديدة مستقلة: أعاد EXPERT JSON بثلاث خطوات و`main.py` مع `stop`، ثم ولّد Coder `def add(a,b): return a+b` ومرّ AST. السجل يقول `behavioral_tests=not_run` و`executed=false`؛ عبارة Test في خطة النموذج لا تثبت أنه اختبر شيئًا.

المقارنة البصرية استعملت صور RGB64×64 معلنة في `artifacts/vision-fixtures/manifest.json` والنص نفسه، مرة واحدة لكل UI وAPI:

| الصورة | UI، temperature0.7 | API المطابق، temperature0.7 | تطابق native |
|---|---|---|---|
| red-blue | `الأحمر والأسود` — FAIL | `أحمر، أزرق` — PASS |9/9 |
| green-yellow | `أخضر، أصفر` — PASS | `أخضر، أصفر` — PASS |9/9 |
| black-white | `أسود، أبيض` — PASS | `أسود، أبيض` — PASS |9/9 |

المراقب `tests/fixtures/real_backend_trace.py` يسجل مدخل `backend.generate` الحقيقي، ويمرر المولد نفسه دون output مصطنع. المقارنة تفحص image hash، والرسائل كاملة بما فيها system، وeffective options بما فيها stream/max_tokens/temp/top_p، وmodel ID/path وprojector/device/context/template hash. التاريخ جديد `[system,user]`. لا seed ثابتًا في المسارين؛ عدم تطابق المخرجات مع تطابق المدخلات لا يثبت وحده خلل نقل أو فساد صورة. السبب الجذري لدقة اللون غير محسوم. نجاح API آخر عند temperature0 محفوظ منفصلًا ولا يحل محل إخفاق UI. هذا اختبار ألوان صغير وليس benchmark رؤية عامًا.

تأخر نقل ملف من file chooser وانتهت مهلة خدمة QA الأولى؛ أُعيد تشغيل خادم QA المملوك بعد انتهاء native فقط، مع حفظ `backend-history`. لم يُنفذ طلب الصورة على الخادم المنتهي، ولم يُحسب نجاحًا. جميع أزواج المقارنة الثلاثة أُجريت على instance نفسها، ثم أُجري restart منفصل للاستمرارية.

## أوامر التحقق والنتائج

الأوامر التالية تُنفذ من checkout وتدعم fish وbash. استبدل مساري `/absolute/...` بالهدف والجولة المسجلين أعلاه. `--allow-real-model` ليس محاكاة؛ يتطلب أوزانًا صالحة وغياب backend مستخدم آخر.

```sh
python tools/verify_neura.py --suite static --target-root /absolute/package/app
python tools/verify_neura.py --suite contract --target-root /absolute/package/app --resume /absolute/run
python tools/verify_neura.py --suite ui --target-root /absolute/package/app --resume /absolute/run
python tools/verify_neura.py --target-root /absolute/package/app --resume /absolute/run --serve real --allow-real-model --trace-real-model
```

بعد استقرار خدمة QA الوحيدة واختبارات composer، نفذ تسلسليًا من طرفية ثانية:

```sh
python tools/verify_neura.py --suite model --allow-real-model --target-root /absolute/package/app --resume /absolute/run
python tools/verification/review_cases.py --case required-plan --allow-real-model --target-root /absolute/package/app --run /absolute/run
python tools/verify_neura.py --suite model --model-case transport --allow-real-model --target-root /absolute/package/app --resume /absolute/run
python tools/verify_neura.py --suite desktop --allow-desktop --target-root /absolute/package/app --resume /absolute/run
```

أوامر vision-pair وإرفاق الملفات وتسلسل التوقف في `artifacts/REVIEW_047_VERIFICATION_AR.md`؛ أوامر الجولة الدقيقة محفوظة في `results.json::invocations/executions` ومدخلات `review_cases.py` وأكواد الخروج الفعلية في `artifacts/live-execution-ledger.json`. desktop suite تفتح التطبيقات/البحث عبر المحول الحقيقي ولا ترسل رسائل. لا تشغّل collectors متعددة تكتب `results.json` في الوقت نفسه.

| المستوى | النتيجة الحالية | الدليل |
|---|---|---|
| خط أساس F1–F3 على0.4.6 |13failed،6passed للـassertions المطلوبة قبل الإصلاح |`artifacts/baseline.xml` و`review-baseline-logs/baseline.txt` |
| خط أساس F4 على0.4.6 |4failed |`artifacts/review-baseline-logs/f4-baseline.txt` |
| targeted بعد الإصلاح |96passed، ثم42passed، ثم40passed بعد تنقيحات السباق؛ هذه جولات مختلفة لا تُجمع كأنها suite واحدة |السجلات الأصلية داخل `review-baseline-logs/` |
| المجموعة الكاملة على الهدف النهائي |**310passed،0failed،0skipped،13.87s** |`logs/contract.txt` و`artifacts/contract.xml`؛ نماذج/حساسات/desktop fake |
| Qt offscreen |14+30+15+6 = **65/65**، sandbox مفعّل |`qa_targets_workspace_qt` و`qa_chat_first_qt` و`qa_milestone_ui` و`qa_review_update_qt`؛ inference/desktop/admin fake |
| المصدر والحزمة |102مطابقة،55endpoint؛ build وmetadata وdecompression exit0 |`static.json` و`logs/package-*` و`build-047-final.txt` |
| نماذج فعلية | FAST/DAILY6/6؛ EXPERT FAIL؛ رؤية API0 PASS؛ Python والحفظ والإلغاء وhistory وcontext recovery PASS |`models.json/vision.json/python-project.json/native-cancel.json/multiturn-history.json/context-budget.json` |
| عقد خطة فعلي |PASS، خطة مكتملة وملف؛0retry،768token |`required-plan.json` |
| vision API/UI مطابق |2/3 أزواج نجحت، red-blue FAIL |`vision-pair-*.json` و`model-traces/*.json` والصور16–18 |
| HTTP والجلسات |20/20 checks |`packaged-extra-api.json`، دون نموذج/إرسال |
| metadata |PASS؛ عداد النموذج8→8، و30قياس tokenizer فقط |`metadata-probe.json/context-token-measurement.json` |
| GIO |7/7 سيناريوهات API؛ ليس رصد نافذة أو صفحة |`desktop.json`؛ لا عدد نوافذ مزعوم |
| restart |ملفات8مشاريع ومراجعاتها والتفضيل والسجل محفوظة |`restart.json/ui-restart-wide.json` |
| العزل |embedded/full محجوبان، beacon/history/grants بلا آثار |`browser-isolation*.json`؛ Qt منفصل أعلاه |

محاولات البيئة والتشخيص الفاشلة محفوظة: أول targeted تعذر عليه socket داخل sandbox، وبعض فحوص Qt الأولية كشفت marshal/timer/prepare-cancel races ثم أُصلحت وأُعيدت. لا تُسمى تلك المحاولات نجاحًا أو تُحذف. قبول الكتالوج يعيد1 بسبب الحالات الحقيقية الحالية؛ نجاح suite contract وحدها يعيد0 ولا يغيّر قبول الكتالوج.

## التخزين والحفاظ على البيانات

اختبارات هذه الجولة فقط تحت `/home/foxlinux/Documents/Codex/2026-10-27/files-mentioned-by-the-user-neura/outputs/NEURA_Review_Fixes_2026-10-30/20261030T150309_b1faac38/profile/`. `data/workspace/catalog.sqlite3` يحفظ jobs/events/preferences/history/permissions، ولكل مشروع مجلد مستقل و`.neura/project.json` و`summary.md` و`revisions/`. الملفات المولدة ونسخ المراجعات الصغيرة اللازمة للمراجعة مصدرة في `projects-saved.json`. ملف profile نفسه ورمز API والكاش والأوزان خارج ZIP الأدلة.

افتراضيًا بيانات المستخدم العادية في `~/.local/share/neura-ai/`، والمشاريع في `workspace/<name>-<id>/`، والجلسات في `conversations.sqlite3`، والإعدادات في `~/.config/neura-ai/settings.json`، والحالة في `~/.local/state/neura-ai/`. متغيرات XDG و`NEURA_*` قد تغير ذلك. الأوزان الحالية قُرئت من `/opt/neura-ai/models` فقط. لم تُنقل أو تُحذف ملفات Downloads أو المستخدم. أُغلقت خدمة QA المملوكة بعد انتهاء native والتبويب المؤقت، دون قتل تطبيقات المستخدم.

## ما بقي والأولويات

المصفوفة تضم109IDs فريدة: **40Implemented،32Partial،25Missing،10Deferred،2Superseded**. قُبل35ID في نطاقه المدعوم بعد مراجعة الأدلة المطلوبة؛ هذه ليست نسبة اكتمال المنتج ولا قبول كل الـ40Implemented. المصدر وحده لا يغلق قبول desktop/model/admin. حالات الباقي واضحة في `MATRIX.csv`؛ لا تُستبدل أعداد الاختبارات بمعاييرها.

| الأولوية | IDs | المشكلة الباقية | التنفيذ المقترح | الاعتماديات | معيار القبول |
|---|---|---|---|---|---|
| P1 | `N045 N054` | تعديل مولّد استبدل Login السابق؛ تباين الوضع الداكن ضعيف | حفظ متطلبات السلوك السابقة كعقد قابل للمراجعة، diff قبل اعتماد تعديل مولّد واختبارات DOM/تفاعل داخل الحد المعزول، repair محدود عند الإخفاق | مصدر المشروع الحالي، fixture Login+theme، sandbox للويب | إضافة theme تبقي Login ووظيفته، ويُظهر فشل الشرط بدل اعتماد صامت؛ last-good قابلة للاستعادة |
| P1 | `N006 N042` | EXPERT العام يفرط في الكود ويصل length | فحص template/roles/stop وأسلوب طلب خطة قصيرة مع fixture ثابت ومعيار مستقل؛ الإبقاء على سياسة fail-closed للمراحل المطلوبة | وزن/runtime محلي، مجموعة عربية/إنجليزية ثابتة | الطلب الأصلي يكمل3خطوات دون تغيير السقف أو معيار الاختبار بعد رؤية النتيجة |
| P1 | `N093` | إخفاق red-blue من UI رغم تطابق المدخلات | تشخيص projector/MTMD/preprocessing وsampling على مجموعة صور معلنة أوسع مع seed عند دعم runtime، مع حفظ عينات الفشل | runtime/weights/projector متوافقون، tracing الحالي | نتائج قابلة للتكرار على المجموعة دون hardcode أو retry انتقائي؛ لا إعلان نجاح رؤية عام من صورة واحدة |
| P1 | `N026 N024 N025` | معاملة التثبيت/التحديث الحقيقية غير مختبرة | تجربة على نظام/VM مستنسخ ومصرح، tamper/wrong-arch/hash/root-staging/auth-cancel/recovery وبيانات مستخدم اصطناعية | بيئة إدارية قابلة للاستعادة | يقبل الصحيح ويرفض المشوه ويحفظ البيانات والعمل؛ لا يُوقف backend قبل قرار الحماية |
| P2 | `N019 N020 N021 N064 N067 N070 N071` | لا رصد أصلي لأيقونة KDE والنوافذ وDPI | اختبار native Qt/KDE مرئي، فتح Brave/Discord/viewer وإعادة التركيز/الإغلاق | سطح desktop قابل للرصد | نافذة فعلية من الأيقونة ونتائج أدوات مرئية، دون خلط GIO بتحميل الصفحة |
| P2 | `N010 N011 N015 N016 N017 N018 N022 N108` | GPU/ضغط الذاكرة/تقسيم التوقيت/اللعب غير مقبولين فعليًا | قياسات اختيار الجهاز وVRAM والمراحل وحالة active-native والأخطاء | عتاد وتعريف مدعوم وتجارب مضبوطة | لا تفريغ نموذج نشط، قراءات فعلية وتحمل OOM واسترداد دون أرقام مصطنعة |
| P2 | `N065 N073 N077 N030 N031 N032 N097` | registry/دوبلكيت قديم/شرح مصدر/Doctor/style/diagnostics غير مكتملة | استكمال العقود المسجلة، ربط قراءة الملف عند الشرح، Doctor حديث لا يبدأ نموذجًا موازيًا، fixtures قابلة لإعادة التشغيل | البنية الحالية ومراجعة مسارات اختيارية | Unknown/disabled/forged تفشل، شرح دون مشروع زائد، فحوص حقيقية وأخطاء واضحة |
| P2 | `N034–N040 N109` | لا facts vault/RAG أوHarvest فعلي | تخزين موافقات ومصادر وإدارة حذف وفهرسة bounded ثم توليد من ملاحظات مختارة | موافقات ومصادر محلية | بقاء وحذف وتتبع مصدر دون رجوع معلومات محذوفة؛ endpoint501 الحالي ليس نجاحًا |
| P2 | `N080–N082` | لا تذكيرات دائمة/إشعارات/استكمال فيديو | CRUD معUTC/Asia/Riyadh وscheduler/delivery مقصود وروابط timestamps | خدمة مستخدم اختيارية لا تعمل خفية | restart/missed/duplicate delivery وروابط صحيحة؛ لا ادعاء closed-app دون خدمة مختبرة |
| P2 | `N085–N092 N094 N095` | STT/TTS غير جاهزين والـVAD/البث الصوتي غير متكامل | runtime وweights/voice متوافقة، تسجيل عربي وتشغيل مسموع وcancel/VAD/queue | Whisper/Piper وأجهزة/fixtures صوت | صوت عربي حقيقي، صمت وضجيج وإيقاف صحيح؛ وجود ملفات الأوزان لا يكفي |
| P3 | `N046–N048 N074–N079 N103` | لاsandbox برامج/وكلاء/بحث متعمق/تلخيص فيديو/تنظيم/MCP متكامل؛ Telegram يثبت8000 | تنفيذ مراحل bounded عبر الأدوات والسياقات القائمة، discovery محمي لقناةAPI | محركات عزل ومصادر/موصلات يختارها المستخدم | حدود وصلاحيات وإلغاء ومصادر فعلية؛ قناةTelegram اختبار مستقل دون رسائل غير مطلوبة |
| مؤجل | `N009 N027 N028 N083 N084 N096 N100 N101 N102 N105` | امتدادات مؤجلة صراحة | تبقى backlog منفصلًا، لا تفعيل تلقائي | قرار وبيئة كل امتداد | قبول خاص قبل إعلان التنفيذ |
| ملغى | `N106 N107` | غلافpywebview المكرر وصيانةWindowsF القديمة | لا يضافان إلى التطبيق | — | Superseded |

يمكنك الآن استعمال إنشاء المشاريع من الطلبات المحددة، ومشاهدة الكود والحفظ اليدوي والمعاينة الثابتة والتبديل والدرج وفهرس المشروع، ضمن المرشح المحلي المختبر. المهارات تستعمل المحول الحقيقي وتخبر بنتيجته، مع بقاء رصد النوافذ مفتوحًا. يعمل التعديل المولد جزئيًا ويحتاج مراجعة؛ التخطيط العام والرؤية غير مقبولين بالكامل. الذاكرة/RAG والتذكيرات والصوت والبحث والوكيل العام تبقى بحسب صفوفها، وليست جاهزة لأنها ذُكرت في خطة.

**المهام الثلاث التالية الموصى بها:** حماية السلوك أثناء تعديلات المشاريع `N045/N054`، ثم تشخيص EXPERT `N006/N042`، ثم معالجة الرؤية بتقييم ثابت `N093`. اختبار التحديث الإداري/native مستقل بعد توفير بيئة قابلة للاستعادة. لا يُنشر هذا المرشح لمجرد انتهاء التقرير.
