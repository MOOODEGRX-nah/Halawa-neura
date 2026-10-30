# تحقق Neura الحالي — 2026-10-30

**القبول الكلي: `FAILED`، وكود الخروج `1`.** رحلة Discord ورحلة إنشاء مشروع CV تعملان في النطاق المختبر. بقي إخفاقان حقيقيان في الجودة: EXPERT لم يكمل خطة من ثلاث خطوات قبل حد الرموز، والرؤية من واجهة المحادثة أخطأت في لون الصورة. توجد أيضًا بنود ناقصة ومحجوبة وغير مختبرة؛ هذه ليست شهادة اكتمال التطبيق أو البنود الـ109.

الجولة المرجعية `20261030T031544_8c45f37a`. تُسلّم معها `ACCEPTANCE_AR.md` و`REPORT_AR.md` و`results.json` و`MATRIX.csv` و`verification-evidence.zip`، وفيه الصور والسجلات وملفات مشاريع QA الصغيرة. المسارات التي تبدأ بـ`artifacts/` و`logs/` و`screenshots/` أدناه تقع داخل حزمة الأدلة، وليست خدمات على الإنترنت. [مصفوفة المصدر](VERIFICATION_MATRIX_2026-10-30.csv) و[كتالوج المعايير](../tools/verification/catalog.json) و[دليل تشغيل الفاحص](VERIFY_NEURA_AR.md) محفوظة في المستودع. التقارير الأقدم باقية بأسمائها التاريخية.

## النسخة والبيئة وحدود الإثبات

| الحقل | ما اختُبر فعلًا |
|---|---|
| checkout | `/home/foxlinux/Documents/Codex/2026-10-27/files-mentioned-by-the-user-neura/work/neura-workspace-v2` |
| branch | `verify/full-catalog-20261030` |
| commit عند بدء العمل | `0ed6f6dfedc07b6ae194d3966dcd65ff7ad975ed`؛ بُني المرشح من هذا الأساس مع التعديلات المحلية المسجلة |
| مصدر المرشح | `VERSION=0.4.6`؛ هوية git النهائية والتغييرات قبل/بعد موجودة في `results.json` |
| المثبت على الجهاز | `neura-ai-bin 0.4.5-1`، من `/opt/neura-ai/app`؛ لم أستبدله تلقائيًا |
| الهدف النهائي | `work/verification-046-final-package/opt/neura-ai/app`، مستخرج من حزمة `0.4.6-1` المحلية |
| runtime SHA256 | `15f132b1357d5592d3fffbd0f055cc002d35af1baeb4d39134333f5a35e25004` |
| النظام | CachyOS، `Linux 7.3.0-4-cachyos`، KDE/Wayland، x86_64 |
| Python | `/usr/bin/python`، `3.14.8`؛ vendor الخاص بالحزمة، دون تثبيت اعتماديات جديدة |
| الاعتماديات المقاسة | PySide6 `6.12.0`، llama-cpp-python `0.3.36`، FastAPI `0.151.0`، Pydantic `2.12.5`، pytest `9.2.0` |
| ملف QA | مجلد `profile/` داخل الجولة، ببيانات وإعدادات وحالة مستقلة وملف ملكية |
| الاستدلال | CPU صراحة، `n_ctx=4096`، `dedicated_coder=True`، المنسق الموجود نفسه، دون استدلال سحابي |
| الواجهة الحقيقية | أصول الحزمة الفعلية في IAB، متصلة بـBackendService الحقيقي؛ ليست نافذة Qt الأصلية المرئية |
| Qt | ثلاثة فحوص offscreen، بنموذج ومحولات وحساسات fake معلنة، **sandbox مفعّل**، دون `--no-sandbox` |
| سطح المكتب | GIO الحقيقي قبل طلبات الفتح؛ لم تتوفر أداة رصد نوافذ KDE الأصلية، لذلك ظهور النافذة `BLOCKED` |
| الإدارة والنشر | لا pacman/Polkit transaction، ولا push أو GitHub release أو رسالة Telegram/بريد |

