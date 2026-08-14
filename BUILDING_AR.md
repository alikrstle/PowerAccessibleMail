# بناء Power Accessible Mail

يملك البرنامج مصدرا واحدا وميزاته متطابقة في نسختي Windows:

- `x64` لأنظمة 64 بت الحديثة.
- `x86` لأنظمة 32 بت.

تستخدم حسابات Gmail واجهة Gmail API ونطاق `gmail.modify`. ويدعم المصدر نفسه Microsoft OAuth والحسابات اليدوية عبر IMAP وSMTP.

## إعداد OAuth

أنشئ `oauth_clients.json` في جذر المشروع اعتمادا على `oauth_clients.example.json`. يجب أن يحتوي المفتاحين:

- `google_gmail_api`
- `microsoft`

لا تضع المفتاح القديم `google` ولا نطاق `https://mail.google.com/` في الإصدارات الجديدة.

## بيئات Python

- `.venv`: Python 64 بت.
- `.venv-x86`: Python 32 بت.

يجب أن تطابق الحزم في البيئتين ملف `requirements-release.lock`. يحتوي الملف على
بصمات SHA-256 لعجلات Windows المعتمدة في معماريتي x64 وx86، ويجب تثبيته باستخدام
الخيار `--require-hashes` حتى يرفض pip أي حزمة مستبدلة أو غير معتمدة.

الإعداد الحالي الموثق يستخدم Python 3.13.15 في `D:\python` لنسخة x64
و`D:\python-x86` لنسخة x86. لا تعتمد على وجود `python.exe` داخل البيئة فقط؛
شغّل `test_all_architectures.ps1` للتأكد من أن المفسر الأساسي وPyInstaller ما زالا
يعملان بالمعمارية المطلوبة.

## البناء

لبناء البرنامج فقط:

```powershell
.\build_power_accessible_mail_x64.ps1
.\build_power_accessible_mail_x86.ps1
```

لبناء الإصدار الكامل، بما في ذلك الاختبارات والمثبت والنسخة المحمولة والبصمات:

```powershell
.\build_release_power_accessible_mail_x64.ps1
.\build_release_power_accessible_mail_x86.ps1
```

يتطلب بناء الإصدار العام ضبط `POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT` لشهادة Authenticode موثوقة، ثم يوقع ملف البرنامج والمثبت مع ختم زمني عبر HTTPS. يتوقف البناء إذا لم توجد الشهادة حتى لا ينشر ملف غير موقع بالخطأ.

يسمح الخيار `-AllowUnsigned` ببناء ملفات تحمل `UNSIGNED` للاختبار المحدود أو للتحليل المحلي وإرسال إنذار كاذب إلى Microsoft:

```powershell
.\build_release_power_accessible_mail_x64.ps1 -AllowUnsigned
.\build_release_power_accessible_mail_x86.ps1 -AllowUnsigned
```

يجوز نشر هذه الملفات في GitHub كـ`Pre-release` للمختبرين فقط، مع تحذير واضح
من غياب التوقيع. لا يجوز إدراجها في إصدار مستقر أو تقديمها على أنها نسخة إنتاج.

على جهاز اختبار تكون فيه حماية Defender فعالة، افتح PowerShell كمسؤول وشغّل فحص الإصدار الاختياري. يستخدم الفحص تعريفات الحماية الحالية و`DisableRemediation` حتى يسجل الاكتشاف من دون عزل ملفات الحزمة:

```powershell
.\build_release_power_accessible_mail_x64.ps1 -AllowUnsigned -RunDefenderScan
.\build_release_power_accessible_mail_x86.ps1 -AllowUnsigned -RunDefenderScan
```

بناء التطبيق هو `onedir` ومن دون UPX. يستخدم المثبت غير الموقع ضغط `zip` غير متصلب، ولا يشغّل المحدّث المثبت بصمت أو من مجلد Windows المؤقت. لا تمنع هذه الاحتياطات الإنذارات الكاذبة بصورة مضمونة، لكنها تقلل السلوكيات التي قد تبدو ملتبسة.

راجع `DEFENDER_FALSE_POSITIVE_AR.md` قبل أي إصدار يصنّفه Defender.

## المخرجات

- التطبيق: `release\win-x64` و`release\win-x86`.
- المثبتان والنسختان المحمولتان: داخل `release`.
- ملف SHA-256 وبيان بناء مستقل لكل معمارية، وفي البيان جرد لبصمات وحالة توقيع ملفات EXE وDLL وPYD.
- عند استخدام `-RunDefenderScan` ينشأ تقرير `DEFENDER-SCAN-X64-...txt` أو `DEFENDER-SCAN-X86-...txt`.

المثبت والمحدّث يستخدمان اسما واحدا للمنتج، ويختار المحدّث الأصل المطابق لمعمارية البرنامج الجاري تشغيله.
