# مصفوفة المتطلبات الحالية — 0.4.5

تُقرأ مع `QA_v0.4.5_AR.md`. «مكتمل ومتحقق» يخص النطاق المذكور والبيئة المحددة، وليس اعتماد كل التطبيقات أو كل صياغة لغوية أو مخرجات النماذج. الدليل الآلي الحالي `final-acceptance.xml` (247)، وQt offscreen بموديل/محول وهمي `acceptance-qt-main` (30) و`acceptance-qt-extra` (15) و`acceptance-qt-targets` (14). التجربة الحقيقية منفصلة في `real-*.json` والصور؛ لا تعني الأرقام القديمة قبولًا حاليًا.

| Task ID | المتطلب | الحالة الحالية | مكان التنفيذ وكيف يعمل | طريقة الاختبار والدليل | الحدود / العمل المتبقي |
|---|---|---|---|---|---|
| N061 | إزالة Projects/Skills الدائمين | مكتمل ومتحقق | `web/index.html`, `workspace.js`, `skills.js`: chat/monitor/about؛ المساحة داخلية والمهارات في Settings | Qt main وواجهة CUA الفعلية؛ الصور 01–08 | لا يعاد إنشاء التبويبين |
| N062 | composer toolbar ودرج المشاريع | مكتمل ومتحقق | `index.html`: صورة/جلسات/زر مجلد مدمجة | Qt main/extra؛ image handler والجلسات والمجلد و360/600/1200 | اختيار الملف في Qt محاكاة معلنة |
| N063 | Markdown آمن | مكتمل ومتحقق | `markdown.js`: parsing محلي مع escape ومنع HTML الخام | renderer tests وQt main ضد script/img/iframe | البث نص escaped حتى اكتماله |
| N064 | RTL/تجاوب/keyboard | مكتمل ومتحقق في الأحجام المفحوصة | `workspace.css`, `input.css`, `index.html`؛ code LTR ومواضع مادية | Qt extra 360/600/1200، التركيز والأسهم وCode/Preview | ليس اعتماد كل قارئات الشاشة/compositors |
| N065 | سجل واحد ومخططات النتائج | مكتمل ومتحقق للمهارات السبع | `DesktopSkills.validate/execute`, `ChatDispatcher._skill` | الاختبارات الحالية للمدخلات/المخرجات/التعطيل/عدم التأكد | المهارات القديمة للبحث المنفصل ليست أوامر shell |
| N066 | أفعال عربية من المحادثة | مكتمل ومتحقق للصيغ المدعومة | `command_text`, `dispatch`, `resolve` قبل LLM | الصيغ الدقيقة والنفي والاقتباس؛ Qt targets؛ متابعة حقيقية Discord | لا parser لغوي مفتوح لكل عبارة مركبة |
| N071 | aliases وتطبيقات مثبتة | مكتمل ومتحقق للحل وقبول الإطلاق | `application_targets.resolve_application`, `DesktopAdapter.launch` إلى IDs موثوقة وGIO | exact aliases، relevant choices، failure tests؛ GIO حقيقي قبل Discord؛ الصورة08 | نافذة Discord غير مرصودة؛ لا تثبيت/أوامر عشوائية؛ entries غير الموثوقة غير مدعومة |
| N073 | متابعة، صلاحيات، سحب، dedup | مكتمل ومتحقق في النطاق المحدد | `TargetContext`, `chat_request_sessions`, `DesktopSkills.authorize/revoke`؛ TTL 300s | session/expiry/forged choice/retry/failure tests؛ محادثة4أدوار Qt؛ سؤال ثم متابعة GIO | حالة OS غير المؤكدة لا يعاد إطلاقها تلقائيًا؛ لا ضمان exactly-once خارجي |
| N067 | فتح موقع في Brave | منفذ ومتحقق آليًا؛ الاختبار المرئي الحقيقي لهذه الدفعة غير منفذ | `website_url`, `DesktopAdapter.browser`؛ HTTP/HTTPS، GIO argv | tests وQt main بمحول وهمي | لا ادعاء تحميل صفحة أو قراءتها؛ لا رحلة Brave حقيقية جديدة |
| N068 | بحث Brave مقابل البحث المسترجع | مكتمل ومتحقق لترميز URL | `chat_dispatch.resolve` إلى `search_web`؛ `SafeActions.search_web` مسار منفصل | اختبارات عربية/إنجليزية للـURL | فتح results ليس retrieval أو verification؛ provider الخارجي لم يختبر حيًا هنا |
| N069 | بحث YouTube | مكتمل ومتحقق لترميز URL والفشل الناقص | `DesktopSkills` و`chat_dispatch` | URI عربي/مختلط وempty، Qt main | لا قراءة فيديو أو transcript |
| N070 | ملفات ومجلدات معتمدة | مكتمل ومتحقق آليًا | `SafeTree`, `DesktopAdapter.file/folder`, `approved_locations` | traversal/symlink/missing/executable/ambiguity وQt main | إطلاق ملف حقيقي جديد في سطح المكتب لم يجر بهذه الدفعة |
| N072 | التطبيقات الحديثة | مكتمل ومتحقق ضمن سجل Neura | `DesktopSkills.history/recent` في catalog SQLite | restart tests، history في `real-final.json` يحتوي إطلاق Discord الحقيقي بعد إعادة التشغيل | آخر التطبيقات التي أطلقها Neura فقط؛ ليس تاريخ KDE/Brave الشامل |
| N098 | حماية APIs والـbridge | مكتمل ومتحقق ضمن عينات الهجوم | `api.py` auth/Host/Origin، `preview_policy.py` وpreview server | security tests وQt العدائي في main/extra | ليس تدقيق اختراق شامل؛ لا محتوى مولد يمنح إذنًا |
| N041 | Task Invoice ومراجع الملفات | مكتمل ومتحقق للعقد الحالي | `ProjectRequest/TaskInvoice`, `ProjectJobs`، requirement/context/stages/saved refs | fixtures و`real-final.json`: مراجع immutable تطابق snapshots | السجلات القديمة لا تحصل فاتورة مختلقة |
| N042 | تخطيط عند الحاجة | منفذ جزئيًا | `InvoiceOrchestrator.stream_files(plan=...)`، شرح يبقى chat والموقع البسيط يتجاوز planning | exact creation/explain tests؛ CV حقيقي دون دورة4نماذج | تصنيف تعقيد عام وتحسينه بقياسات غير مكتمل |
| N043 | أسماء وروابط ملفات صحيحة | مكتمل ومتحقق للقواعد المحدودة | `FileStream._filename/_referenced_files`، hints اختيارية وprovenance | لغة بلا اسم/fragmentation/ambiguous/unsafe/3files مترابطة؛ CV حقيقي index.html | لا تخمين عند غياب مرشح وحيد؛ فشل العقد الأول محفوظ |
| N044 | فحص ساكن للمخرج | مكتمل ومتحقق للحدود المعلنة | `inspect_files`, `SafeTree`, `commit`، صياغة ومراجع وأحجام | invalid/empty/duplicate/traversal/Python/JSON/JS/CSS؛ Qt failures | النجاح السلوكي منفصل؛ أول تعديل blue الحقيقي يثبت هذا الحد |
| N045 | مراجعة وإصلاح | منفذ جزئيًا | legacy `InvoiceOrchestrator.process_request` verdict صريح ومحاولة محدودة؛ workspace يعتمد static validation | NEEDS_FIX وzero-files tests؛ فشل blue الأول وحفظه | لا دورة إصلاح/تحقق سلوكي كاملة للـworkspace المبثوث |
| N049 | إنشاء مشروع من الطلب نفسه | مكتمل ومتحقق للطلب الحرفي | `project_intent`, `jobs.create`, `acceptCreated`؛ الطلب الأصلي محفوظ | الأربع صيغ fake؛ CV حرفي real CPU، الصور01/02/03 | لا ضمان جودة كل محتوى مولد؛ CV الناتج الإنجليزي يستخدم بيانات عينة |
| N050 | مشروعات منفصلة ومراجعات | مكتمل ومتحقق | IDs مستقرة ومجلدات user-data، Atomic writes وsnapshots | collisions/restart/rollback tests؛ إعادة فتح المشروع الحقيقي revision5 | QA محفوظ منفصلًا؛ لا ترحيل بيانات إنتاج بهذه الدفعة |
| N052 | أحداث حقيقية وترتيب/استعادة/إلغاء | مكتمل ومتحقق للنقل؛ الإلغاء الحقيقي غير مجرب هنا | `ProjectJobs._emit/events`, `NeuraSSEDecoder/watchJob`، queue bounded | fragments/reconnect/dedup/cancel-later fake؛ real jobs event sequences contiguous | cancellation بالنموذج الحقيقي/GPU يحتاج تجربة منفصلة |
| N051 | Code LEFT / Preview RIGHT | مكتمل ومتحقق | `workspace.css`, `openProject/selectFile/refreshPreview` | geometry Qt وCUA؛ صورة03 وموقع حقيقي | Python fixture يُعرض ولا ينفّذ؛ لا Python real جديد هنا |
| N053 | تبديل الجانبين | مكتمل ومتحقق | `S.prefs`, `/workspace/preferences` | نص وselected file قبل/بعد متطابقان؛ الصورة04؛ restart07 | غير المحفوظ يبقى أثناء view switch؛ ليس autosave دائمًا |
| N054 | تحرير وحفظ وتعارض | مكتمل ومتحقق | `save()`, expected_revision/hash، dirty/leave، atomic commit | Qt real API conflict وsave-race؛ حفظ CSS حقيقي revision2 وصورة06 | اختيار ترك المسودة يفقد غير المحفوظ عمدًا؛ لا اختبارات تحرير كل أنواع binary |
| N055 | معاينة static فعلية | مكتمل ومتحقق | `project_preview.py`, `refreshPreview()`، snapshot بعد commit | HTML/CSS real، JS button fixture؛ saved CSS computed color | لا تشغيل React/TSX/server/build/deps تلقائيًا |
| N056 | معاينة كاملة | مكتمل ومتحقق | dialog iframe بنفس capability URL/mراجعة | Qt sandbox tests وCUA نفسURL؛ الصورة05 | static eligible assets فقط |
| N057 | عزل المعاينة | مكتمل ومتحقق ضمن اختبارات التهديد المذكورة | منفذ منفصل+opaque sandbox+CSP+Qt request policy | browser/Qt paths، main/extra security fixtures | لا ضمان لعزل برنامج أصلي؛ هذا preview web فقط |
| N060 | إعادة الفتح من المجلد | مكتمل ومتحقق | `openDrawer/listProjects/openProject` | QA restart فعلي وQt؛ الصورة07 | لا permanent Projects tab |
| N058 | metadata/summary واقعي ومحدود | مكتمل ومتحقق ضمن العينات | `source_observations`, `ProjectStore.summary/answer`، ميزات مرصودة provenance | static features tests وmetadata سؤال حقيقي دون LLM | facts ليست وصفًا سلوكيًا؛ حد حروف لا حد tokens عالمي |
| N059 | كشف stale وقراءة المصدر | مكتمل ومتحقق للخلل المحدد | `get()` hashes حتى same-size/mtime، `rebuild()`, `context()`, question refresh | fixture+Qt dirty-preserved؛ real QA John→Jane بنفسالحجم/mtime، stale ثم revision5/current دون LLM | لا watcher دائم؛ الفحص عند حدود القراءة/الحفظ؛ المصدر ضروري للتعديل |
| N008 | Coder متاح فعلًا | منفذ جزئيًا مع دليل حقيقي | availability + llama.cpp backend | CV وتعديل حقيقيان من GGUF المكتمل | تدقيق provenance وتحميل كل النماذج ليسا مكتملين |
| N011 / N018 | scheduler/VRAM | منفذ جزئيًا | `NeuraLoop.exclusive/_load`, ResidencyManager، single-large-model policy | fake load-once/cancel/contention/memory tests؛ real CPU فقط | لا قياس GPU/OOM/warm improvement جديد؛ تقديرات VRAM معلنة |
| N013 / N016 | deadlines/Gaming | منفذ جزئيًا | cancel/deadline/native stop criteria و`_on_game` lock | unit tests الحالية؛ لم يُختبر كشف لعبة/تفريغ GPU فعلي | retries/timeouts والناتج الأصلي المتأخر تحتاج فحص بيئة GPU |
| N034–N040 | ذاكرة شخصية/RAG | غير منفذ كرحلة إنتاج مكتملة | `ConversationVault` يحفظ جلسات؛ `memory.py` قديم غير موصول بالواجهة الحالية | source inspection وCRUD sessions tests | لا preference approval/index invalidation/RAG citations/persona caching مثبت |
| N109 | Vault Harvest | غير منفذ | `/vault/harvest` يعيد501 صريحًا | فحص المصدر | يتطلب ملاحظات مختارة وتوليد حقيقي ومراجع |
| N080–N082 | تذكيرات/إشعارات/فيديو continuation | غير منفذ | لا خدمة reminders متكاملة في backend الحالي | source inspection | UTC/Asia Riyadh/storage/scheduler/delivery/provider permissions |
| N085 / N087 / N088 | STT/TTS/Kokoro | منفذ جزئيًا؛ غير متاح في QA | `VoiceService` يتحقق من CLI/weights/config؛ لا fallback سحابي | health/capabilities؛ لا تسجيل أو صوت حقيقي | لم يُختبر تفريغ عربي أو Piper مسموع؛ weights وحدها ليست جاهزية |
| N086 / N089–N092 | VAD/تقييم/stream/dictation/activation | غير منفذ كحزمة مكتملة | بعض عناصر واجهة، دون الرحلات المطلوبة | source inspection | fixtures صوتية، worker/cancel/input portal وموافقة activation |
| N093 | Vision | منفذ لكن غير متحقق بصورة حقيقية بهذه الدفعة | mtmd adapter/model+projector، schemas image | fake adapter/schema tests فقط | اختبار صورة حقيقية عبر الحزمة والموارد مطلوب |
| N094 / N095 | Orb/HUD | منفذ جزئيًا | frontend visual states/monitoring | UI transitions/sensor tests الحالية | listening/speaking الحقيقيان ومزامنة الصوت غير مثبتين |
| N025 | one-click startup/package | منفذ جزئيًا مع تشغيل حزمة مستخرجة | desktop entry/launcher/MainWindow/service؛ لا كود مطلوب للمستخدم المثبت | build metadata/zstd/102matches/QA restart | installed0.4.4 مختلف؛ لا clean install/admin update جديد؛ Qt visible native لم يُختبر |
| N026 | updater/dirty/active jobs | منفذ جزئيًا | releases SHA/size/repo/identity، root staging، polkit | release/download/helper unit tests | `UpdateDialog.downloaded()` يوقف backend قبل dirty/job gate؛ اختبار إداري فعلي غير منفذ؛ الإصدار المحلي غير منشور |
| N030 | docs/Doctor | منفذ جزئيًا | README وAPI guides والتقرير الحالي؛ أدوات diagnose | مراجعة المسارات والنتائج الحالية | لا عدد Doctor مختلق؛ التشخيص الكامل لكل hardware غير مكتمل |
| N103 | Telegram | منفذ جزئيًا | client API، allowlist، bounded history؛ لا نموذج ثانٍ | tests وقراءة `telegram_gateway.py` | مثبت علىport8000؛ dynamic discovery/identity/stale state غير منفذ؛ لم تُرسل رسائل حية |
| N074–N079 / N046–N048 | مهارات/بحث/وكيل إضافي | منفذ جزئيًا أو غير منفذ حسب الرحلة | SafeActions search provider/email draft؛ legacy modules ليست سيرًا مكتملًا | tests للمسارات المتاحة؛ source inspection للباقي | لا calculator/time/weather/transcript/deep research/MCP/organizer/sandbox تنفيذ كامل مُثبت؛ لا host execution |
| N077 | شرح الكود | منفذ ومتحقق للمحادثة العادية | الشرح لا يصنع مشروعًا؛ metadata يطلب actual source عند الحاجة | test «اشرح هذا الكود» وQt targets | لم تُختبر جودة شرح بالنموذج الحقيقي هنا |
| N097 | تقييم قابل للتكرار | منفذ جزئيًا مع أدلة جديدة | regression fixtures وQA tools/environment manifests | exact inputs/results محفوظة؛ 247+59 وreal failures/success | فشل عابر قديم غير معاد الإنتاج؛ evalsuite كلاللغات/الأداء لم يكتمل |