قبل الاستدلال الحقيقي أُتيحت نافذة اختبار بعد إغلاق نسخة المستخدم. فُحص عدم وجود backend آخر، ثم بدأت خدمة QA وحدها. تغير منفذها من `39375` إلى `45097` عند اختبار إعادة التشغيل، مع تغير `instance_id`؛ لم يُفترض منفذ8000 ولم تُطبع مفاتيح المصادقة. التنفيذ الحقيقي مرّ عبر `BackendService` و`NeuraLoop` الحاليين، لا خادم نموذج موازٍ.

قراءة sysfs و`lspci` أظهرت RX9060XT/Navi44 عند PCI `03:00.0` و`card1`، وبطاقة Polaris عند `07:00.0` و`card0`. إذن card0 لا يعني تلقائيًا البطاقة الرئيسية. هذه قراءة هوية وذاكرة فقط؛ لم أُجر اختبار توليد Vulkan أو تحقق اختيار GPU الفعلي. لا يجوز تحويل نتائج CPU إلى أرقام أداء RX9060XT.

## ما تغير وما أعيد استخدامه

أضفت `tools/verify_neura.py` و`tools/verification/`، وكتالوجًا فيه **109 IDs فريدة**، وفحوص أمان وحساب نتائج في `tests/regression/test_verification_runner.py`. أضفت حواجز imports حتى يستعمل فحص الحزمة `src` من الهدف المختار، وعزلت الحساسات والعمليات في fixtures حتى لا تقرأ الاختبارات المضبوطة VRAM حقيقية أو تهيئ Vulkan أثناء اللعب. `tools/verification/probes.py` يفحص metadata وعزل المتصفح وHTTP على ملف QA نفسه. أُصلح تصنيف المشاريع المضبوطة في أداة قياس السياق حتى لا تُحسب كأنها ناتجة من نموذج.

**الإصلاح التشغيلي الجديد `N005`:** تجربة حقيقية على0.4.5 أعادت502 برسالة `Conversation roles must alternate user/assistant/user/assistant/...`. كانت مقدمة قدرات الخادم تُضاف كرسالة system منفصلة قبل system أرسلها العميل. المحاكي لم يكشف قيد قالب Gemma3. الدالة الجديدة `src/backend/api.py::capability_messages()` تدمج المقدمة ورسائل النظام الأولى في system واحدة، وتبقي بقية user/assistant والصور، ثم تستخدم قالب GGUF الفعلي. فُصل وصف مهارات الجهاز عن القدرة على كتابة الشرح والخطط والكود. في0.4.6 أعاد اختبار الإنجليزية ثم العربية الرمز **`QA742`** كما طُلب. الدليل القديم502 محفوظ داخل `artifacts/baseline-045/`، والنجاح الحالي في `artifacts/multiturn-history.json`.

**Discord وCV لم أفترض أنهما ما زالا معطّلين.** الإصلاح الموجود في commit `1523f8f` كان حاضرًا في0.4.5. أعاد الفحص الحالي إنتاج رحلة نجاحهما، فأبقيت المعالجة القائمة ولم أنشئ dispatcher أو workspace بديلًا. لا تسمح الصورة التاريخية وحدها بنسب إخفاق النسخة القديمة إلى فرع بعينه في المصدر الحالي.

