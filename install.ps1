# install.ps1 — Instalador del script 8-bit Pixel Art para Siril (Windows)
# Uso: haz clic derecho sobre este archivo y selecciona "Ejecutar con PowerShell"
#      o desde una terminal: .\install.ps1

$ScriptName   = "8bit_pixel_art.py"
$ScriptSource = Join-Path $PSScriptRoot $ScriptName

# Directorios predeterminados donde Siril busca scripts en Windows
$candidatePaths = @(
    "$env:APPDATA\siril\scripts",
    "$env:LOCALAPPDATA\siril\scripts",
    "C:\Program Files\Siril\scripts",
    "C:\Program Files (x86)\Siril\scripts"
)

Write-Host ""
Write-Host "=== Instalador 8-bit Pixel Art para Siril ==="  -ForegroundColor Cyan
Write-Host ""
Write-Host "Buscando directorio de scripts de Siril..." -ForegroundColor Gray

$targetDir = $null
foreach ($path in $candidatePaths) {
    Write-Host "  Revisando: $path" -ForegroundColor DarkGray
    if (Test-Path $path) {
        $targetDir = $path
        Write-Host "  Encontrado!" -ForegroundColor Green
        break
    }
}

if (-not $targetDir) {
    Write-Host ""
    Write-Host "ERROR: No se encontro el directorio de scripts de Siril." -ForegroundColor Red
    Write-Host ""
    Write-Host "Ubicaciones buscadas:"
    foreach ($path in $candidatePaths) {
        Write-Host "  - $path"
    }
    Write-Host ""
    Write-Host "Para realizar la instalacion manualmente:" -ForegroundColor Yellow
    Write-Host "  1. Abre Siril."
    Write-Host "  2. Ve a  Preferencias > Carpetas  y anota la ruta del 'Directorio de scripts'."
    Write-Host "  3. Copia el archivo '$ScriptName' a esa carpeta."
    Write-Host "  4. Reinicia Siril."
    Write-Host "  5. El script aparecera en  Herramientas > Scripts > 8bit_pixel_art."
    Write-Host ""
    Read-Host "Presiona ENTER para cerrar"
    exit 1
}

if (-not (Test-Path $ScriptSource)) {
    Write-Host ""
    Write-Host "ERROR: No se encontro el archivo fuente '$ScriptName' junto a este instalador." -ForegroundColor Red
    Write-Host "Asegurate de que '$ScriptName' e 'install.ps1' esten en la misma carpeta."
    Write-Host ""
    Read-Host "Presiona ENTER para cerrar"
    exit 1
}

$targetFile = Join-Path $targetDir $ScriptName
Copy-Item -Path $ScriptSource -Destination $targetFile -Force

Write-Host ""
Write-Host "Instalacion exitosa!" -ForegroundColor Green
Write-Host "  Ruta: $targetFile"
Write-Host ""
Write-Host "Proximos pasos:" -ForegroundColor Cyan
Write-Host "  1. Reinicia Siril (si estaba abierto)."
Write-Host "  2. Carga una imagen."
Write-Host "  3. Ve a  Herramientas > Scripts > 8bit_pixel_art."
Write-Host "  4. Ajusta los controles y haz clic en 'Aplicar efecto'."
Write-Host ""
Read-Host "Presiona ENTER para cerrar"
