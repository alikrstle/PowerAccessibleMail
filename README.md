# برنامج البريد الإلكتروني المتوافق مع المكفوفين

تطبيق بريد إلكتروني أولي بلغة Python وواجهة wxPython. الواجهة عمودية، وتعتمد على عناصر Windows/wx الأصلية لتعمل بشكل أفضل مع قارئات الشاشة.

## التشغيل

1. افتح موجه الأوامر داخل هذا المجلد.
2. شغل ملف التثبيت:

```bat
install.bat
```

أو ثبت المتطلبات يدويا:

```bat
python -m pip install -r requirements.txt
```

3. شغل البرنامج:

```bat
python main.py
```

أو شغل الملف:

```bat
run.bat
```

## ما الذي يدعمه الإصدار الحالي؟

- إضافة حساب بريد واحد أو أكثر باستخدام IMAP و SMTP.
- إضافة حساب Gmail بتسجيل الدخول عبر المتصفح باستخدام OAuth.
- عرض الرسائل الواردة.
- عرض رسائل البريد غير المرغوب بها إذا كان اسم المجلد معروفا أو يمكن اكتشافه تلقائيا.
- عرض الرسائل المرسلة.
- تصنيف الرسائل إلى مقروءة وغير مقروءة.
- جلب الرسائل على دفعات صغيرة بدل تحميل كل الحساب مرة واحدة.
- عرض نسبة تقدم أثناء استلام الرسائل من الخادم.
- حفظ الرسائل المستوردة محليا في تخزين مشفر حتى لا يعيد البرنامج طلبها كل مرة.
- واجهة عربية أو إنجليزية يمكن تبديلها مباشرة من الإعدادات.
- مستعرض HTML ومستعرض نصي سهل للرسائل.
- ترجمة الرسالة إلى لغة الواجهة داخل مستعرض الرسالة أو في نافذة مستقلة حسب الإعداد المختار.
- استخراج الروابط والمرفقات وعرضها في مستعرض واحد، مع تمييز كل عنصر بعنوان مثل رابط 1 أو مرفق 1.
- إنشاء رسالة جديدة.
- الرد على رسالة محددة من زر "رد" الموجود بجانب "فتح الرابط".
- قائمة مساعدة تحتوي على دليل البرنامج وخيار فحص التحديثات.
- تظهر الرسائل في الوضع العادي كعناصر قائمة بلا مربعات اختيار. استخدم `Ctrl+Shift+Space` لتفعيل التحديد المتعدد وإظهار المربعات، ثم حدّد بالمسافة أو بالفأرة. اضغط `Control` وحده لسماع عدد الرسائل المحددة، ويُنطق الوصول إلى بداية القائمة أو نهايتها.
- قائمة أوامر رئيسية عمودية يمكن التنقل فيها بالسهم للأعلى والأسفل، وتنفيذ الأمر المحدد بـ Enter أو Space.
- أمر "تحميل رسائل أقدم" لجلب الدفعة السابقة من رسائل القسم الحالي.
- أمر "إعادة تسجيل الدخول للحساب" لتجديد OAuth إذا رفضت Google الرمز أو تغيّرت الصلاحيات.
- اختصارات لوحة المفاتيح:
  - F5 لتحديث المحتوى المعروض.
  - Ctrl+N لإنشاء رسالة.
  - Ctrl+R للرد.
  - Ctrl+T لترجمة الرسالة الحالية.
  - Escape للرجوع إلى قائمة الرسائل من مستعرض الرسالة أو مستعرض العناصر.
  - Ctrl+Enter للتبديل بين مستعرض الرسالة ومستعرض العناصر.
  - Ctrl+A لإضافة حساب.
  - Ctrl+O لفتح الرابط المحدد.
  - F1 لعرض دليل البرنامج.
  - Alt+F4 لإغلاق البرنامج.

## تسجيل الدخول عبر المتصفح

يدعم البرنامج تسجيل الدخول عبر المتصفح لحسابات:

- Google / Gmail
- Microsoft / Outlook

افتح "إضافة حساب" واختر طريقة التسجيل. عند اختيار التسجيل عبر المتصفح تظهر خدمات البريد كأزرار؛ الضغط على اسم الخدمة يفتح المتصفح مباشرة من دون زر "موافق" إضافي. أما نموذج التسجيل اليدوي فيحتفظ بزر "موافق" لحفظ البيانات.

