# تجهيز موافقة Google OAuth

هذه الملفات تساعدك في إرسال تطبيق Power Accessible Mail إلى Google للمراجعة حتى يظهر تسجيل الدخول عبر المتصفح بشكل رسمي للمستخدمين.

## مهم جدا

Google لا تطلب عادة رفع ملف البرنامج فقط. المراجعة تتم من داخل Google Cloud Console، وتحتاج:

- مشروع Google Cloud خاص بالتطبيق.
- شاشة OAuth Consent Screen مكتملة.
- صفحة رئيسية للتطبيق على نطاق تملكه.
- سياسة خصوصية منشورة على نفس النطاق.
- شرح سبب طلب صلاحيات Gmail.
- فيديو توضيحي يبين تسجيل الدخول واستخدام صلاحيات Gmail داخل البرنامج.

## النطاق الحالي في البرنامج

البرنامج يستخدم حاليا:

`https://mail.google.com/`

هذا النطاق مصنف من Google كنطاق Gmail مقيد Restricted؛ لأنه يعطي وصولا واسعا للبريد. السبب التقني لاستخدامه حاليا هو أن البرنامج يعمل عبر IMAP و SMTP مع XOAUTH2.

## الطريق الأسرع للمختبرين فقط

إذا كان لديك عدد صغير من المختبرين، لا تحتاج موافقة عامة الآن:

1. افتح Google Cloud Console.
2. افتح مشروع التطبيق.
3. OAuth consent screen.
4. اجعل التطبيق في Testing.
5. أضف حسابات المختبرين في Test users.
6. أعطهم النسخة التي تحتوي على `oauth_clients.json`.

هذا مناسب للتجربة قبل النشر العام.

## الطريق الرسمي للنشر العام

1. أنشئ أو افتح مشروع Google Cloud الخاص بالتطبيق.
2. فعّل Gmail API إن كنت ستستخدم Gmail API. أما النسخة الحالية عبر IMAP/SMTP فتحتاج OAuth فقط مع نطاق `https://mail.google.com/`.
3. افتح OAuth consent screen.
4. اختر External.
5. املأ:
   - App name: Power Accessible Mail
   - User support email: بريد دعم تملكه
   - App domain/homepage: رابط صفحة البرنامج
   - Privacy policy: رابط سياسة الخصوصية
   - Developer contact email
6. أضف النطاقات المطلوبة في Authorized domains.
7. أضف النطاقات المطلوبة في Data Access / Scopes:
   - `openid`
   - `email`
   - `profile`
   - `https://mail.google.com/`
8. انشر التطبيق إلى Production.
9. اضغط Prepare for verification.
10. أضف تبرير النطاقات من ملف `scope_justification_en.md`.
11. أضف رابط فيديو العرض بعد تسجيله حسب `demo_video_script_ar.md`.
12. أرسل الطلب وانتظر مراسلة Google على بريد مالك المشروع.

## ملفات هذه الحزمة

- `privacy_policy_en.md`: نص سياسة خصوصية إنجليزي للنشر.
- `privacy_policy_ar.md`: نسخة عربية للمستخدمين.
- `scope_justification_en.md`: تبرير الصلاحيات لـ Google.
- `demo_video_script_ar.md`: سيناريو فيديو المراجعة.
- `homepage_content_ar.md`: نص مناسب لصفحة تعريف البرنامج.
- `submission_checklist_ar.md`: قائمة تحقق قبل الإرسال.

## نصيحتي الفنية

للإصدار العام، الأفضل لاحقا نقل Gmail من IMAP/SMTP إلى Gmail API بنطاقات أضيق قدر الإمكان. سيبقى بعض وصول Gmail مقيدا، لكن Google تفضّل دائما أقل نطاق ممكن بدل `https://mail.google.com/`.
