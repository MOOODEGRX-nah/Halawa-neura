# نشر neura-ai-bin على AUR لأول مرة

حزمة AUR مجهّزة، لكنها غير مسجلة بعد. هذه الخطوة تحتاج حساب AUR مستقلًا؛ حساب GitHub لا ينشئه تلقائيًا. بعد النشر يعمل:

```bash
paru -S neura-ai-bin
```

## إنشاء الحساب وربط SSH

1. أنشئ حسابًا من [صفحة AUR الرسمية](https://aur.archlinux.org/register).
2. أنشئ مفتاح SSH على جهازك إن لم يكن لديك مفتاح مناسب:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/aur -C "AUR package publishing"
```

3. انسخ **المفتاح العام فقط** من `~/.ssh/aur.pub` إلى حقل SSH Public Key في إعدادات حساب AUR. احتفظ بالملف `~/.ssh/aur` الخاص على جهازك.
4. أضف إلى `~/.ssh/config`:

```text
Host aur.archlinux.org
    User aur
    IdentityFile ~/.ssh/aur
    IdentitiesOnly yes
```

## رفع وصف الحزمة

حمّل `neura-ai-bin-<version>-aur.tar.gz` من [إصدار Neura على GitHub](https://github.com/MOOODEGRX-nah/Halawa-neura/releases/latest) وفكّه. يحتوي الملفات الجاهزة بالبصمة الفعلية لأرشيف runtime المنشور. ثم:

```bash
git clone ssh://aur@aur.archlinux.org/neura-ai-bin.git aur-neura-ai-bin
```

انسخ `PKGBUILD` و`.SRCINFO` من الأرشيف إلى جذر `aur-neura-ai-bin`، ثم نفّذ بداخله:

```bash
git add PKGBUILD .SRCINFO
git commit -m "Publish Neura AI Linux desktop"
git push
```

إذا كان الاسم قد حُجز لاحقًا من ناشر آخر، لا تحاول استبدال حزمته؛ استخدم اسمًا متاحًا أو اطلب الصيانة وفق قواعد AUR. عند كل إصدار جديد ترفع Actions أرشيف AUR بالبصمة والنسخة الجديدتين؛ حدّث الملفين وادفع commit جديدًا في مستودع AUR.

ملف `packaging/aur/PKGBUILD.in` في GitHub قالب بناء فقط. ملف الإصدار الجاهز يحل محل `@VERSION@` و`@SHA256@` بالقيم الحقيقية. لا تستخدم `SKIP` للبصمة، ولا تنشر قالبًا غير مستبدل.
