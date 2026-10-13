# Установка serial-драйвера sprdvcom (BROM VID_1782&PID_4D00) через pnputil.
# Использование:
#   powershell -ExecutionPolicy Bypass -File scripts\install_driver.ps1 -DriverDir "C:\path\to\SPD_Driver_R4.20.0201"
param(
    [Parameter(Mandatory = $true)] [string]$DriverDir,
    [string]$InfName = "sprdvcom.inf"
)

if (-not (Test-Path $DriverDir)) {
    Write-Host "Каталог не найден: $DriverDir"
    exit 1
}

$inf = Get-ChildItem -Path $DriverDir -Filter $InfName -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $inf) {
    Write-Host "$InfName не найден в $DriverDir. Доступные .inf:"
    Get-ChildItem -Path $DriverDir -Filter "*.inf" -Recurse | ForEach-Object { Write-Host "  $($_.FullName)" }
    exit 1
}

Write-Host "Устанавливаю: $($inf.FullName)"
pnputil /add-driver "$($inf.FullName)" /install
Write-Host ""
Write-Host "Готово. Проверка:"
Write-Host "  1) Подключите телефон в BROM (см. README, Танец)"
Write-Host "  2) Диспетчер устройств → должно появиться sprdvcom (COMx) у устройства VID_1782&PID_4D00"
Write-Host "  Если устройство 'Неизвестно' с VID_1782&PID_4D00 — обновите драйвер вручную, указав этот inf."