| المسار | كيف يعمل الآن | الدليل والحد |
|---|---|---|
| `N065 N066 N071 N073` | `ApplicationTargets` يطبع الأسماء العربية والإنجليزية ويطابق aliases بتطبيق موثوق. `ChatDispatcher.dispatch/choose/manual` يربط الطلب الصريح بسياق جلسة محدود وسجل request IDs. الرد الناجح يمنع fallback العادي لنفس الطلب. | تسلسل composer الكامل: «هل يمكنك ان تفتح ديسكورد» ثم المعرفة بالاسم ثم «هذا هوا افتحه» ثم الاسم الإنجليزي. ثلاثة طلبات فتح مقصودة قبلها GIO؛ سؤال المعرفة لم يفتح. `desktop.json` وصورة08؛ النافذة غير مرصودة. |
| `N041 N049 N052` | `web/chat.js::handleChat()` يستدعي dispatch قبل inference عام. النص الأصلي ينشئ ProjectJobs job واحدة وproject مستقلة؛ `NeuraWorkspace.openProject()` ينتقل قبل اكتمال التوليد ويقرأ draft/events. | الطلب **«برمج لي موقع للcv»** أنشأ project `p_7793eb5400c04f2aae7bda6da8724ec2`، ومهمته الأصلية محفوظة في `cv-job.json`. الصورتان01و02 تعرضان الطلب والتوليد الجاري. |
| `N003 N004 N005 N012 N014` | FastAPI وPydantic يتحققان من العقد؛ NeuraLoop.select يختار النموذج، وstream يرسل chunks من المولد الحقيقي بهوية ثابتة. اختبارات العقود تستخدم fixtures منفصلة. | تطابق routed/actual لكل tier المختبر؛ `native-transport.json` يثبت أول جزء قبل النهاية و`stop` و`[DONE]`. إخفاق الجودة ليس تلقائيًا إخفاق توجيه أو نقل. |
| `N007 N008` | `ResidencyManager.availability` يفحص الأوزان وmarkers، وllama_cpp_backend يحمّل الملف المختار. | سبعة GGUF فُحصت metadata وبصماتها المحلية. Coder الاختياري المكتمل ولّد CV وPython فعلًا؛ upstream provenance ليست مثبتة بالبصمة المحلية وحدها. |
| `N043 N044` | `FileStream.feed/finish` يحفظ الأسماء المعروفة من output/references؛ `inspect_files` و`source_syntax` يفحصان المسارات والملفات المطلوبة والحدود والمراجع والنحو. | مشروع ثانٍ ولّد `index.html/style.css/script.js/logo.svg` بروابط صحيحة. حالات الصفر والتكرار/traversal/symlink/الحدود والنحو والتجزئة في tests. لا مساواة بين الفحص الساكن واختبار برنامج Python سلوكيًا. |
| `N050 N054` | `ProjectStore.create/commit/save_file/_recover` يفصل الاسم عن ID ويحفظ manifest وrevisions؛ expected_revision/sha256 يرفضان الكاتب القديم. المحرر يحتفظ بـdirty عند تعارض أو حفظ متأخر. | حفظ حقيقي إلى مراجعة2 غيّر المعاينة. فحوص Qt المضبوطة تغطي التأخير والتعارض والنص المحلي. إلغاء native edit أبقى آخر revision/bits صالحة، ثم نجح طلب تالٍ. |
| `N051 N053 N060` | workspace يحكم المواضع الفيزيائية داخل RTL؛ preference في `/workspace/preferences` داخل SQLite. درج المجلد يعيد المشاريع دون صفحة Projects دائمة. | الكود x195 يسار والمعاينة x737 يمين عند1280px. بعد swap صارا737/195؛ أُعيد تشغيل BackendService فعليًا وأُعيد فتح CV وبقيت الملفات والمراجعة5 والترتيب. لا ادعاء باستعادة unsaved draft بعد انهيار التطبيق. |
| `N055 N056` | `PreviewServer.issue/serve` يخدم snapshot static مؤهلًا. full-page يستعمل URL/revision نفسها في iframe معزول. | صورة05؛ شعار محلي naturalWidth50؛ الضغط على `Click Me` غيّر النص إلى «مرحبا!». Python وReact/TSX/server لا يملكون معاينة static وهمية ولا يُبنى المشروع تلقائيًا. |
| `N057 N098` | أصل معاينة منفصل، capability للsnapshot، manifest assets، CSP، `sandbox=allow-scripts` دون same-origin أو native bridge. API الخاص يفحص token وHost/Origin وحجم الجسم. | Qt offscreen وIAB اختبرا كلًا على حدة. المضمنة والكاملة حجبتا parent/storage/bridge/tool/API/vault/metadata/private وbeacon محليًا مملوكًا؛ history/grants وbeacon بلا آثار. اختبار auth الفعلي رفض missing token/Origin بـ403 وHost بـ400. ليس برهانًا ضد كل ثغرة مستقبلية. |
| `N058 N059` | `_canonical/get/summary/_derived/answer` تبني فهرسًا من الملفات المحفوظة، لا من تخمين النموذج. قراءة metadata أو حدود الحفظ تعيد hashes؛ السؤال البسيط لا يستدعي inference. سياق التعديل يقرأ الملفات الفعلية المختارة. | نفس-size/mtime تغير كشف stale؛ الإضافة والحذف أعادا اللغات؛ نقل logo كشف مرجعًا مكسورًا ورفض reindex؛ أُعيد logo وصار current. عداد requests بقي19→19. المصدر يُقرأ من القرص للتحقق؛ لا ادعاء بتجنب كل disk reads أو وجود watcher دائم. |
| `N061 N062 N063 N064` | nav: المحادثة/المراقبة/حول؛ الصورة والجلسات والمجلد في toolbar قرب composer؛ Markdown مهرب وروابط مقيدة؛ code LTR والتحكم RTL مع تبويبي عرض ضيقين. | DOM الحقيقي وQt يثبتان غياب Projects/Skills. 480px أعطت scrollWidth480 وتبويبَي الكود والمعاينة usable، و1280px لوحين. `N061/N062` أبقيا placeholder فحص contract مستقل غير منفذ في matrix رغم نجاح UI؛ لا يُغلق بالاستنتاج. native DPI/accessibility الكامل غير مختبر. |
| `N067 N068 N069 N070 N072` | `DesktopAdapter.browser/launch/open_file/open_folder` يمرر وسائط منظمة إلى GIO؛ البحث يرمز query إلى Brave أو YouTube. recent من `skill_history` الخاص بالتطبيق. | ستة طلبات فتح فعلية في desktop suite وسؤال معرفة، مع same-ID retry يعيد النتيجة؛ فتح ملف/مجلد QA قبلتهما GIO. history بقي بعد restart. لا إثبات تحميل صفحة أو قراءة بحث أو مشاهدة نافذة. |
| `N033` | `ConversationVault.save/get/list/delete` يحفظ history في SQLite. | CRUD وعزل جلستين وقراءة من instance تخزين جديدة وحذف جلسات QA فقط؛ Qt يغطي restart. ليس facts vault أو RAG أو persona memory. |
| `N001 N023 N029 N099` | Linux entry points والأصول المحلية وVERSION وCI/build الحالية فُحصت؛ المقارنة مع runtime المستخرج منفصلة عن تثبيت النظام. | 102ملفًا مطابقًا، منها launcher/version/license. `makepkg` نجح محليًا و`zstd -t` نجح للحزمتين و`pacman -Qip` طابق0.4.6-1/x86_64. CI YAML صالح؛ لم يُشغّل workflow بعيدًا. |
| `N104` | `SafeActions.draft_email` يتحقق من العنوان ويعيد object محليًا فقط. | مسودة إلى `qa@example.invalid`؛ لا إرسال بريد أو SMTP. |