مهم للمستخدم: لا تحتاج إلى كلمة مرور تطبيق أو كلمة مرور الحساب الأصلية. عند تجهيز مفاتيح OAuth سيعرض المتصفح صفحة اختيار الحساب ثم صفحة الموافقة، ويضغط المستخدم متابعة أو استمرار فقط.

مهم للمطور: لا يستطيع البرنامج قراءة حسابات أو كلمات مرور المتصفح مباشرة. يجب تسجيل التطبيق مرة واحدة لدى Google وMicrosoft، ثم وضع بيانات العملاء في ملف `oauth_clients.json` الموحد. هذه البيانات لا تظهر في واجهة المستخدم.

نطاقات OAuth المستخدمة:

- Gmail API: `openid email profile https://www.googleapis.com/auth/gmail.modify`
- Microsoft: `openid profile email offline_access https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send`

### تجهيز OAuth للمطور

1. أنشئ `oauth_clients.json` في جذر المشروع اعتمادا على `oauth_clients.example.json`.
2. سجل التطبيق في Google Cloud أو Microsoft Entra.
3. ضع بيانات الخدمتين في الملف الموحد:

```json
{
  "google_gmail_api": {
    "client_id": "ضع Google Gmail API Client ID هنا",
    "client_secret": "ضع Google Gmail API Client Secret هنا إن وجد"
  },
  "microsoft": {
    "client_id": "ضع Microsoft Application Client ID هنا",
    "client_secret": ""
  }
}
```

نسختا `x64` و`x86` تستخدمان ملف الاعتماد نفسه والميزات نفسها. يمكن أيضا ضبط القيم عبر متغيرات البيئة:

- `ACCESSIBLE_MAIL_GOOGLE_GMAIL_API_CLIENT_ID`
- `ACCESSIBLE_MAIL_GOOGLE_GMAIL_API_CLIENT_SECRET`
- `ACCESSIBLE_MAIL_MICROSOFT_CLIENT_ID`
- `ACCESSIBLE_MAIL_MICROSOFT_CLIENT_SECRET`

عند تسجيل Microsoft استخدم منصة Mobile and desktop applications واضبط Redirect URI على `http://localhost`.

## بناء نسختي Windows

المصدر واحد، والاختلاف الوحيد هو معمارية Python والمكتبات:

```powershell
.\build_release_power_accessible_mail_x64.ps1
.\build_release_power_accessible_mail_x86.ps1
```

تستخدم نسخة `x64` البيئة `.venv`، وتستخدم نسخة `x86` البيئة `.venv-x86`. ينتج البناء مثبتا ونسخة محمولة وبصمات SHA-256 لكل معمارية.

قبل البناء، يمكن التحقق من البيئتين والمصدر المشترك وقفل الحزم والاختبارات بأمر واحد:

```powershell
.\test_all_architectures.ps1
```

