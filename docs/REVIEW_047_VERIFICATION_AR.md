# إعادة فحوص مراجعة 0.4.6 على المرشح 0.4.7

المراجعة الخارجية تشخيص وليست إصلاحًا. تحفظ الجولة الجديدة الأدلة الفاشلة قبل التعديل، ثم تفحص المصدر والحزمة. لا يُنسخ قبول0.4.6 أو عدد اختبارات قديم إلى جولة جديدة.

`tests/regression/test_review_046.py` يغطي التوجيه والخطة المبتورة وعقد الخطة وlast-good وسباق snapshot. `test_update_lifecycle.py` يغطي admission والمهام والمصادقة دون معاملة إدارية. `test_desktop_skills.py` يحدد مالك الملف وصلاحياته كمدخل اختبار مستقل عن UID المضيف. `qa_review_update_qt.py` يفحص واجهة التأجيل والإلغاء والقراءة الأخيرة والاسترداد في Qt offscreen بمحاكيات صريحة وsandbox مفعّل.

من جذر المصدر، استعمل المسارات المطلقة للهدف والجولة اللذين يطبعهما الفاحص. هذه الأوامر تدعم fish وbash:

```sh
python tools/verify_neura.py --suite static --target-root /absolute/package/app
python tools/verify_neura.py --suite contract --target-root /absolute/package/app --resume /absolute/run
python tools/verify_neura.py --suite ui --target-root /absolute/package/app --resume /absolute/run
```

يمكن بدء خدمة QA الحقيقية الوحيدة بعد انتهاء أي نسخة Neura أخرى. مراقب الاستدلال اختياري ومقصور على profile ذي علامة QA؛ يسجل مدخلات الاختبار الاصطناعية الفعلية قبل `backend.generate` ويمرر استجابة llama.cpp نفسها. لا يحل محل النموذج أو يبث نصًا مصطنعًا. لا تستخدم بيانات شخصية في جلسة tracing:

```sh
python tools/verify_neura.py --target-root /absolute/package/app --resume /absolute/run --serve real --allow-real-model --trace-real-model
```

اختبر من composer «برمج لي لعبة XO»، و«برمج لي موقع للcv»، و«برمج لي لعبة ثعبان باستخدام Python»، و«اكتب لي كود Python لحساب المصروفات». على مشروع ويب محفوظ اختبر «أضف زر تسجيل دخول» ثم «أضف الوضع الداكن إلى هذا المشروع». قارن IDs والمراجعات والمصدر الفعلي وعدد jobs، واحفظ صور النتيجة والفشل. لا تشغّل Python الناتج على المضيف. اختبارات النفي والشرح والاقتباس والهدف غير الفريد يجب ألا تنشئ job غير مقصودة.

بعد انتهاء مهمة الواجهة، يمكن اختبار الخطة المطلوبة بحد768رمزًا ودون retry تلقائي:

```sh
python tools/verification/review_cases.py --case required-plan --allow-real-model --run /absolute/run --target-root /absolute/package/app
```

يفصل الدليل نجاح سياسة fail-closed عن نجاح النموذج في إنتاج خطة. `plan=true` يتطلب `stop` وJSON بخطوات قصيرة وأسماء آمنة قبل coder. failure لا يُسمى مرحلة مكتملة، ويحفظ سجلها وlast-good. لا يدّعي فحص البنية صحة السلوك.

للمقارنة البصرية تولّد `vision_fixtures.py` ثلاث صور RGB ثابتة ومعلنة، وليست screenshots:

```sh
python tools/verification/vision_fixtures.py --output /absolute/run/artifacts/vision-fixtures
```

ارفع كل صورة مرة واحدة من واجهة الحزمة بتاريخ محادثة جديد، وبالنص الموجود في manifest. احفظ الرد الأصلي وصورته واسم trace الجديد. ثم أعد طلب API واحدًا بالخيارات الفعلية نفسها:

```sh
python tools/verification/review_cases.py --case vision-pair --allow-real-model --run /absolute/run --target-root /absolute/package/app --ui-trace /absolute/run/artifacts/model-traces/TRACE.json --ui-output 'الرد الفعلي من الواجهة' --expected red blue
```

المقارنة تفحص رسائل native كاملة بما فيها system، وخيارات sampling والبث، وmodel/projector/device/context/template والصورة. تطابق الصورة وحده غير كافٍ. عدم تثبيت seed في المسارين يعني أن الردود العشوائية قد تختلف رغم تطابق الإعدادات. لا تُعد الصورة حتى تنجح، ولا تُعدّل النتائج أو ترفع الحد بعد رؤية الفشل. تبقى Native KDE/GPU/audio/admin أدلة منفصلة. أداة تقرير الجولة تعيد1للفشل و3للقبول الناقص؛ لا تُخفهما للحصول على نتيجة خضراء.