## الملفات والنماذج والقياسات

بيانات الاستخدام العادية خارج ملفات التثبيت: `/home/foxlinux/.local/share/neura-ai/workspace/catalog.sqlite3` للمشاريع والتفضيلات والjobs/events/permissions، ولكل مشروع directory مستقل بملفاته و`.neura/project.json` و`.neura/summary.md` و`.neura/revisions/`. المحادثات في `/home/foxlinux/.local/share/neura-ai/conversations.sqlite3`؛ إعدادات desktop في `/home/foxlinux/.config/neura-ai/settings.json`، والحالة في `/home/foxlinux/.local/state/neura-ai/`. يمكن أن تغيّر XDG أو متغيرات `NEURA_*` هذه الافتراضات. لم أعدل بيانات المستخدم الأصلية ولم أحذف مجلد Downloads.

في هذه الجولة استُعمل بدلًا منها `outputs/NEURA_Verification_2026-10-30/20261030T031544_8c45f37a/profile/{data,config,state}`. ملفات QA الفعلية محفوظة داخل `profile/data/workspace/`، ونسخ صغيرة قابلة للمراجعة دون credentials في `artifacts/qa-projects/`. مشروع CV الأصلي مراجعة5، ومشروع الملفات الأربعة مراجعة7 بعد فحوص freshness، وPython مراجعة1 بعد إلغاء تعديل. هذه الأرقام لا تعني عدد المشاريع الحقيقية عند المستخدم.

