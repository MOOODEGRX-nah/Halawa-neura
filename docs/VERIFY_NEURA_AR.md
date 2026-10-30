# التحقق المتكرر من Neura

المدخل `tools/verify_neura.py` يراجع كتالوج `tools/verification/catalog.json`: **109 معرفات فريدة من N001 إلى N109**، منها80نشطة و17انحدارًا سابقًا و10مؤجلة وبندان ملغيان. أصل المواصفة محفوظ دون تحويلها إلى نتائج في `VERIFICATION_ASSIGNMENT_2026-10-30.md`. التقارير القديمة لا تدخل نتائج الجولة الجديدة تلقائيًا.

استخدم Python المتوافق مع الحزمة. لا تثبت اعتماديات في system Python أثناء التدقيق. في هذا الجهاز يُستخدم `/usr/bin/python` وvendor المثبت في `/opt/neura-ai/vendor`. عند فحص مصدر checkout مرر `--vendor-dir /opt/neura-ai/vendor`؛ وعند فحص حزمة مستخرجة يوجد vendor بجانب app. تستهدف الحزمة الحالية Python3.14 وLinux/Arch؛ Windows مؤجل.

الأوامر الآتية تعمل في fish وbash. شغّلها من جذر المستودع، أو استعمل المسار الكامل للسكربت:

```sh
python tools/verify_neura.py --suite static --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor
```

يطبع السكربت `run_id` ومسار النتائج والملف الشخصي والأثر المخطط قبل التنفيذ. يحفظ `results.json` و`REPORT_AR.md` و`logs/` و`artifacts/` و`screenshots/`. تُرفض المسارات التي تتداخل مع بيانات المستخدم الأصلية أو ملفات التثبيت؛ كل جولة جديدة لها UUID وملف ملكية QA. لا تطبع الأداة الرمز السري.

استبدل `/absolute/run/path` أدناه بمسار الجولة المطبوع، واستعمل target نفسه عند الاستئناف:

```sh
python tools/verify_neura.py --suite contract --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor --resume /absolute/run/path
python tools/verify_neura.py --suite ui --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor --resume /absolute/run/path
```

`contract` يستخدم نماذج ومحولات وحساسات صريحة وهمية؛ يمنع fixture تهيئة Vulkan للاستدلال وقراءة VRAM الحقيقية، وتسجل أصول imports. `ui` يشغل Qt offscreen بمحاكيات، مع sandbox المعتاد ودون `--no-sandbox`. لا يشهد أي منهما بجودة النموذج أو ظهور نافذة KDE. قراءات renderer من checkout معلنة، وتُفحص مطابقة الأصول للحزمة. فشل الاعتماديات أو الاستيراد أو مهلة الاختبار يظهر في log ولا يتحول إلى نجاح.

لاختبار النموذج الحقيقي احفظ عملك وأغلق النسخة الأخرى أولًا. الأداة لا تقتل نسخة المستخدم لتوفير الذاكرة. ابدأ خادم QA من الحزمة المختارة:

```sh
python tools/verify_neura.py --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor --resume /absolute/run/path --serve real --allow-real-model --allow-desktop
```

يبدأ `BackendService` الأصلي منفذًا ديناميكيًا، ويتحقق من `instance_id` والإصدار، ويحفظ اكتشافه في `artifacts/backend.json` دون token. لا يفترض port8000. افتح URL المطبوع في هذا الملف عبر واجهة المتصفح المصرح بها، ثم أدخل «برمج لي موقع للcv» من composer. صوّر الانتقال والبث والكود والمعاينة والحفظ والتبديل وإعادة الفتح؛ استورد ملاحظات UI للجولة نفسها، لا صورًا قديمة. تشغيل BackendService عبر هذا المسار ليس برهان فتح أيقونة Qt الأصلية؛ ذلك فحص منفصل.

من طرفية أخرى، وبعد انتهاء مهمة الواجهة، استعمل المنسق نفسه:

```sh
python tools/verify_neura.py --suite model --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor --resume /absolute/run/path --allow-real-model
python tools/verify_neura.py --suite desktop --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor --resume /absolute/run/path --allow-desktop
```

الاختبار الحقيقي يختار CPU صراحة وسياق4096 ونموذج Coder الاختياري المكتمل، دون تغيير إعدادات الإنتاج أو تحميل أوزان جديدة. تُقاس الموارد أولًا؛ يبدأ RAM preflight محافظ ولا يُفتعل OOM. كل التوليد عبر المنسق الحالي، ولا يبدأ مع backend آخر غير مملوك للجولة. يشمل `model` العربية والإنجليزية والمختلط، وخطة فعلية، وصورة بألوان معروفة، وPython مفحوصًا ساكنًا لا منفذًا، وإلغاء تعديل يحفظ آخر نسخة، وتاريخ محادثة وسقف سياق. يعاد استخدام مشروع CV الذي أنشأه composer؛ لا يحل latest edit محل دليل مهمته الأصلية. عند غياب رحلة composer تبقى مفتوحة.

حالات منفردة للتشخيص دون إعادة كل التوليد:

```sh
python tools/verify_neura.py --suite model --model-case history --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor --resume /absolute/run/path --allow-real-model
python tools/verify_neura.py --suite model --model-case budget --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor --resume /absolute/run/path --allow-real-model
python tools/verify_neura.py --suite model --model-case transport --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor --resume /absolute/run/path --allow-real-model
```