لا تُغلق بقية P5–P10 تلقائيًا بهذه المصفوفة. تبقى N002/N006/N015/N017/N022/N031/N032/N108 وغيرها للتحقق/الإكمال حسب `REMAINING_TRACKER.json`؛ لم تُختبر كل معاييرها هنا.

المؤجلة منفصلة دون تفعيل: **N009, N027, N028, N083, N084, N096, N100, N101, N102, N105**. الملغية: **N106, N107**. النشر في AUR يحتاج حسابًا وتفويضًا لاحقًا؛ لا نعد الأمر `paru -S neura-ai-bin` متاحًا للجميع لمجرد وجود PKGBUILD.

## الأولويات المتبقية

| Priority | Task ID | المشكلة | التنفيذ المقترح | الاعتماد | معيار القبول |
|---|---|---|---|---|---|
| P0 | N026 | التحديث قد يوقف مهمة أو يترك dirty دون مراجعة | dirty/job gate قبل تنزيل/إيقاف backend؛ فشل يعيد الاتصال؛ اختبار ترقية واسترجاع | VM/تثبيت QA وصلاحية إدارية مقصودة | refusal يبقي العمل، success يحفظ البيانات، tampered package مرفوض |
| P1 | N045 / N097 | static pass لا يضمن اللون/سلوك الطلب؛ أول blue فشل | نتائج validate واضحة؛ إصلاح محدود بمخرجات تشخيص موثوقة، وفحص سلوكي اختياري معزول | fixtures ومراجعةالمستخدم، لا تنفيذ host | failed semantic case لا يُعلن طلبًا ناجحًا؛ retries محدودة وتحفظ آخرrevision |
| P1 | N025 / N071 | لا تحقق مرئي لنافذة Qt/Discord | تشغيل desktop QA على سطح KDE المتاح وملاحظة النافذة | تحكم native غير متاح لهذه الجلسة | request accepted وwindow observed موثقان منفصلين |
| P1 | N013 / N052 / N018 | native cancel/GPU/OOM غير مجرب بهذه الدفعة | تجربة bounded cancel ثم طلب آخر، قياسات queue/load/generation مستقلة | GPU خالٍ وملف QA | لا premature unload، تعافٍ ونتائجحقيقية |
| P2 | N103 | Telegram يرفض dynamic port | اكتشاف محلي محمي والتحقق منinstance/auth/staleness | contract tests، botlive لاحقًا فقط بتفويض | لا fixed-port ولا نموذج ثانٍ؛ disconnected fails clearly |
| P2 | N085–N093 | نقص جاهزية/تحقق صوت وصورة | engines/weights compatible ثم fixture عربي وصورة حقيقية | أوزان ومحركات مناسبة، إذن ميكروفون عندالطلب | أدلة صوت/صورة محلية حقيقية مع إلغاء وفشل صريح |
| P3 | N034–N040 / N080–N082 | الذاكرة والتذكيرات ليست مكتملة | approved facts/index deletion وUTC scheduler | تصميم storage/permissions وtests | restart/delete/provenance/notifications حقيقية |

يمكن استخدام الأفعال المدعومة والمشاريع الثابتة والتحرير والحفظ وإعادة الفتح من المرشح المحلي. جودة التوليد العام، التحديث الإداري الآمن، الصوت/الذاكرة/التذكيرات/RAG والقناة الديناميكية ليست كاملة. أفضل الخطوات الثلاث التالية: **N026** لحماية العمل عند التحديث، **N045/N097** للفحص والإصلاح السلوكي المحدود، ثم **N025/N071** للتحقق الأصلي المرئي من الحزمة وDiscord.