| الاستخدام | الملف الحالي | ما ثبت |
|---|---|---|
| FAST | `/opt/neura-ai/models/gemma-4-E4B-Q4_K_M.gguf` | metadata الفعلية `gemma3 / Gemma-3-4B-It`؛ الاسم المحلي ليس إثبات Gemma4. عربية/إنجليزية/مختلط نجحت. |
| DAILY | `/opt/neura-ai/models/Qwen3.5-9B-Q4_K_M.gguf` | ثلاثة طلبات موضوعية نجحت. |
| EXPERT/CODER الافتراضي المشترك | `/opt/neura-ai/models/Qwen3.5-9B-Claude-Distilled-Q4_K_M.gguf` | community local Qwen35؛ ليس Claude سحابيًا. التخطيط فشل ضمن الاختبار المبين. |
| CODER المختار لـQA | `/opt/neura-ai/models/Qwen2.5-Coder-14B-Q4_K_M.gguf` | ملف مكتمل، generation فعلية لـCV وPython؛ لم يُنفّذ Python. |
| VISION | `/opt/neura-ai/models/Qwen3VL-8B-Instruct-Q4_K_M.gguf` ومعه `mmproj-Qwen3VL-8B-Instruct-F16.gguf` | MTMD/projector حقيقي؛ API أصاب اللونين وcomposer أخطأ في أحدهما. |
| embedding | `/opt/neura-ai/models/nomic-embed-text-v1.5.Q8_0.gguf` | header/hash فقط؛ لا يعني وجود RAG عامل. |

قياس `models.json` يحتوي prompts والخيارات والمخرجات والأسماء وأسباب النهاية. مدد الطلبات في هذه العينة: FAST نحو1.315/0.331/0.442ث، DAILY نحو4.098/0.853/2.594ث. هذه مدد شاملة في وضع CPU وليست decode tok/s. EXPERT استغرق نحو83.61ث وانتهى `length` عند حد768tokens؛ بدأ الخطوة الأولى وأطال HTML بدل إكمال ثلاث خطوات. التقييم لم يكتفِ برد غير فارغ أو grade من نموذج آخر.

عُينت الموارد250مرة أثناء التشغيل الحقيقي: أقصى زمن health poll نحو0.0188ث، وRSS backend نحو0.29–10.15GB بحسب المرحلة، وavailable RAM نحو25.76–28.11GB في هذه العينة. لا يعني ذلك اختبار ضغط RAM/VRAM؛ low-memory اختبر بحساسات مصطنعة. queue/load/prefill وdecode_tps بقيت `null` حيث لا توجد counters؛ لا حساب سرعات من عدد الأحرف ولا إعادة أرقام30–55tok/s القديمة.

قياس السياق استعمل tokenizer الحقيقي لـCoder في `vocab_only` دون weights inference، وفصل ثلاثة مشاريع مولدة عن fixture أمني وعن مشروعين كبيرين مصطنعين. **18 حالة/3أسئلة لكل مشروع**: full-source114–14066tokens، summary151–246tokens، والأسئلة metadata الفعلية أرسلت **0tokens إلى نموذج**. في Python الصغير كان source114 وsummary151؛ الملخص ليس دائمًا أصغر. هذه تكلفة context افتراضية مقاسة، لا نسبة توفير ثابتة ولا إثبات prompt caching. انظر `context-token-measurement.json`.

## الاختبارات الفعلية وكيف تعاد

الأوامر الآتية تعمل في fish وbash عند تشغيلها من checkout. انسخ مسار الجولة الذي يطبعه runner؛ `TARGET` هنا وصف، وليس متغير shell يجب تعريفه. لا تستعمل نتائج الجولة النهائية لتدعي قبول نسخة أحدث أو نسخة مثبّتة مختلفة.

```sh
python tools/verify_neura.py --suite static --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor
python tools/verify_neura.py --suite contract --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor --resume /absolute/run/path
python tools/verify_neura.py --suite ui --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor --resume /absolute/run/path
```

في الجولة المسلّمة كان target هو المسار المطلق للحزمة المستخرجة المبين أعلاه، و`--resume` هو مسار الجولة المرجعية. توجد الأوامر المطلقة المنفذة فعلًا وcwd/executable/returncode في `results.json::executions/invocations`؛ هذه ليست أوامر تثبيت0.4.6 من GitHub.