التوليد له مهل منفصلة أطول. لا يعني timeout العميل انتهاء عمل llama.cpp. يُطلب الإلغاء وتنتظر الأداة حالة idle حتى الحد المعلن؛ إذا لم تثبت نهاية العمل تبقي هوية العملية المملوكة وتمنع بدء نموذج آخر، بدل تحريرها كذبًا. تنظيف static/fake فقط قد ينهي مجموعة عملياته المملوكة عند المهلة، مع حد16MiB للملفات. لا يوجد pkill عام أو قتل listener مجهول. لإغلاق خدمة QA المملوكة بعد انتهاء عملها، أنشئ ملف `stop-server` داخل الجولة؛ الخدمة تنتظر نهاية العمل الأصلي قبل الإغلاق. مدة الخدمة القصوى ساعة، وليست خدمة خلفية للمستخدم.

`desktop` يحتاج opt-in صريحًا؛ يستخدم GIO الموثوق عبر API، ولا ينفّذ نص أوامر مولّدًا. قبول طلب الفتح منفصل عن رصد النافذة أو قراءة الصفحة. سجل التطبيقات يخص ما أطلقه Neura فقط. لا يرسل Telegram أو بريدًا، ولا يجري مصادقة أو تثبيتًا إداريًا أو نشرًا أو مراقبة تصفح.

فحوص إضافية قابلة للتكرار على الخدمة المملوكة نفسها، مع `vendor` بجوار `app`:

```sh
python tools/verification/probes.py --probe metadata --run /absolute/run/path --target-root /opt/neura-ai/app
python tools/verification/probes.py --probe api --run /absolute/run/path --target-root /opt/neura-ai/app
python tools/verification/probes.py --probe browser-security --run /absolute/run/path --target-root /opt/neura-ai/app
```

الأول يعدل ملفات مشروع QA ذي الملفات الأربعة ويختبر ثبات size/mtime والإضافة والحذف ومرجع صورة مفقود، ثم يعيد المصدر والفهرس لحالة صالحة. `--pause-for-ui` يتيح تصوير stale حتى180ثانية؛ إنشاء ملف `continue-metadata` داخل الجولة يكمل الفحص. انتهاء مهلة التصوير يترك الدليل القديم ويعيد خطأ، ولا يمر كنجاح. الثاني يختبر جلسات اصطناعية ومصادقة ومسودة بريد وأخطاء غياب الصوت دون تسجيل أو إرسال. الثالث ينشئ fixture هجوميًا غير مولد وخادم beacon محليًا مملوكًا، ثم تنتظر الأداة حتى20دقيقة فحص المعاينة المضمنة والكاملة. بعد حفظ النتائج والصور أنشئ `finish-browser-security` داخل الجولة؛ تتأكد الأداة من صفر آثار في history/grants/beacon وتغلق الخادم. هذه العلامة وحدها لا تثبت عزل الواجهة؛ يجب إرفاق assertions الواجهة والصور. لا تُشغّل أكثر من كاتب واحد لـresults.json في الوقت نفسه.

`--suite all` يشغل المتاح ويسجل المحجوب؛ لا يفعل المؤجلات. الأكواد: **0** نجاح الفحوص المختارة، **1** فشل فعلي، **3** قبول غير مكتمل/محجوب. ملخص الكتالوج مستقل: لا تتساوى أعداد الحالات مع أعداد البنود، ولا يكفي PASS وهمي أو فحص مصدر لإغلاق قبول حقيقي. الحسم النهائي يحتاج مراجعة صريحة لجميع معايير البند. `feature_state` منفصل عن `case_result` و`evidence_method`.

لتوليد التقرير والأرشيف دون إعادة الاختبارات:

```sh
python tools/verify_neura.py --suite report --target-root /opt/neura-ai/app --vendor-dir /opt/neura-ai/vendor --resume /absolute/run/path --observations /absolute/run/path/artifacts/ui-observations.json --archive
```

تحتوي الملاحظات `run_id` نفسه و`cases` بأرقام N ونتائج وطريقة وأثر وخطوات، و`screenshots` بمسار نسبي وcaption عربي. تُرفض ملفات جولة تاريخية وروابط تتجاوز حدود الجولة. الأرشيف يستبعد profile/cache والأوزان، ويرفض تصدير token الـQA، ويُختبر ZIP وتُحسب بصمته. ضمّن الصور الفعلية في التسليم، وأعلن المحاكاة وoffscreen وأي فشل أو قيود رصد.

الإصلاح الإضافي في0.4.6 موثق من تجربة0.4.5 الفاشلة: تعليمات القدرات كانت تضيف system ثانية يقبلها المحاكي ويرفضها قالب Gemma3. `capability_messages()` يدمج المقدمة مع رسائل النظام الأولى ويحفظ بقية الأدوار والصور، ثم يستعمل قالب GGUF نفسه. كما فُصلت قائمة مهارات الجهاز عن القدرة على كتابة نص وخطة وكود. نجاح رد غير فارغ لا يكفي: تحقق الخطة يرفض الرفض المرقم الذي يدّعي عجزًا غير صحيح.
