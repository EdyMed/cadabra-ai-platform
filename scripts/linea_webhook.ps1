# Dirección propia (webhook) de UNA línea de WhatsApp en Meta: manda sus mensajes a la plataforma o los devuelve a n8n.
# Meta prioriza: dirección del número > dirección de la cuenta (WABA) > dirección de la app (n8n).
#
#   ver       muestra qué dirección tiene la línea
#   activar   la línea pasa a la plataforma (exige que /healthz diga modo_ensayo=false y worker=true)
#   revertir  borra la dirección propia: la línea vuelve a n8n al instante
#
# Uso (PowerShell, desde la carpeta cadabra-ai-platform):
#   powershell -ExecutionPolicy Bypass -File scripts\linea_webhook.ps1 -Accion ver
#   powershell -ExecutionPolicy Bypass -File scripts\linea_webhook.ps1 -Accion activar
#   powershell -ExecutionPolicy Bypass -File scripts\linea_webhook.ps1 -Accion revertir
param(
    [Parameter(Mandatory = $true)][ValidateSet('ver', 'activar', 'revertir')][string]$Accion,
    [string]$PhoneNumberId = '1168256669712210',   # Sofía (empresa 1)
    [string]$Version = 'v23.0'
)
$ErrorActionPreference = 'Stop'
$plataforma = 'https://plataforma.appcadabra.cl'

# Token de Meta: el mismo que usan n8n y el panel (META_WA_TOKEN en app\CRM Whatsap\.env.local). No se imprime.
$envPanel = Join-Path $PSScriptRoot '..\..\CRM Whatsap\.env.local'
$linea = Get-Content $envPanel | Where-Object { $_ -match '^META_WA_TOKEN=' } | Select-Object -First 1
if (-not $linea) { throw "No encontré META_WA_TOKEN en $envPanel" }
$token = ($linea -replace '^META_WA_TOKEN=', '').Trim().Trim('"')
$cabeceras = @{ Authorization = "Bearer $token" }
$url = "https://graph.facebook.com/$Version/$PhoneNumberId"

function Mostrar {
    $r = Invoke-RestMethod -Uri "$url`?fields=display_phone_number,verified_name,webhook_configuration" -Headers $cabeceras
    Write-Host "Línea: $($r.verified_name) ($($r.display_phone_number))"
    Write-Host ("webhook_configuration: " + ($r.webhook_configuration | ConvertTo-Json -Compress))
}

if ($Accion -eq 'ver') { Mostrar; exit 0 }

if ($Accion -eq 'activar') {
    $salud = Invoke-RestMethod -Uri "$plataforma/healthz"
    if ($salud.estado -ne 'ok' -or -not $salud.worker) { throw "La plataforma no está sana: $($salud | ConvertTo-Json -Compress)" }
    if ($salud.modo_ensayo) { throw 'La plataforma sigue en MODO ENSAYO: no respondería. Pon CADABRA_MODO_ENSAYO=false en plataforma-worker e Implementar.' }
    $seguro = Read-Host 'Pega el valor de CADABRA_META_VERIFY_TOKEN (de plataforma-api en EasyPanel)' -AsSecureString
    $verify = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro))
    $cuerpo = @{ webhook_configuration = @{ override_callback_uri = "$plataforma/webhooks/whatsapp"; verify_token = $verify } } | ConvertTo-Json -Compress
}
else {
    $cuerpo = @{ webhook_configuration = @{ override_callback_uri = '' } } | ConvertTo-Json -Compress
}

$r = Invoke-RestMethod -Method Post -Uri $url -Headers $cabeceras -ContentType 'application/json' -Body $cuerpo
Write-Host ("Respuesta de Meta: " + ($r | ConvertTo-Json -Compress))
Mostrar
