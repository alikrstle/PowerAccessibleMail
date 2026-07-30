# Power Accessible Mail 1.2.13

## العربية

- إصلاح تعطل الترجمة المتقطع داخل مستعرض HTML ومنع إعادة تحميل الصفحة قبل اكتمال WebView.
- إضافة إعادة محاولة آمنة عند تعذر الاتصال المؤقت بخدمة الترجمة، ومنع نتيجة متأخرة من استبدال رسالة أخرى.
- استبدال اختصار `Ctrl+Space` بزر `Escape` للعودة إلى قائمة الرسائل من مستعرض HTML والمستعرض السهل ومستعرض العناصر.
- تحسين استعادة التركيز وإعادة فتح مستعرض HTML بعد الخروج منه.
- عرض يوم وتاريخ ووقت الرسالة وفق إعدادات Windows الإقليمية، بما فيها أسماء الشهور السريانية أو اللاتينية التي يختارها النظام.
- تحديث أدلة الاستخدام واختبارات إمكانية الوصول والسلوك في نسختي x64 وx86.

## English

- Fixed intermittent translation failures and crashes in the HTML viewer by waiting for WebView navigation to complete.
- Added a safe retry for temporary translation-service failures and prevented late results from replacing another message.
- Replaced `Ctrl+Space` with `Escape` for returning to the message list from the HTML, simple, and item viewers.
- Improved focus restoration and reopening of the HTML viewer after leaving it.
- Displayed message weekday, date, and time using the Windows regional format, including the system-selected month names.
- Updated the user guides and accessibility behavior tests for both x64 and x86 builds.
