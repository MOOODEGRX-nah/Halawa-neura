# 🧠 Neura — مساعد ذكاء اصطناعي محلي بالكامل

[![Build](https://github.com/MOOODEGRX-nah/Halawa-neura/actions/workflows/build.yml/badge.svg)](https://github.com/MOOODEGRX-nah/Halawa-neura/actions)
[![Release](https://img.shields.io/github/v/release/MOOODEGRX-nah/Halawa-neura?color=red)](https://github.com/MOOODEGRX-nah/Halawa-neura/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **مساعد ذكي شخصي يعمل 100% على جهازك — لا بايت واحد يغادر حاسوبك.**
> مستوحى من J.A.R.V.I.S، لكن حقيقي وقابل للتشغيل اليوم.

## ✨ المميزات الحالية

- 🚀 ~62 توكن/ثانية على RX 9060 XT عبر Vulkan (قياس فعلي: 21.5 TFLOPS عمليات مصفوفية)
- 🔒 خصوصية تامة: محادثاتك وملفاتك ونماذجك محلية
- 🤖 Qwen2.5-7B-Instruct Q4_K_M يعمل محلياً (4.4GB)
- 🎯 منتقي نماذج ذكي يكتشف كل ملفات GGUF تلقائياً
- 🔄 تحديث ذاتي جزئي: ~28KB لكل إصدار (manifest + SHA256)
- ⚡ Cache ذكي: لا يحمّل أي بايت مرتين
- 📦 توزيع بنقرة: Neura.exe + بناء تلقائي عبر GitHub Actions
- 🩺 Neura Doctor: أداة تشخيص شاملة (18 فحصاً)

## 🏆 الإنجازات

| الإصدار | الإنجاز |
|---------|---------|
| v0.1.0 | أول إطلاق — CPU |
| v0.1.1 | تسريع Vulkan (8 → 61.9 tok/s) |
| v0.1.2 | منتقي نماذج ذكي |
| v0.1.3 | محدّث جزئي + Cache |
| v0.2.0 | Launcher + CI/CD |
| v0.2.1 | إصلاح PYTHONPATH |
| v0.2.2 | تثبيت المحرك تلقائياً |

## 🗺️ خارطة الطريق (التفاصيل الكاملة في docs/MASTER_PLAN.md)

| الإصدار | الهدف | أبرز الملامح |
|---------|-------|--------------|
| v0.3.0 | ذاكرة + مراقبة | شبكة معرفة 3 فروع، Monitor حي، معايرة تلقائية |
| v0.4.0 | مهارات + وكلاء | @skill، Tool-Calling، Planner، ReAct |
| v0.5.0 | صوت احترافي | Whisper محلي، VAD، بث نص وصوت، إملاء |
| v0.6.0 | وجه هولوغرامي | كرة Three.js بأربع حالات، WebSocket، إقلاع سينمائي |
| v0.7.0 | وضع مطور الويب | Qwen2.5-Coder + خزنة قوالب + تصحيح ذاتي |
| v1.0.0 | إنتاج كامل | Deep Research، Personas، Profiler، حلقة تعلم |

## 🏗️ البنية المعمارية

    Neura-Portable/
    ├── Neura.exe            Launcher ذكي (8MB)
    ├── python-embed/        Python 3.11 + llama-cpp (Vulkan)
    ├── src/                 واجهة Flet + العقل + المحدّث + Cache
    ├── models/              ملفات GGUF
    ├── data/                محادثات + إعدادات
    ├── tools/               Neura Doctor + AI-Bench
    └── docs/                MASTER_PLAN (56 مهمة)

## 🎨 اختيار التقنيات (بوعي)

| المكون | الاختيار | السبب |
|--------|----------|-------|
| الواجهة | Flet | عبر منصات + عربي ممتاز |
| المحرك | llama-cpp-python (Vulkan) | محلي + سريع + يدعم AMD |
| النماذج | GGUF Q4_K_M | توازن حجم/جودة/سرعة |
| التحديثات | Releases + SHA256 | آمنة وجزئية |
| التوزيع | PyInstaller + Actions | exe + بناء تلقائي |

## 🆚 لماذا محلي وليس سحابياً؟

| الخاصية | Neura | المساعدات السحابية |
|---------|-------|-------------------|
| الخصوصية | 100% على جهازك | بياناتك على خوادمهم |
| التكلفة | مجاني للأبد | اشتراكات شهرية |
| الإنترنت | غير مطلوب بعد التثبيت | مطلوب دائماً |
| السرعة | 62 tok/s على كرتك | حسب ازدحام الخدمة |

## 🚀 البدء السريع

**للمستخدمين (3 دقائق):**
1. حمّل `Neura-Portable-vX.zip` من Releases
2. فك الضغط في أي مكان
3. انقر `Neura.exe` — يثبّت كل شيء تلقائياً
4. حمّل النموذج من الإعدادات ⚙️ (4.4GB)

**للمطورين:**

    git clone https://github.com/MOOODEGRX-nah/Halawa-neura.git
    cd Halawa-neura
    install.bat
    run.bat

**التشخيص:**

    python-embed/python.exe tools/diagnose.py

## 🔒 الخصوصية

لا يتصل Neura بأي خادم خارجي إلا في حالتين:
1. فحص التحديثات (GitHub API — قراءة فقط)
2. تحميل النماذج (HuggingFace — مرة واحدة)

كل ما عدا ذلك يبقى على جهازك للأبد.

## 🙏 الاعترافات

مستوحى من: **OpenJarvis** (فلسفة local-first)، **Pipecat** (مسارات الصوت)،
**LangGraph** (تنسيق الوكلاء)، **sukeesh/Jarvis** (نمط @skill)،
**openclaw-jarvis-ui** (الكرة الهولوغرامية)،
**Build Your Own J.A.R.V.I.S Blueprint** (القواعد الذهبية).

## 📄 الرخصة

MIT — استخدمه، عدّله، وزّعه بحرية.

---

<div align="center">

**صُنع بـ ❤️ في العالم العربي**

</div>
