SEKY BARCODE - WINDOWS DESKTOP APP
=================================

The recommended app is the Windows installer:

  release\SekyBarcode-Setup.exe

For installation steps, database location, updates, and the test checklist,
read "README - Seky Barcode Windows Installer.md".

The old run.bat starts the browser-based Python server. It is for the previous
version and is not used by the
installed desktop app. After migration, use the Seky Barcode desktop shortcut
so all changes go to the database in %APPDATA%\SekyBarcode.

The desktop app starts its bundled backend automatically. It does not require
Python on the computer where the installer is installed. The app's database
is kept outside the install folder, so updates and reinstallations preserve it.

العربية
-------
التطبيق الموصى به هو:

  release\SekyBarcode-Setup.exe

لخطوات التثبيت ومكان قاعدة البيانات والتحديثات، اقرأ الملف:
"README - Seky Barcode Windows Installer.md".

ملف run.bat يشغّل النسخة القديمة التي تعمل في المتصفح وتحتاج إلى Python.
بعد نقل البيانات، افتح تطبيق Seky Barcode من
الاختصار الموجود على سطح المكتب حتى تُحفظ التغييرات في:
%APPDATA%\SekyBarcode