إذا نُقل مجلد المشروع إلى مسار جديد، فقد تبقى مشغلات البيئة الافتراضية مرتبطة بالمسار القديم. أصلح البيئتين من Python الأساسي المطابق ثم أعد الفحص:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe" -m venv --upgrade .venv
& "$env:LOCALAPPDATA\Programs\Python\Python314-32\python.exe" -m venv --upgrade .venv-x86
.\test_all_architectures.ps1
```

يتحقق الفاحص أيضا من معمارية bootloader الخاص بـPyInstaller، لا من معمارية Python فقط. إذا أبلغ عن bootloader غير مطابق، أعد تثبيت PyInstaller داخل البيئة المتأثرة:

```powershell
.\.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps pyinstaller==6.20.0
```

## ملاحظات مهمة للحسابات

الطريقة المعتمدة الآن هي تسجيل الدخول عبر المتصفح. لا تستخدم كلمة مرور الحساب الأصلية ولا كلمة مرور تطبيق داخل البرنامج.

إعدادات شائعة:

- Gmail:
  - IMAP: `imap.gmail.com`, المنفذ `993`, SSL.
  - SMTP: `smtp.gmail.com`, المنفذ `587`, STARTTLS.
  - مجلد غير مرغوب غالبا: `[Gmail]/Spam`.
- Outlook/Hotmail:
  - IMAP: `outlook.office365.com`, المنفذ `993`, SSL.
  - SMTP: `smtp-mail.outlook.com`, المنفذ `587`, STARTTLS.
  - مجلد غير مرغوب غالبا: `Junk Email`.
- Yahoo:
  - IMAP: `imap.mail.yahoo.com`, المنفذ `993`, SSL.
  - SMTP: `smtp.mail.yahoo.com`, المنفذ `587`, STARTTLS.
  - مجلد غير مرغوب غالبا: `Bulk Mail`.

## مكان حفظ الحسابات

يحفظ البرنامج إعدادات الحسابات في مجلد بيانات المستخدم:

- على Windows: `%APPDATA%\PowerAccessibleMail\accounts.json`
- على الأنظمة الأخرى: `~/.accessible_mail/accounts.json`

إذا اخترت حفظ كلمة المرور اليدوية أو رموز OAuth، تُخزن داخل هذا الملف بعد حمايتها باستخدام Windows DPAPI لحساب Windows الحالي. لا يكتب البرنامج هذه الأسرار كنص صريح، ويفشل الحفظ إذا تعذرت حمايتها.

## التخزين المحلي المشفر

يحفظ البرنامج الرسائل المستوردة في قاعدة بيانات محلية داخل:

`%APPDATA%\PowerAccessibleMail\.mail_store\messages.sqlite3`

المجلد مخفي على Windows، ومحتوى الرسائل والروابط وملخصات الرسائل تحفظ مشفرة باستخدام Windows DPAPI لحساب Windows الحالي. هذا يعني أن البرنامج يعرض الرسائل المحفوظة بسرعة في المرات التالية، ثم يحدّث أحدث دفعة من Gmail في الخلفية.

هذا ليس بديلا عن تشفير قرص Windows الكامل، لكنه يمنع قراءة الرسائل مباشرة من الملف بدون حساب Windows نفسه.

## تحديث البرنامج

يفحص البرنامج أحدث إصدار منشور في [GitHub Releases](https://github.com/alikrstle/PowerAccessibleMail/releases) بعد بدء التشغيل، ويمكن إجراء الفحص يدويا من قائمة "المساعدة" عبر "تحديث البرنامج". لا يحتاج المستخدم إلى رمز GitHub. عند وجود إصدار أحدث تظهر نافذة واضحة تحتوي على زري "تحديث الآن" و"إغلاق". يفتح زر التحديث مثبّت النسخة المطابقة مباشرة، أو صفحة الإصدار إذا لم يوجد ملف مطابق.

عند نشر إصدار جديد:

1. أنشئ GitHub Release منشورا، وليس Draft أو Pre-release.
2. استخدم وسم إصدار مثل `v1.2.13`.
3. ارفع `PowerAccessibleMailSetup-1.2.13-win-x64-UNSIGNED.exe` عند عدم توفر شهادة توقيع.
4. ارفع `PowerAccessibleMailSetup-1.2.13-win-x86-UNSIGNED.exe` عند عدم توفر شهادة توقيع.
5. ارفع ملفات ZIP وملفات بصمة SHA-256 للمعماريتين إلى الإصدار نفسه.

المستودع الافتراضي هو `alikrstle/PowerAccessibleMail`. يمكن تغييره لأغراض التطوير عبر:

`POWER_ACCESSIBLE_MAIL_GITHUB_REPOSITORY=owner/repository`

يبقى ملف JSON القديم مدعوما كخيار تجاوز. عند ضبط `POWER_ACCESSIBLE_MAIL_UPDATE_URL` أو وضع الرابط في `update_manifest_url.txt` بجانب البرنامج أو في مجلد بيانات المستخدم، يستخدم البرنامج ذلك الملف بدلا من GitHub Releases:

```json
{
  "version": "1.2.13",
  "downloads": {
    "x64": "https://example.com/PowerAccessibleMailSetup-1.2.13-win-x64.exe",
    "x86": "https://example.com/PowerAccessibleMailSetup-1.2.13-win-x86.exe"
  },
  "notes": "تحسينات في استلام الرسائل ودعم المرفقات."
}
```

يجب أن يستخدم رابط ملف JSON وروابط التنزيل HTTPS. لا يشغّل المحدث الداخلي مثبتا إلا إذا طابق اسم المنتج ورقم الإصدار ومعمارية البرنامج الحالية وتوفرت بصمة SHA-256 صحيحة.
