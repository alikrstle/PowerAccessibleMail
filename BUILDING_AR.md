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

يجب أن تطابق الحزم في البيئتين ملف `requirements-release.lock`.

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

عند ضبط `POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT` يوقع البناء ملف البرنامج والمثبت مع الختم الزمني. من دون شهادة تحمل أسماء الأصول اللاحقة `UNSIGNED`.

## المخرجات

- التطبيق: `release\win-x64` و`release\win-x86`.
- المثبتان والنسختان المحمولتان: داخل `release`.
- ملف SHA-256 وبيان بناء مستقل لكل معمارية.

المثبت والمحدّث يستخدمان اسما واحدا للمنتج، ويختار المحدّث الأصل المطابق لمعمارية البرنامج الجاري تشغيله.