| الفحص | النتيجة الحالية | تفسير النطاق |
|---|---|---|
| pytest النهائي | **267 passed in10.81s**، exit0 | نماذج ومحولات وحساسات fake؛ أصل imports من الحزمة المستهدفة. لا جودة نموذج أو نافذة حقيقية. |
| Qt `qa_targets_workspace_qt.py` |14/14 | sandbox مفعّل، offscreen، نموذج وdesktop fake |
| Qt `qa_chat_first_qt.py` |30/30 | navigation/settings/generation/view/drawer/persistence مضبوطة |
| Qt `qa_milestone_ui.py` |15/15 | Markdown وحفظ وتأخير وتعارض وعزل؛ لا native visible KDE |
| packaged HTTP إضافي |20/20 | auth/Host/Origin وجلسات ومسودة محلية وأخطاء unavailable؛ no inference |
| FAST/DAILY |6/6 | native inference موضوعية، CPU، لا إعادة استخدام count تاريخي |
| EXPERT plan |**FAIL** | `length` قبل اكتمال الخطوات الثلاث |
| تاريخ system/user/assistant |PASS | `QA742`، بعد إصلاح502 الحقيقي |
| context overflow/recovery |PASS | خطأ واضح لسياق زائد، idle ثم ردOK؛ لا exhaustion حقيقي |
| SSE الحقيقي |PASS | هوية ثابتة، أول محتوى قبل النهاية و`stop/[DONE]` |
| CV/4files/Python |PASS في النطاق المبين | ملفات حقيقية وstatic validation وJS داخل المعاينة؛ لا تنفيذ Python على المضيف |
| native cancellation |PASS | last-good unchanged، انتهاء native ثم طلب لاحق صالح |
| vision API |PASS | PNG أحمر/أزرق، temp0، نتيجة «أحمر، أزرق» |
| vision composer |**FAIL** | رفع PNG نفسه، defaults الحالية temp0.7/max_tokens800، نتيجة «الأحمر والأسود» |
| desktop suite |7/7scenario | ستة launches accepted وسؤال معرفة؛ same-ID replay؛ remote pages/windows غير مثبتة |
| metadata/staleness |PASS | same-stat/add/delete/rename/context-read، عداد النموذج ثابت |
| restart |PASS لنطاق BackendService/IAB | ملفات وبصمات وتفضيل الألواح وhistory؛ native icon restart غير مختبر |
| browser isolation |PASS للـfixture | embedded/full وzero beacon/grant/history effects؛ Qt path منفصل |
| package/build |PASS للفحص المحلي | build + metadata + integrity + source identity؛ ليست transaction إدارية |

لا تجمع هذه الأعداد مع عدد البنود: قد يُستخدم testcase واحد لإثبات أكثر من ID. static review لـ109صفًا يعني مراجعة تنفيذها، لا109ميزة عاملة. baseline0.4.5 له258اختبارًا في جولته وفشل502؛ حُفظ منفصلًا ولا يحل محل267الحالية.

أثناء بناء الفاحص وقع عطل `TypeError` لأن متغير token budget ظلّل دالة `budget()`. صُحح إلى `token_budget`، وأضيف regression يثبت الاستمرار بعد إخفاق جودة مستقل، ثم نُفذ budget الحقيقي بنجاح. وقع أيضًا خطأ تجهيزتي اختبار ناقصتي `feature_state`، ثم نجحت266كلها قبل إضافة حالة محاسبة أخرى؛ العدد النهائي267. السجلات الفاشلة باقية. حفظ `harness-correction-history.json` التصنيف القديم الذي كان يلحق إخفاق جودة EXPERT خطأً بالتوجيه والنقل؛ أُعيدت قراءة المخرجات نفسها للفصل بين الادعاءات، دون توليد أجوبة بديلة أو إخفاء إخفاق الجودة.

في probe إضافي افترض الفاحص أولًا401/JSON، بينما العقد الموجود يعيد403للمصادقة و400نصيًا لـTrustedHost. راجعت المصدر والاختبارات وصُحح التوقع؛ `packaged-extra-api-attempt1.json` محفوظ. وقفة تصوير metadata انتهت قبل استكمالها؛ حُفظت stale وأُعيد الفحص دون pause بنجاح، لا تحويل timeout إلى نجاح.

## ما لم يكتمل

