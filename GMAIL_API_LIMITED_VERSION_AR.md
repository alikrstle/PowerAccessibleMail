# نسخة Gmail API محدودة الصلاحيات

هذه نسخة مستقلة من Power Accessible Mail مخصصة لحسابات Google/Gmail عبر Gmail API بدل IMAP/SMTP.

## لماذا هذه النسخة؟

النسخة الأصلية تستخدم Gmail عبر IMAP و SMTP، وهذا يتطلب نطاق OAuth الواسع:

`https://mail.google.com/`

النسخة المحدودة تستخدم Gmail API بالنطاق:

`https://www.googleapis.com/auth/gmail.modify`

هذا النطاق ما زال مصنفا عند Google كنطاق مقيد Restricted، لكنه أضيق من `mail.google.com` لأنه لا يعطي صلاحية الحذف الدائم المباشر خارج سلة المهملات.

## ما الذي تدعمه النسخة المحدودة؟

- تسجيل الدخول إلى Gmail عبر المتصفح.
- عرض الوارد عبر Gmail API.
- عرض الرسائل غير المرغوب بها عبر تصنيف `SPAM`.
- عرض الرسائل المرسلة عبر تصنيف `SENT`.
- قراءة نص الرسالة.
- عرض الروابط والمرفقات.
- حفظ المرفقات.
- جعل الرسائل مقروءة عند فتحها.
- إرسال رسائل جديدة والرد على الرسائل.
- الكاش المحلي المشفر كما في النسخة الأصلية.

## ما المختلف داخليا؟

- لا تستخدم `imap.gmail.com`.
- لا تستخدم `smtp.gmail.com`.
- لا تحتاج تفعيل IMAP من إعدادات Gmail.
- تعتمد على REST API:
  - `users.messages.list`
  - `users.messages.get`
  - `users.messages.attachments.get`
  - `users.messages.modify`
  - `users.messages.send`

## هل يمكن دمج أكثر من API من Google؟

نعم. يمكن للتطبيق الواحد أن يستخدم أكثر من API وأكثر من نطاق OAuth، مثل Gmail API وPeople API وDrive API. لكن كل نطاق جديد يظهر للمستخدم في شاشة الموافقة وقد يزيد صعوبة مراجعة Google. القاعدة الأفضل هي طلب أقل صلاحية ممكنة، وفي اللحظة التي يحتاجها المستخدم.

## ملفات التشغيل والبناء

تشغيل النسخة المحدودة من المصدر:

```bat
python main_gmail_api_limited.py
```

بناء نسخة 64 بت:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_power_accessible_mail_gmail_api_limited_64.ps1 -PythonPath .\.venv\Scripts\python.exe
```

بناء إصدار نظيف مع الاختبارات والمثبت وملف ZIP وبصمات SHA-256:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_release_power_accessible_mail_gmail_api_limited_64.ps1
```

عند عدم توفر شهادة Authenticode تحمل أسماء المثبت وملف ZIP كلمة `UNSIGNED`. عند توفر الشهادة اضبط `POWER_ACCESSIBLE_MAIL_SIGNING_CERT_THUMBPRINT` وسيستخدم مسار الإصدار الشهادة والختم الزمني تلقائيا.

مجلد الجذر `accessible_mail` هو المصدر الوحيد. مجلدا `. النسخة الكاملة` و`. النسخة المحدودة` ملفا تعريف للتشغيل وبيانات OAuth والبناء، وليسا نسختين إضافيتين من المصدر.

ستخرج النسخة في:

`release\win-x64-gmail-api-limited`

ويخرج ملف التثبيت بجوار ملف ZIP مباشرة في:

`release`

## إعداد Google OAuth

استخدم OAuth Client منفصلا لهذه النسخة عن OAuth Client الخاص بالنسخة الكاملة. ضع بيانات النسخة المحدودة في مفتاح `google_gmail_api` داخل `. النسخة المحدودة\oauth_clients.json`:

```json
{
  "google_gmail_api": {
    "client_id": "ضع Client ID الخاص بنسخة Gmail API المحدودة هنا",
    "client_secret": "ضع Client Secret الخاص بنسخة Gmail API المحدودة هنا"
  }
}
```

أو اضبطها عبر متغيرات البيئة:

- `ACCESSIBLE_MAIL_GOOGLE_GMAIL_API_CLIENT_ID`
- `ACCESSIBLE_MAIL_GOOGLE_GMAIL_API_CLIENT_SECRET`

يجب أن يحتوي OAuth Consent Screen الخاص بهذه النسخة على النطاق:

`https://www.googleapis.com/auth/gmail.modify`

لا تستخدم قيم `google` أو متغيرات `ACCESSIBLE_MAIL_GOOGLE_CLIENT_ID` و`ACCESSIBLE_MAIL_GOOGLE_CLIENT_SECRET` لهذه النسخة؛ تلك مخصصة للنسخة الكاملة التي تستخدم `https://mail.google.com/`.

في Google Auth Platform يجب أن يكون اسم التطبيق `Power Accessible Mail` كي يطابق اسم البرنامج الذي يراه المستخدم. أثناء حالة النشر `Testing` أضف عنوان Gmail الكامل لكل مختبر ضمن `Audience > Test users`. ستعرض Google تحذير التطبيق غير الموثق للمختبرين، وتنتهي صلاحية موافقتهم بعد سبعة أيام ثم يحتاجون إلى تسجيل الدخول مجددا.

إذا نشرت هذه النسخة للعامة، حدّث سياسة الخصوصية وطلب المراجعة بحيث يذكران Gmail API والنطاق الجديد بدل `https://mail.google.com/`.
