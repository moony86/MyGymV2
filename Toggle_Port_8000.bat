@echo off
chcp 65001 >nul
:: فحص الصلاحيات وطلبها تلقائياً إذا لم تكن متوفرة
NWX 2>nul
openfiles >nul 2>&1
if %errorlevel% neq 0 (
    echo [+] جاري طلب صلاحيات المسؤول...
    powershell -Command "Start-Process -FilePath '%0' -ArgumentList 'am_admin' -Verb RunAs"
    exit /b
)

set RULE_NAME=Temp_Port_8000
set PORT=8000

cls
echo ===========================================
echo       متحكم بورت %PORT% المؤقت
echo ===========================================
echo.

:: فحص ما إذا كانت القاعدة موجودة مسبقاً
powershell -Command "Get-NetFirewallRule -DisplayName '%RULE_NAME%' -ErrorAction SilentlyContinue" >nul 2>&1

if %errorLevel% equ 0 (
    echo [-] البورت %PORT% مفتوح حالياً.
    echo [+] جاري إغلاقه وحذف القاعدة من جدار الحماية...
    powershell -Command "Remove-NetFirewallRule -DisplayName '%RULE_NAME%'"
    echo [V] تم إغلاق البورت بنجاح.
) else (
    echo [-] البورت %PORT% مغلق حالياً.
    echo [+] جاري فتحه مؤقتاً في جدار الحماية...
    powershell -Command "New-NetFirewallRule -DisplayName '%RULE_NAME%' -Direction Inbound -Action Allow -Protocol TCP -LocalPort %PORT%"
    echo [V] تم فتح البورت %PORT% بنجاح.
)

echo.
echo ===========================================
pause