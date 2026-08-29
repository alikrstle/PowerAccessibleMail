# سيناريو فيديو مراجعة Google OAuth — النسخة الثانية

اسم التطبيق: Power Accessible Mail

معرّف المشروع: `accessiblemail260527`

نطاق Gmail المطلوب: `https://www.googleapis.com/auth/gmail.modify`

هذه النسخة تجيب مباشرة عن ملاحظة فريق Third-Party Data Safety بأن الفيديو السابق لم يعرض أقصى وظائف التطبيق التي تستخدم `gmail.modify`.

## التحضير قبل التسجيل

1. استخدم حساب Gmail تجريبيًا لا يحتوي على معلومات شخصية.
2. جهز ثلاث رسائل بعناوين واضحة: `PAM READ TEST` و`PAM STAR TEST` و`PAM TRASH TEST`، مع مرفق صغير وآمن.
3. أبقِ Gmail Web مفتوحًا بالحساب التجريبي نفسه لإثبات نتيجة كل عملية كتابة.
4. احذف الحساب التجريبي من Power Accessible Mail أو ألغِ التفويض السابق كي تظهر شاشة موافقة Google كاملة أثناء التسجيل.
5. اجعل لغة شاشة موافقة Google هي الإنجليزية.
6. أبقِ حالة النشر **In production**.
7. لا تعرض كلمات المرور أو رموز OAuth أو سر العميل أو رسائل شخصية أو إشعارات لا تتعلق بالفيديو.
8. استخدم التكبير أو العناوين التوضيحية حتى تبقى الصلاحيات وعناوين الرسائل ونتائج Gmail مقروءة.

## تسلسل التسجيل المطلوب

### المشهد 1: هوية التطبيق والغرض منه

اعرض Power Accessible Mail وواجهته المكتبية القابلة للوصول.

النص الإنجليزي المقترح على الشاشة:

> Power Accessible Mail is a Windows desktop email client designed for blind and screen-reader users. This video demonstrates every production feature that currently uses gmail.modify and verifies each write operation in the source Gmail account.

### المشهد 2: تدفق OAuth كاملًا

1. افتح خيارات الحسابات وإدارتها.
2. اختر إضافة حساب ثم المتابعة باستخدام Google.
3. اعرض صفحة اختيار الحساب الرسمية.
4. اختر الحساب التجريبي.
5. اعرض شاشة الموافقة الإنجليزية كاملة وباسم Power Accessible Mail.
6. اضغط **Show all services** إن ظهر.
7. توقف وكبّر العرض حتى تصبح كل الصلاحيات موسعة ومقروءة.
8. وضح أن الصلاحيات تطابق Google Cloud: `openid` و`email` و`profile` و`gmail.modify`.
9. اختر **Allow** أو **Continue**.
10. ارجع إلى البرنامج واعرض نافذة نجاح إضافة الحساب.

### المشهد 3: عرض أقسام البريد

حدّث البريد واعرض الرسائل الواردة، ثم اعرض بإيجاز أقسام Spam وSent وAll Mail وTrash.

النص الإنجليزي:

> The app uses Gmail API to list Inbox, Spam, Sent, All Mail, and Trash messages selected by the user.

### المشهد 4: قراءة رسالة وجلب مرفق

افتح `PAM READ TEST` واعرض المرسل والموضوع والنص، ثم افتح مستعرض العناصر واعرض المرفق الآمن والروابط.

النص الإنجليزي:

> gmail.modify provides the read access required to retrieve the full selected message and its attachments. gmail.metadata would not provide message bodies or attachment content.

### المشهد 5: التحويل إلى غير مقروءة وإثبات النتيجة

1. حوّل `PAM READ TEST` إلى غير مقروءة من البرنامج.
2. انتظر رسالة نجاح الحفظ في الخادم.
3. انتقل إلى Gmail Web وحدّث الصفحة واعرض الرسالة نفسها كغير مقروءة.

### المشهد 6: التحويل إلى مقروءة وإثبات النتيجة

1. ارجع إلى البرنامج وحوّل الرسالة نفسها إلى مقروءة.
2. انتظر تأكيد الخادم.
3. حدّث Gmail Web واعرض أنها أصبحت مقروءة.

### المشهد 7: إضافة النجمة وإزالتها

1. أضف نجمة إلى `PAM STAR TEST` داخل البرنامج.
2. حدّث Gmail Web واعرض النجمة.
3. أزل النجمة داخل البرنامج.
4. حدّث Gmail Web مرة أخرى واعرض اختفاءها.

### المشهد 8: إرسال رسالة وإثباتها في Sent

1. أنشئ رسالة بعنوان `PAM OAUTH SEND TEST`، ويمكن إرفاق ملف آمن.
2. أرسل الرسالة.
3. افتح Gmail Web ثم Sent وحدّث الصفحة واعرض الرسالة والمرفق.

### المشهد 9: الرد وإثباته داخل المحادثة

1. رد من البرنامج على رسالة اختبار بعنوان `PAM OAUTH REPLY TEST`.
2. أرسل الرد.
3. افتح المحادثة نفسها في Gmail Web واعرض الرد الجديد.

### المشهد 10: النقل إلى سلة المحذوفات

1. اختر `PAM TRASH TEST` داخل البرنامج.
2. نفذ النقل إلى سلة Gmail ووافق على نافذة التأكيد.
3. افتح Gmail Web ثم Trash وحدّث الصفحة واعرض الرسالة نفسها.
4. لا تحذف الرسالة نهائيًا.

النص الإنجليزي:

> The app moves a selected message to Gmail Trash only after explicit user confirmation. It does not permanently delete Gmail messages and does not request the broader mail.google.com scope.

### المشهد 11: توضيح مبدأ أقل الصلاحيات

النص الإنجليزي الختامي:

> gmail.send alone cannot list or read the mailbox. gmail.readonly cannot change read state, change the Starred label, or move messages to Trash. Combining gmail.readonly and gmail.send still cannot perform those message-management operations. gmail.modify is therefore the narrowest Gmail scope that supports the complete production email-client workflow demonstrated in this video.

> Gmail data and OAuth tokens remain on the user's Windows device and are not sent to a developer-controlled server. Local cached data and saved OAuth credentials are protected for the current Windows account using Windows DPAPI.

## ملاحظات المونتاج والإرسال

- ضع عنوانًا إنجليزيًا قصيرًا قبل كل مشهد يذكر العملية التي ستُعرض.
- أبقِ عنوان رسالة الاختبار ظاهرًا عند الانتقال بين التطبيق وGmail Web.
- لكل عملية كتابة: اعرض التنفيذ في Power Accessible Mail أولًا، ثم النتيجة في Gmail Web.
- لا تسرّع أو تقطع مشهد الصلاحيات الموسعة في شاشة الموافقة.
- لا تستهلك وقت الفيديو في الترجمة أو التثبيت المحلي أو سجل العناوين أو التحديثات؛ هذه لا تبرر `gmail.modify`.
- ارفع الفيديو النهائي بوضع **Unlisted**، واختبر فتحه دون تسجيل دخول، ثم رد مباشرة على سلسلة بريد OAuth Verification الحالية بالرابط الجديد.
