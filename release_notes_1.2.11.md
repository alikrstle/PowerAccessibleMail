# Power Accessible Mail 1.2.11

## العربية

- تحويل اختيارات طريقة إضافة الحساب وخدمات OAuth إلى قوائم أصلية متوافقة مع قارئ الشاشة، مع تفعيل العنصر بواسطة Enter أو النقر الأيمن أو زر موافق.
- إضافة زر الاستمرار مع Microsoft إلى شاشة التشغيل الأول.
- جعل خدمة البريد أول عنصر في التسجيل اليدوي، مع اختيار Google أو Microsoft وتعبئة خوادم IMAP وSMTP المناسبة.
- تقليل مهلة نطق الدخول والخروج من وضع التحديد المتعدد إلى 300 مللي ثانية.
- إعادة كتابة دليل المستخدم ونصوص المثبت بالعربية والإنجليزية بأسلوب مباشر، وإضافة الدليلين إلى النسخ المحمولة.
- إضافة محدث داخلي ينزل المثبت الصحيح من GitHub من دون فتح المتصفح.
- عرض رقم الإصدار وتاريخ الإطلاق وشريط التقدم والنسبة المئوية أثناء التنزيل.
- التحقق من بصمة SHA-256 قبل تشغيل المثبت، مع دعم الإلغاء وإعادة تشغيل البرنامج بعد التحديث.
- إصلاح توافق Microsoft IMAP عند رفض الخادم أمر EXAMINE، مع انتقال آمن إلى SELECT واستمرار جلب المحتوى من دون تعليم الرسالة كمقروءة.
- إبقاء صندوق الحسابات وقائمة الأوامر مفعّلين أثناء المزامنة، ومنع قفز التركيز عند تبديل الحسابات أو تحديث الرسائل.
- وضع التركيز على صندوق الحسابات عند بدء البرنامج، وحفظ الحساب المحدد عند إعادة تحميل القائمة.
- منع مستعرض HTML من استعادة التركيز متأخراً بعد انتقال المستخدم إلى جزء آخر من الواجهة.

## English

- Converted account-method and OAuth-service choices to native screen-reader-accessible lists with Enter, right-click, and OK-button activation.
- Added Continue with Microsoft to the first-run sign-in screen.
- Made Email service the first manual-sign-in field, with Google and Microsoft choices that fill the matching IMAP and SMTP settings.
- Reduced multiple-selection entry and exit announcements to 300 milliseconds.
- Rewrote the Arabic and English user guides and installer text in a direct narrative style, and included both guides in portable packages.
- Added an internal updater that downloads the correct GitHub installer without opening a browser.
- Shows the version, release date, progress bar, and percentage while downloading.
- Verifies SHA-256 before launching Setup, supports cancellation, and restarts the application after updating.
- Fixed Microsoft IMAP compatibility when the server rejects EXAMINE by safely falling back to SELECT while continuing to fetch message bodies without marking them as read.
- Keeps the account selector and command list enabled during synchronization and prevents focus jumps while switching accounts or refreshing messages.
- Focuses the account selector at startup and preserves the selected account when the list is rebuilt.
- Prevents the HTML viewer from reclaiming focus after the user has moved to another part of the interface.
