# Power Accessible Mail 1.2.12

## العربية

- إعادة تنظيم الواجهة إلى وحدات أصغر مع إبقاء `app.py` نقطة تشغيل وتوافق مستقرة.
- تحسين أمان فتح الروابط وحفظ المرفقات وتنظيف الملفات المؤقتة عند الإغلاق.
- جعل OAuth والعمليات الطويلة غير متزامنة للحفاظ على استجابة الواجهة.
- تقوية حماية الإعدادات والرموز والبيانات المحلية بواسطة Windows DPAPI.
- تحسين الحذف والمزامنة للحسابات التي تستخدم IMAP وGmail API.
- توحيد بناء نسختي x64 وx86 والتحقق من معمارية Python وPyInstaller وملف التطبيق.
- إضافة تحقق صارم من الإصدار المضمّن وبصمات SHA-256 وبيانات إصدار كل حزمة.

## English

- Split the interface into focused modules while keeping `app.py` as a stable entry point and compatibility surface.
- Improved safe link opening, attachment storage, and temporary-file cleanup at shutdown.
- Moved OAuth and long-running operations off the UI thread to preserve responsiveness.
- Hardened Windows DPAPI protection for local settings, tokens, and cached data.
- Improved deletion and synchronization behavior for IMAP and Gmail API accounts.
- Unified x64 and x86 builds with architecture checks for Python, PyInstaller, and the application executable.
- Added strict verification for embedded versions, SHA-256 digests, and per-package release metadata.