المصفوفة الكاملة تحتوي41`IMPLEMENTED` و31`PARTIAL` و25`MISSING` و10`DEFERRED` وبندين`SUPERSEDED`. `IMPLEMENTED` لا يساوي تلقائيًا Completed and verified؛ الحسم المنفصل `acceptance_reviewed` ومعه كل required cases. يوجد33IDمقبولًا ضمن النطاقات المحددة، دون اعتبار ذلك نسبة اكتمال عامة. بعض الأدلة الحقيقية ناجح وبعضهاFAIL/BLOCKED/NOT_RUN؛ لكل منها artifact أو سبب، لا تحويل error غير المتاح إلى نجاح للميزة.

| الأولوية | IDs | المشكلة الباقية | التنفيذ المقترح | الاعتماديات | معيار القبول |
|---|---|---|---|---|---|
| P0 | `N006 N042` | التخطيط تجاوز حد الرموز ولم ينفذ المطلوب | ضبط عقد planner المختصر وحدود السياق/النهاية وإظهار `length` بوضوح، ثم تقييم prompts ثابتة | النموذج الحالي ومنسق واحد | ثلاث خطوات فعلية دون HTML مطول أو رفض قدرة كاذب، مع إنهاء `stop` وسجل الخيارات |
| P0 | `N093` | الرؤية من UI أخطأت في الأزرق | مطابقة bytes/hash نجحت بالفعل؛ أكمل مقارنة الرسائل والsampling بين API وcomposer، ثم fixtures ألوان عربية/إنجليزية | GGUF+projector الحاليان | الرفع من packaged composer يجيب اللونين الصحيحين بتجارب معلنة؛ فشل الجودة لا يغطى بنجاحAPI |
| P0 | `N026` | updater قد يوقف backend مع dirty أو jobنشطة | gate صريح للعمل غير المحفوظ والمهمة النشطة قبل stop، وتعافي الإلغاء | Qt/BackendService وبيئة Arch قابلة للاستعادة | رفض/تأجيل آمن ثم update أصلي مصرح به يحفظ البيانات ويكشف الحزمة الخاطئة/المعدلة |
| P1 | `N019 N020 N025 N064 N067 N070 N071` | نافذة Qt الأصلية وsingle-instance/native windows غير مرصودة | تشغيل اختبار KDE مرئي وأيقونة مثبتة في بيئة مدعومة | أداة native desktop واختبار مناسب للمستخدم | رصد window/focus/ownership وDPI؛ فصل ذلك عن GIO acceptance |
| P1 | `N024 N025 N026` | clean install/update الإداري غير منفذ | تجربة VM/disposable عبر Polkit/pacman مدعومة | بيئة قابلة للاستعادة | install/retry/cache/cancel/update مع metadata/hash وuser-data preservation |
| P1 | `N045 N046` | static review لا يثبت السلوك، لا sandbox تنفيذ مكتمل | bounded repair مرتبط بالنتيجة، ثم sandbox اختياري مضبوط قبل أي تنفيذ | حدود filesystem/network/CPU/RAM/time | B+NEEDS_FIX والصفر لا يمران؛ أي test تشغيل يظل داخل isolation المعلن أو NOT_RUN |
| P1 | `N010 N011 N015 N016 N017 N018 N022 N108` | GPU/VRAM/defaults/gaming/profile مراحل غير مكتمل | اختبار اختيار PCI/UUID وKV budget والqueue/load/prefill counters ودورة gaming | Vulkan مدعوم، testwindow مستقلة | لا unload أثناء native؛ OOM واضح؛ cold/warm ومقاييس حقيقية دون تخمين |
| P1 | `N065 N073` | registry handlers ثابتة؛ legacy reusable grant دونrequest_id لا يميز retry | توحيد التسجيل typed وفرض ledger ID واضح لمسارات العمل المدعومة | dispatcher/skills API الحاليان | skill جديدة تدخل نفس schema/timeout/permissions؛ retried requests لا تنفذ مرتين |
| P1 | `N060` | خيارا المشروع المتشابهين يعرضان العنوان نفسه | غرض مختصر أو وقت/ID في أزرار clarification | المشروع المحفوظ | يميز المستخدم مشروعين بالاسم نفسه دون فتح أحدهما للتخمين |
| P2 | `N030 N031 N032` | Doctor قديم Windows/Flet؛ لا synced-folder detector حديث | Doctor readonly على Qt/XDG وتشخيصات محددة وتنظيف lint scoped | أدوات Linux المتاحة | كل probe فعلي أو unavailable، دون نموذج مستقل أو كتابة install tree |
| P2 | `N034–N040 N109` | لا vault facts/RAG/persona/cache/harvest article متكامل | approved explicit facts ثم CRUD/provenance/retrieval وحذف محدث | storage/versioned index وحساب context | أمثلة حفظ/تعديل/حذف/import وإجابة بمصدر حقيقي؛ sessions وحدها لا تحقق ذلك |
| P2 | `N080–N082` | لا reminders/notifications/video continuation عاملة | UTC/IANA+Asia/Riyadh وIDs وجدولة صريحة وروابط وقت مدخلة من المستخدم | خدمة مستخدم اختيارية للتنبيه المغلق | restart/missed/dedup والزمن والرابط صحيح؛ لا ادعاء watch history |
| P2 | `N085–N092 N094 N095` | STT/TTS تعيدان501، لا VAD/صوت عربي/worker/dictation مكتملة | runtime+weights متوافقة ثم fixtures صوت محلية وqueue/cancel/mute | mic/voice/CLI مدعومة وبيئة تشغيل مسموع | تسجيل عربي حقيقي وصمت/ضجيج/WAV/playback، وorb speaking يتبع الصوت الفعلي |
| P2 | `N074–N079 N047 N048` | skills إضافية/بحث مؤصّل/MCP/حلقة bounded غير متكاملة | parser حساب آمن ومصادر فعلية ثم مراحل محدودة وإذن server صريح | مصادر مختارة وعقود permissions | نتائج ذات مصادر/قيود صحيحة، وفشل/loop ينتهي؛ لا eval أو تركيب برامج مولدة |
| P2 | `N077` | شرح عادي موجود؛ الملف المختار لا يدخل تلقائيًا رحلة شرح مكتملة | إرفاق مصدر مختار حالي bounded دون إنشاء مشروع جديد | context endpoint الحالي | شرح actual selected source دون تنفيذ ودون الاعتماد على summary وحده |
| P2 | `N103` | Telegram ما زال يفرض port8000 | discovery/config محمي معinstance/version/stale checks | backend الحالي وعميلTelegram | contract tests للمنفذ المتغير والفشل؛ الرسالة الحية فقط لمحادثة يختارها المستخدم |
| P2 | `N061 N062 N097` | UI مثبتة؛ بعض required contract placeholders وتغطية تقييمات إضافية مفتوحة | استكمال دليل مستقل مناسب لكل معيار وتوثيق أي refinement دون محو الحالات السابقة | runner الحالي | لا placeholder مطلوب غير محسوم عند إغلاق ID، مع منع fake من إغلاق قبول real |

