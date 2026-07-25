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
- واجهة عربية أو إنجليزية مرتبطة بخيار اللغة في الإعدادات.
- مستعرض HTML ومستعرض سهل، مع ترجمة الرسالة داخل أي منهما أو في نافذة مستقلة.

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

من داخل مجلد تعريف النسخة المحدودة، استخدم مسار الإصدار النظيف لتشغيل الاختبارات وبناء التطبيق والمثبت وملف ZIP وبصمات SHA-256:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_release_power_accessible_mail_64.ps1
```

عند عدم توفر شهادة Authenticode تحمل الملفات القابلة للتوزيع كلمة `UNSIGNED` بوضوح.

ستخرج النسخة في:

`..\release\win-x64-gmail-api-limited`

ويخرج ملف التثبيت بجوار ملف ZIP مباشرة في:

`..\release`

## إعداد Google OAuth

استخدم OAuth Client منفصلا لهذه النسخة عن OAuth Client الخاص بالنسخة الكاملة. ضع بيانات النسخة المحدودة في مفتاح `google_gmail_api` داخل `oauth_clients.json`:

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

لا تستخدم مفتاح `google` أو متغيرات `ACCESSIBLE_MAIL_GOOGLE_CLIENT_ID` و`ACCESSIBLE_MAIL_GOOGLE_CLIENT_SECRET`؛ فهي مخصصة للنسخة الكاملة.

يجب أن يحتوي Google Auth Platform على النطاق:

`https://www.googleapis.com/auth/gmail.modify`

أثناء وضع `Testing` لا يستطيع تسجيل الدخول إلا العنوان المضاف حرفيا إلى `Audience > Test users`. ستعرض Google للمختبر تحذير أن التطبيق غير موثق، كما تنتهي موافقته بعد سبعة أيام ويحتاج بعدها إلى تسجيل الدخول مجددا.

إذا نشرت هذه النسخة للعامة، حدّث سياسة الخصوصية وطلب المراجعة بحيث يذكران Gmail API والنطاق الجديد بدل `https://mail.google.com/`.