الصوت حُجب صراحة بـ501ولم يُثبت من وجود ملف whisper أو kokoro. `N088` ليس محركًا عربيًا مثبتًا. `N109` أعاد501حقيقيًا؛ لا مقال وهمي. Telegram لم يُرسل منه شيء. البحث المفتوح في Brave ليس retrieval أو deep research أو فهم فيديو. لا تشغيل لبرامج مولدة أو dependency install أو تفعيل تلقائي للامتدادات.

المؤجل منفصل: `N009 N027 N028 N083 N084 N096 N100 N101 N102 N105`. لا حسابAUR/Windows/browser tracking/calendar/cinematic boot/public server/self-authored skills/advanced input/alternative inference مفعلة أثناء التدقيق. `N106` و`N107` ملغيان، لا يُحسبان عملًا متبقيًا لـLinux.

يمكن استعمال المحادثة والمشاريع المحلية وملفاتها ومعاينتها وحفظها ودرج إعادة فتحها، ومهارات سطح المكتب المدعومة ضمن الأذونات. يعمل التخطيط المعقد والصوت والتكاملات وبعض معايير التوزيع جزئيًا أو لا تعمل. **المهام الثلاث التالية المقترحة:** إصلاح عقد التخطيط `N006/N042`، تشخيص إخفاق رفع الرؤية `N093`، ثم حماية التحديث واختباره `N026`. بقيت بقية البنود في المصفوفة، ولم يُعلن اكتمال الخطة.
